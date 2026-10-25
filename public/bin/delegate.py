import sys
import os
import json
import argparse
import tempfile
import shutil
import threading
import subprocess
import http.server

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import delegate_prep
import delegate_call
import send_rules
import budget_rules
import answer_rules
import engine_lock
import journal_log
import journal_rules
import anon_rules
import verify_rules
import eta_rules
import run_limits
import limits_files

try:
    import verify_sandbox
except ImportError:
    verify_sandbox = None

try:
    import journal_guard
except ImportError:
    journal_guard = None

NOTICE = (
    "NAME      delegate.py - sends a task to a role's model and, with --verify, retries until the check passes, never writing an unchecked attempt to the target.\n"
    "READS     --file; models.json, preferences.json and, for a non-private model, anonymization.json (--models, else FRUGALFLOW_HOME, else ~/.frugalflow); .frugalflow.json in the working directory (--tries, --max-tokens and --trust may only tighten their ceilings); the delegation log, for the delay estimate; the engine's answers.\n"
    "WRITES    --out once verified; the candidate file next to it; one line in the delegation log, with its duration. Exit 0 done, 2 arguments, 3 checks, 4 content, 5 not verified, 6 answer refused, 7 brief refused.\n"
    "EXAMPLE   python3 delegate.py --role code --file task.md --out tool.py --verify 'python3 \"$FRUGALFLOW_CANDIDATE\" --autotest' --verify-timeout 900\n"
    "PITFALLS  2026-09-18 a failed last attempt landed in the target; the target now only receives a verified attempt.\n"
    "          2026-09-23 the candidate lost its extension and the check could not load it; it keeps the target's extension.\n"
    "          2026-09-26 a faulty brief could be sent and a check naming the target failed every attempt; the brief is checked before sending, the check is corrected to the candidate."
)


def _guard_home():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow")


def _guard_protected_paths():
    home = _guard_home()
    if journal_guard is not None:
        try:
            with open(os.path.join(home, "guard.json"), "r", encoding="utf-8") as f:
                settings = json.load(f)
        except (OSError, ValueError):
            settings = {}
        if not isinstance(settings, dict):
            settings = {}
        return journal_guard.protected_paths(home, settings)
    return [os.path.join(home, "delegations.jsonl"), os.path.join(home, "guard.json"), os.path.join(home, "blocks")]


def _refuse_protected_out(args):
    if not args.out:
        return None
    protected = _guard_protected_paths()
    paths = [args.out]
    if args.verify:
        paths.append(answer_rules.candidate_path(args.out))
    for p in paths:
        rp = os.path.realpath(p)
        for pp in protected:
            rpp = os.path.realpath(pp)
            if rp == rpp or rp.startswith(rpp + os.sep):
                return "OUT REFUSED: " + rp + " is one of the guard's own files"
    return None


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE + "\n")
        sys.exit(0)
    if len(sys.argv) >= 2 and sys.argv[1] == "--autotest":
        autotest()
        return

    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--role", required=True)
    parser.add_argument("--file", required=True)
    parser.add_argument("--out", default=None)
    parser.add_argument("--verify", default=None)
    parser.add_argument("--tries", type=int, default=None)
    parser.add_argument("--trust", default=None)
    parser.add_argument("--models", default=None)
    parser.add_argument("--system", default="You are a rigorous software engineer. Answer without preamble.")
    parser.add_argument("--effort", default=None)
    parser.add_argument("--no-thinking", action="store_true")
    parser.add_argument("--bench", action="store_true")
    parser.add_argument("--max-tokens", type=int, default=None)
    parser.add_argument("--timeout", type=float, default=1800.0)
    parser.add_argument("--brief-waiver", default=None)
    parser.add_argument("--verify-weak", default=None)
    parser.add_argument("--verify-timeout", type=float, default=900.0)

    try:
        args = parser.parse_args()
    except SystemExit as e:
        if e.code == 2:
            print("usage: delegate.py --role NAME --file TASK [--out FILE --verify CMD --tries N] [--trust LEVEL] [--models FILE] [--effort LEVEL] [--no-thinking] [--bench] [--max-tokens N] [--brief-waiver REASON] [--verify-weak REASON] [--verify-timeout SECONDS]")
            sys.exit(2)
        sys.exit(e.code)

    if args.verify and not args.out:
        print("VERIFY NEEDS --out")
        sys.exit(2)

    if args.verify and verify_sandbox is None:
        sys.stderr.write("VERIFY REFUSED: verify_sandbox.py must be restored next to delegate.py; --verify is never run outside the sandbox\n")
        sys.exit(2)

    guard_refusal = _refuse_protected_out(args)
    if guard_refusal:
        sys.stderr.write(guard_refusal + "\n")
        sys.exit(3)

    # Step 2b: the ceilings of preferences.json and .frugalflow.json; an option may only tighten.
    models_path = args.models or os.path.join(os.environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow"), "models.json")
    prefs, project, error = limits_files.read(models_path, os.getcwd())
    if error is None:
        limits, error = run_limits.resolve(prefs, project, {"tries": args.tries, "max_tokens": args.max_tokens, "trust": args.trust})
    if error:
        print(error)
        sys.exit(2)
    explicit_cap = args.max_tokens is not None
    args.tries, args.max_tokens, args.trust = limits["tries"], limits["max_tokens"], limits["trust"]

    # Step 3
    verify_cmd = None
    judge_lines = []
    if args.verify:
        code, verify_cmd, judge_lines = verify_rules.judge(args.verify, args.out, args.verify_weak)
        for line in judge_lines:
            print(line)
        if code != 0:
            sys.exit(3)

    # Step 4
    try:
        with open(args.file, "r", encoding="utf-8") as f:
            prompt = f.read()
    except OSError:
        print("NO TASK FILE: " + args.file)
        sys.exit(2)

    # Step 5
    brief_cmd = [
        sys.executable,
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "brief_check.py"),
        "--brief", args.file,
        "--trust", "untrusted_third_party" if args.trust == "untrusted_third_party" else "private",
    ]
    if args.brief_waiver:
        brief_cmd += ["--waiver", args.brief_waiver]

    r = subprocess.run(brief_cmd, capture_output=True, text=True, timeout=60)

    if r.returncode == 5:
        sys.stdout.write(r.stdout)
        print("BRIEF REFUSED: nothing sent")
        sys.exit(7)
    elif r.returncode != 0:
        sys.stdout.write(r.stdout)
        print("BRIEF CHECK FAILED: code " + str(r.returncode))
        sys.exit(3)
    else:
        sys.stderr.write(r.stdout)

    waivers = []
    if "ACCEPTED WITH WAIVER" in r.stdout:
        waivers.append("brief: " + args.brief_waiver)
    if args.verify_weak:
        for line in judge_lines:
            if line.startswith("VERIFY WEAK ACCEPTED"):
                waivers.append("verify: " + args.verify_weak)
                break
    waiver = "; ".join(waivers) if waivers else None

    # Step 6
    plan, code, message = delegate_prep.prepare(models_path, args.role, args.trust, args.bench, args.timeout)
    if code != 0:
        print(message)
        sys.exit(code)

    # Step 7
    A, I = [], []
    if plan["trust"] != "private":
        anon_path = os.path.join(os.path.dirname(os.path.abspath(models_path)), "anonymization.json")
        try:
            with open(anon_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
            A, I, errors = anon_rules.load(doc)
            if errors:
                print("NO RULES: anonymization.json missing or invalid")
                sys.exit(4)
        except (OSError, ValueError):
            print("NO RULES: anonymization.json missing or invalid")
            sys.exit(4)

    to_send, table, counts, refusal = send_rules.outbound(prompt, plan["trust"], A, I)
    if refusal:
        print("CONTENT REFUSED: " + refusal)
        sys.exit(4)
    # the system message leaves too: same filter, same table (restored on the way back)
    system_sent, table, sys_counts, sys_refusal = send_rules.outbound(args.system, plan["trust"], A, I, table)
    if sys_refusal:
        print("CONTENT REFUSED: --system: " + sys_refusal)
        sys.exit(4)
    for k, v in sys_counts.items():
        counts[k] = counts.get(k, 0) + v
    ann = send_rules.announce(counts)
    if ann:
        sys.stderr.write(ann)

    # Step 8
    cap = args.max_tokens if explicit_cap else plan["max_output"]
    if not explicit_cap and args.max_tokens is not None:
        cap = args.max_tokens if cap is None else min(cap, args.max_tokens)
    if cap is None:
        print("NO OUTPUT CAP: set max_output in models.json or pass --max-tokens")
        sys.exit(2)

    max_tokens, why = budget_rules.plan_max_tokens(plan["window"], len(to_send) + len(system_sent), 2, cap)
    if why:
        print("TASK TOO BIG: " + why)
        sys.exit(3)

    # Step 9
    try:
        with open(journal_log.default_path(), "r", encoding="utf-8") as f:
            records, _unreadable = journal_rules.parse_lines(f.read())
    except OSError:
        records = []
    est = eta_rules.estimate(records, plan["name"], len(prompt))
    sys.stderr.write(eta_rules.describe(est) + "\n")

    # Step 10
    lock = None
    if plan["location"] == "local":
        lock = engine_lock.acquire(plan["name"], plan["slots"], wait=args.timeout)
        if lock is None:
            print("ENGINE BUSY: " + plan["name"])
            sys.exit(3)

    try:
        # Step 11
        first_line = prompt.split("\n", 1)[0]
        journal_log.arm(journal_log.default_path(), args.role, plan["name"], args.out, first_line, chars=len(prompt), waiver=waiver)

        # Step 12
        base = [{"role": "system", "content": system_sent}, {"role": "user", "content": to_send}]
        if args.no_thinking:
            base.append({"role": "assistant", "content": "<think>\n\n</think>\n\n"})
        extra = {"chat_template_kwargs": {"reasoning_effort": args.effort}} if args.effort else None

        def do_call(messages):
            return delegate_call.call(plan["endpoint"], plan["name"], messages, plan["settings"], max_tokens, args.timeout, plan["key"], extra)

        def check_substitution(ans):
            if ans["refusal"] and ans["refusal"].startswith("model substituted"):
                journal_log.conclude("failure", ans["refusal"], ans["tokens_in"], ans["tokens_out"], ans["model"])
                print("ANSWER REFUSED: " + ans["refusal"])
                sys.exit(6)

        # Step 13
        if not args.verify:
            ans = do_call(base)
            check_substitution(ans)

            if ans["truncated"]:
                msgs2 = base + [{"role": "user", "content": answer_rules.RETRY_TRUNCATED}]
                ans = do_call(msgs2)
                check_substitution(ans)

            if ans["refusal"] or ans["truncated"]:
                reason = ans["refusal"] if ans["refusal"] else "truncated"
                journal_log.conclude("failure", reason, ans["tokens_in"], ans["tokens_out"], ans["model"])
                print("ANSWER REFUSED: " + reason)
                sys.exit(6)

            text = send_rules.inbound(ans["content"], table)
            if args.out:
                out_dir = os.path.dirname(os.path.abspath(args.out))
                fd, tmp = tempfile.mkstemp(dir=out_dir, prefix=".", suffix=os.path.splitext(args.out)[1])
                m = os.umask(0)
                os.umask(m)
                os.fchmod(fd, 0o666 & ~m)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(answer_rules.strip_fences(text))
                os.replace(tmp, args.out)
            print(text)
            journal_log.conclude("success", None, ans["tokens_in"], ans["tokens_out"], ans["model"])
            sys.exit(0)

        # Step 14
        cand = answer_rules.candidate_path(args.out)
        messages = base

        for attempt in range(1, args.tries + 1):
            ans = do_call(messages)
            check_substitution(ans)

            if ans["refusal"]:
                report = ans["refusal"]
            else:
                content = answer_rules.strip_fences(send_rules.inbound(ans["content"], table))
                if os.path.lexists(cand):
                    os.unlink(cand)
                fd = os.open(cand, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
                with os.fdopen(fd, "w", encoding="utf-8") as f:
                    f.write(content)
                code, output = verify_sandbox.run_isolated(verify_cmd, cand, args.out, os.getcwd(), args.verify_timeout)
                if code == 0:
                    os.replace(cand, args.out)
                    journal_log.conclude("success", None, ans["tokens_in"], ans["tokens_out"], ans["model"])
                    print("VERIFIED at attempt " + str(attempt) + "/" + str(args.tries) + ": " + args.out)
                    sys.exit(0)
                else:
                    report = output[-4000:]
                    if code in (124, 125):
                        sys.stderr.write(output + "\n")

            sys.stderr.write("attempt " + str(attempt) + " rejected\n")

            report_sent = send_rules.outbound(report, plan["trust"], A, I, table)[0]
            if report_sent is None:
                report_sent = "the check failed; its output cannot be shared"

            messages = answer_rules.retry_messages(base, ans["content"], report_sent, ans["truncated"])

        last_reason = ans["refusal"] if ans["refusal"] else "check failed"
        journal_log.conclude("failure", "not verified after " + str(args.tries) + " attempts, last: " + last_reason,
                            ans["tokens_in"], ans["tokens_out"], ans["model"])
        print("NOT VERIFIED after " + str(args.tries) + " attempts: " + args.out + " unchanged, last attempt in " + cand)
        sys.exit(5)
    finally:
        if lock:
            engine_lock.release(lock)


def autotest():
    D = tempfile.mkdtemp()
    G = chr(96) * 3

    def models_doc(port):
        own = {"id": "own", "name": "alpha-7b", "location": "remote",
               "endpoint": "http://127.0.0.1:" + str(port) + "/v1",
               "context_window": 8192, "trust": "private", "key_env": "", "max_output": 1024}
        far = dict(own, id="far", trust="untrusted_third_party")
        return {"models": [own, far],
                "layers": [{"name": "work", "delegable": True}],
                "roles": [{"name": "code", "layer": "work", "model": "own"},
                          {"name": "far", "layer": "work", "model": "far"}]}

    RULES = {"limits": {}, "rules": [{"id": "N1", "title": "no nature",
                                      "born_from": {"date": "2026-01-01", "incident": "i"},
                                      "fix": "write nature:", "trigger": {},
                                      "requirement": {"type": "regex_all", "patterns": ["nature:"]}}]}
    TASK = "NATURE: creation\nWrite print(42).\n"
    BAD = "Write print(42).\n"
    CHECK = 'python3 "$FRUGALFLOW_CANDIDATE" | grep -q 42'

    state = {"QUEUE": [], "MODEL": "alpha-7b", "BODIES": []}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path == "/v1/chat/completions":
                length = int(self.headers.get("Content-Length", 0))
                body = self.rfile.read(length)
                state["BODIES"].append(json.loads(body))
                content = state["QUEUE"].pop(0)
                resp = {"model": state["MODEL"],
                        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                        "usage": {"prompt_tokens": 10, "completion_tokens": 5}}
                data = json.dumps(resp).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, fmt, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    with open(os.path.join(D, "models.json"), "w", encoding="utf-8") as f:
        json.dump(models_doc(port), f)
    with open(os.path.join(D, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(RULES, f)
    with open(os.path.join(D, "task.md"), "w", encoding="utf-8") as f:
        f.write(TASK)
    with open(os.path.join(D, "bad.md"), "w", encoding="utf-8") as f:
        f.write(BAD)

    env = dict(os.environ, FRUGALFLOW_HOME=D, FRUGALFLOW_BRIEF_RULES=os.path.join(D, "rules.json"))
    base_cmd = [sys.executable, os.path.abspath(__file__), "--timeout", "10"]
    jpath = os.path.join(D, "delegations.jsonl")

    def last_journal():
        with open(jpath, "r", encoding="utf-8") as f:
            lines = [l for l in f.read().split("\n") if l.strip()]
        return json.loads(lines[-1])

    def journal_line_count():
        try:
            with open(jpath, "r", encoding="utf-8") as f:
                return len([l for l in f.read().split("\n") if l.strip()])
        except OSError:
            return 0

    results = []

    def reset():
        state["QUEUE"] = []
        state["MODEL"] = "alpha-7b"
        state["BODIES"] = []

    # --- Test 1 ---
    reset()
    state["QUEUE"].append(G + "python\nprint(42)\n" + G)
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", os.path.join(D, "a.py")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 0:
        ok = False
        details.append("code=" + str(p.returncode))
    try:
        with open(os.path.join(D, "a.py"), "r", encoding="utf-8") as f:
            ac = f.read()
        if ac != "print(42)\n":
            ok = False
            details.append("a.py=" + repr(ac))
    except OSError:
        ok = False
        details.append("a.py missing")
    if len(state["BODIES"]) != 1:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    try:
        jl = last_journal()
        if jl["status"] != "success":
            ok = False
            details.append("status=" + str(jl["status"]))
        if jl["model_answered"] != "alpha-7b":
            ok = False
            details.append("model=" + str(jl["model_answered"]))
        if jl["chars"] != len(TASK):
            ok = False
            details.append("chars=" + str(jl["chars"]))
        if jl.get("waiver") is not None:
            ok = False
            details.append("waiver=" + str(jl.get("waiver")))
        sec = jl.get("seconds")
        if isinstance(sec, bool) or not isinstance(sec, (int, float)) or sec < 0:
            ok = False
            details.append("seconds=" + repr(sec))
    except Exception as ex:
        ok = False
        details.append("journal error: " + str(ex))
    results.append(("test1", ok, "code=0 a.py=print(42) 1req success alpha-7b", "; ".join(details) if details else "ok"))

    # --- Test 2 ---
    reset()
    state["QUEUE"].extend(["print(1)", "print(42)"])
    verify2 = "python3 " + os.path.join(D, "b.py") + " | grep -q 42"
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", os.path.join(D, "b.py"), "--verify", verify2]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 0:
        ok = False
        details.append("code=" + str(p.returncode))
    if "VERIFY CORRECTED: " not in p.stdout:
        ok = False
        details.append("no VERIFY CORRECTED in stdout")
    if "VERIFIED at attempt 2/3: " not in p.stdout:
        ok = False
        details.append("no VERIFIED line in stdout: " + p.stdout[:150])
    try:
        with open(os.path.join(D, "b.py"), "r", encoding="utf-8") as f:
            bc = f.read()
        if bc != "print(42)\n":
            ok = False
            details.append("b.py=" + repr(bc))
    except OSError:
        ok = False
        details.append("b.py missing")
    if len(state["BODIES"]) != 2:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    else:
        msgs = state["BODIES"][1].get("messages", [])
        if len(msgs) != 4:
            ok = False
            details.append("msgs_len=" + str(len(msgs)))
        else:
            c3 = msgs[3].get("content", "")
            if not c3.startswith("This code fails."):
                ok = False
                details.append("msg3=" + c3[:50])
    results.append(("test2", ok, "code=0 CORRECTED VERIFIED 2/3 b.py=print(42) 2req 4msgs", "; ".join(details) if details else "ok"))

    # --- Test 3 ---
    reset()
    with open(os.path.join(D, "c.py"), "w", encoding="utf-8") as f:
        f.write("keep\n")
    state["QUEUE"].extend(["print(1)", "print(2)"])
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", os.path.join(D, "c.py"), "--verify", CHECK, "--tries", "2"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 5:
        ok = False
        details.append("code=" + str(p.returncode))
    with open(os.path.join(D, "c.py"), "r", encoding="utf-8") as f:
        if f.read() != "keep\n":
            ok = False
            details.append("c.py modified")
    cand_p = os.path.join(D, "c.candidate.py")
    try:
        with open(cand_p, "r", encoding="utf-8") as f:
            cc = f.read()
        if cc != "print(2)\n":
            ok = False
            details.append("candidate=" + repr(cc))
    except OSError:
        ok = False
        details.append("candidate missing")
    try:
        jl = last_journal()
        if jl["status"] != "failure":
            ok = False
            details.append("status=" + str(jl["status"]))
        if jl["model_answered"] != "alpha-7b":
            ok = False
            details.append("model=" + str(jl["model_answered"]))
        exp_r = "not verified after 2 attempts, last: check failed"
        if jl.get("reason") != exp_r:
            ok = False
            details.append("reason=" + str(jl.get("reason")))
    except Exception as ex:
        ok = False
        details.append("journal error: " + str(ex))
    results.append(("test3", ok, "code=5 keep unchanged candidate=print(2) failure", "; ".join(details) if details else "ok"))

    # --- Test 4a ---
    reset()
    state["MODEL"] = "beta-3b"
    state["QUEUE"].append("print(42)")
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", os.path.join(D, "d.py")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 6:
        ok = False
        details.append("code=" + str(p.returncode))
    exp_msg = "ANSWER REFUSED: model substituted: expected alpha-7b, answered by beta-3b"
    if exp_msg not in p.stdout:
        ok = False
        details.append("no refusal msg: " + p.stdout[:150])
    if os.path.exists(os.path.join(D, "d.py")):
        ok = False
        details.append("d.py exists")
    if len(state["BODIES"]) != 1:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    try:
        jl = last_journal()
        if jl["model_answered"] != "beta-3b":
            ok = False
            details.append("model=" + str(jl["model_answered"]))
    except Exception as ex:
        ok = False
        details.append("journal error: " + str(ex))
    results.append(("test4a", ok, "code=6 model substituted d.py absent", "; ".join(details) if details else "ok"))

    # --- Test 4b ---
    reset()
    state["QUEUE"].append("print(42)")
    cmd = base_cmd + ["--file", os.path.join(D, "bad.md"), "--role", "code", "--brief-waiver", "known gap"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 0:
        ok = False
        details.append("code=" + str(p.returncode))
    if len(state["BODIES"]) != 1:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    try:
        jl = last_journal()
        if jl.get("waiver") != "brief: known gap":
            ok = False
            details.append("waiver=" + str(jl.get("waiver")))
    except Exception as ex:
        ok = False
        details.append("journal error: " + str(ex))
    results.append(("test4b", ok, "code=0 waiver=brief: known gap", "; ".join(details) if details else "ok"))

    # --- Test 5 ---
    n_lines = journal_line_count()

    # 5a
    reset()
    cmd = base_cmd + ["--file", os.path.join(D, "bad.md"), "--role", "code", "--out", os.path.join(D, "e.py")]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 7:
        ok = False
        details.append("code=" + str(p.returncode))
    if "REFUSED N1 - no nature" not in p.stdout:
        ok = False
        details.append("no REFUSED N1")
    if "  To fix: write nature:" not in p.stdout:
        ok = False
        details.append("no To fix line")
    if "BRIEF REFUSED: nothing sent" not in p.stdout:
        ok = False
        details.append("no BRIEF REFUSED")
    if len(state["BODIES"]) != 0:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    if os.path.exists(os.path.join(D, "e.py")):
        ok = False
        details.append("e.py exists")
    if journal_line_count() != n_lines:
        ok = False
        details.append("journal lines changed: " + str(n_lines) + "->" + str(journal_line_count()))
    results.append(("test5a", ok, "code=7 brief refused 0 bodies no e.py journal stable", "; ".join(details) if details else "ok"))

    # 5b
    reset()
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", os.path.join(D, "e.py"), "--verify", "python3 -m py_compile x.py"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 3:
        ok = False
        details.append("code=" + str(p.returncode))
    if "VERIFY WEAK: compile only" not in p.stdout:
        ok = False
        details.append("no VERIFY WEAK: " + p.stdout[:150])
    if len(state["BODIES"]) != 0:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    results.append(("test5b", ok, "code=3 VERIFY WEAK 0 bodies", "; ".join(details) if details else "ok"))

    # 5c
    reset()
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "far", "--trust", "untrusted_third_party"]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 4:
        ok = False
        details.append("code=" + str(p.returncode))
    if "NO RULES: anonymization.json missing or invalid" not in p.stdout:
        ok = False
        details.append("no NO RULES: " + p.stdout[:150])
    if len(state["BODIES"]) != 0:
        ok = False
        details.append("bodies=" + str(len(state["BODIES"])))
    results.append(("test5c", ok, "code=4 NO RULES 0 bodies", "; ".join(details) if details else "ok"))

    # 5d
    reset()
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--verify", CHECK]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 2:
        ok = False
        details.append("code=" + str(p.returncode))
    if "VERIFY NEEDS --out" not in p.stdout:
        ok = False
        details.append("no VERIFY NEEDS: " + p.stdout[:150])
    results.append(("test5d", ok, "code=2 VERIFY NEEDS --out", "; ".join(details) if details else "ok"))

    # --- Test 6 ---
    reset()
    sentinel_dir = tempfile.mkdtemp()
    sentinel = os.path.join(sentinel_dir, "sentinel.py")
    with open(sentinel, "w", encoding="utf-8") as f:
        f.write("SENTINEL\n")
    out6 = os.path.join(D, "f.py")
    cand6 = answer_rules.candidate_path(out6)
    os.symlink(sentinel, cand6)
    state["QUEUE"].append("print(42)")
    cmd = base_cmd + ["--file", os.path.join(D, "task.md"), "--role", "code", "--out", out6, "--verify", CHECK]
    p = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
    ok = True
    details = []
    if p.returncode != 0:
        ok = False
        details.append("code=" + str(p.returncode))
    try:
        with open(sentinel, "r", encoding="utf-8") as f:
            if f.read() != "SENTINEL\n":
                ok = False
                details.append("sentinel modified")
    except OSError:
        ok = False
        details.append("sentinel missing")
    if os.path.islink(out6):
        ok = False
        details.append("f.py is a symlink")
    try:
        with open(out6, "r", encoding="utf-8") as f:
            if f.read() != "print(42)\n":
                ok = False
                details.append("f.py=" + repr(f.read()))
    except OSError:
        ok = False
        details.append("f.py missing")
    shutil.rmtree(sentinel_dir, ignore_errors=True)
    results.append(("test6", ok, "code=0 sentinel intact f.py=print(42) not a symlink", "; ".join(details) if details else "ok"))

    server.shutdown()
    srv_thread.join(timeout=5)
    shutil.rmtree(D)

    all_pass = True
    for name, passed, expected, actual in results:
        if passed:
            print("PASS " + name + ": " + expected)
        else:
            print("FAIL " + name + ": expected " + expected + ", got " + actual)
            all_pass = False

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    # every refusal is logged, or the tools never learn from them.
    import exit_log
    exit_log.run(main, "delegate", sys.argv[1:])
