#!/usr/bin/env python3
"""run_brief_bench.py - measures whether a brief that passed the brief checker
succeeds more often at the FIRST delegation attempt than a faulty brief sent
without the filter.

Commands:
    run_brief_bench.py run --tasks DIR --bin DIR --models MODELS_JSON --home DIR
        --role ROLE --out DIR [--reps 3] [--ids p01,p02] [--cond C0,C1]
        [--trust untrusted_third_party]
    run_brief_bench.py report --out DIR
    run_brief_bench.py --autotest

The `run` command sends each brief through bin/delegate.py without --verify
(first attempt only), records the verdict of bin/brief_check.py on the brief,
runs the task's check.py oracle on the produced file, and appends one JSON line
per execution to OUT/results.jsonl.  `report` turns that file into a Markdown
table with Wilson 95% intervals and a verdict.  `--autotest` runs five cases in
subprocesses against a tiny local OpenAI-compatible model server.
"""

import argparse
import http.server
import json
import math
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "..", "bin")

Z = 1.959963984540054  # 97.5th percentile of the standard normal distribution

WAIVER_TEXT = "bench: faulty brief sent on purpose"

# A brief that passes brief_check.py: it names the quantity, the filter, the
# tests, forbids accented byte literals and text after the code block, and gives
# the fixtures verbatim.
FIXED_BRIEF = '''NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1]. Each line of the file holds a name and a count, separated by a semicolon. There is no header line. The program prints the sum of the counts as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the sum of the count column, printed as one integer.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores nothing.
TESTS: 2
Copy verbatim the two fixtures below.

FORBIDDEN: reading any file other than the one given as argv[1].
The program code is pure ASCII.
Write nothing after the code block.

```
alice;3
bob;5
carol;7
```

```
x;10
y;20
```
'''

# The same task with the fixtures described instead of given verbatim: the
# brief checker refuses it.
FAULTY_BRIEF = '''NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1]. Each line of the file holds a name and a count. There is no header line. The program prints the sum of the counts as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the sum of the count column, printed as one integer.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores nothing.
TESTS: 2
The fixtures: a file with three rows (alice 3, bob 5, carol 7), and a second file with two rows (x 10, y 20).

FORBIDDEN: reading any file other than the one given as argv[1].
The program code is pure ASCII.
Write nothing after the code block.
'''

REFERENCE_PROG = "print('PASS')\n"
WRONG_PROG = "print('WRONG')\n"

CHECK_CODE = r'''import subprocess
import sys


def main():
    prog = sys.argv[1]
    r = subprocess.run([sys.executable, prog], capture_output=True, text=True, timeout=20)
    want = "PASS\n"
    if r.returncode == 0 and r.stdout == want:
        print("PASS oracle")
        sys.exit(0)
    print("FAIL oracle: got %r exit %d" % (r.stdout, r.returncode))
    sys.exit(1)


if __name__ == "__main__":
    main()
'''


def _write(path, content):
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def make_task(tasks_dir, tid, fixed_text, faulty_text, reference, check):
    d = os.path.join(tasks_dir, tid)
    os.makedirs(os.path.join(d, "reference"), exist_ok=True)
    _write(os.path.join(d, "brief_fixed.md"), fixed_text)
    _write(os.path.join(d, "brief_faulty.md"), faulty_text)
    _write(os.path.join(d, "reference", "prog.py"), reference)
    _write(os.path.join(d, "check.py"), check)


def write_models(path, port):
    doc = {
        "models": [
            {
                "id": "m",
                "name": "fake-model",
                "location": "remote",
                "endpoint": "http://127.0.0.1:%d/v1" % port,
                "context_window": 8192,
                "trust": "private",
                "key_env": "",
                "max_output": 1024,
            }
        ],
        "layers": [{"name": "work", "delegable": True}],
        "roles": [{"name": "code", "layer": "work", "model": "m"}],
    }
    _write(path, json.dumps(doc))


class _FakeHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0) or 0)
            raw = self.rfile.read(length)
            try:
                body = json.loads(raw.decode("utf-8"))
            except Exception:
                body = {}
            self.server.bodies.append(body)
            brief = ""
            for m in body.get("messages", []):
                if isinstance(m, dict) and m.get("role") == "user":
                    brief = m.get("content", "")
                    break
            content = self.server.fixed_answer if "Copy verbatim" in brief else self.server.wrong_answer
            resp = {
                "model": body.get("model") or "fake-model",
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 7, "completion_tokens": 3},
            }
            data = json.dumps(resp).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def start_fake_server(fixed_answer, wrong_answer):
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeHandler)
    server.fixed_answer = fixed_answer
    server.wrong_answer = wrong_answer
    server.bodies = []
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def dead_port():
    import socket
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def load_results(out_dir):
    path = os.path.join(out_dir, "results.jsonl")
    recs = []
    if not os.path.isfile(path):
        return recs
    with open(path, "r", encoding="utf-8") as f:
        for line in f.read().splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict):
                recs.append(obj)
    return recs


def _journal_raw_count(home):
    path = os.path.join(home, "delegations.jsonl")
    if not os.path.isfile(path):
        return 0
    with open(path, "r", encoding="utf-8") as f:
        return len([l for l in f.read().splitlines() if l.strip()])


def _last_journal_record(home):
    path = os.path.join(home, "delegations.jsonl")
    if not os.path.isfile(path):
        return None
    with open(path, "r", encoding="utf-8") as f:
        lines = [l for l in f.read().splitlines() if l.strip()]
    if not lines:
        return None
    try:
        return json.loads(lines[-1])
    except ValueError:
        return None


def _append(out_dir, rec):
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "results.jsonl"), "a", encoding="utf-8") as f:
        f.write(json.dumps(rec) + "\n")


def cmd_run(args):
    tasks_dir = os.path.abspath(args.tasks)
    bin_dir = os.path.abspath(args.bin)
    models = os.path.abspath(args.models)
    home = os.path.abspath(args.home)
    out_dir = os.path.abspath(args.out)
    role = args.role
    trust = args.trust
    reps = args.reps

    conds = [c.strip() for c in args.cond.split(",") if c.strip()]
    if not conds:
        conds = ["C0", "C1"]

    if args.ids:
        ids = [i.strip() for i in args.ids.split(",") if i.strip()]
    else:
        ids = sorted(
            name for name in os.listdir(tasks_dir)
            if os.path.isdir(os.path.join(tasks_dir, name))
            and os.path.isfile(os.path.join(tasks_dir, name, "brief_fixed.md"))
        )

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(home, exist_ok=True)

    delegate = os.path.join(bin_dir, "delegate.py")
    brief_check = os.path.join(bin_dir, "brief_check.py")

    done = set()
    for rec in load_results(out_dir):
        task = rec.get("task")
        cond = rec.get("cond")
        rep = rec.get("rep")
        if task is not None and cond is not None and rep is not None:
            done.add((task, cond, rep))

    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home

    for tid in ids:
        task_dir = os.path.join(tasks_dir, tid)
        for rep in range(1, reps + 1):
            for cond in conds:
                key = (tid, cond, rep)
                if key in done:
                    continue

                brief = os.path.join(
                    task_dir, "brief_fixed.md" if cond == "C1" else "brief_faulty.md"
                )

                brief_check_rc = None
                try:
                    bc = subprocess.run(
                        [sys.executable, brief_check, "--brief", brief, "--trust", trust],
                        capture_output=True, text=True, timeout=60,
                    )
                    brief_check_rc = bc.returncode
                except Exception:
                    brief_check_rc = None

                refused = (brief_check_rc == 5)

                if cond == "C1" and refused:
                    _append(out_dir, {
                        "task": tid,
                        "cond": cond,
                        "rep": rep,
                        "brief_check_rc": brief_check_rc,
                        "brief_refused": True,
                        "delegate_rc": None,
                        "produced": False,
                        "oracle_rc": None,
                        "success": False,
                        "secs": None,
                        "tokens_in": None,
                        "tokens_out": None,
                    })
                    continue

                out_file = os.path.join(out_dir, "cand", "%s_%s_r%d" % (tid, cond, rep), "prog.py")
                os.makedirs(os.path.dirname(out_file), exist_ok=True)

                cmd = [
                    sys.executable, delegate,
                    "--role", role,
                    "--file", brief,
                    "--models", models,
                    "--out", out_file,
                    "--trust", trust,
                ]
                if cond == "C0" and refused:
                    cmd += ["--brief-waiver", WAIVER_TEXT]

                n0 = _journal_raw_count(home)
                t0 = time.monotonic()
                delegate_rc = None
                produced = False
                secs = None
                try:
                    dr = subprocess.run(cmd, capture_output=True, text=True, timeout=3600, cwd=out_dir, env=env)
                    delegate_rc = dr.returncode
                    if dr.returncode:
                        sys.stderr.write("DELEGATE ERR: " + (dr.stdout + dr.stderr)[-400:] + "\n")
                    secs = round(time.monotonic() - t0, 3)
                except subprocess.TimeoutExpired:
                    delegate_rc = None
                    secs = round(time.monotonic() - t0, 3)
                except Exception:
                    delegate_rc = None
                    secs = round(time.monotonic() - t0, 3)

                produced = os.path.isfile(out_file)

                tokens_in = None
                tokens_out = None
                if _journal_raw_count(home) > n0:
                    rec = _last_journal_record(home)
                    if rec is not None:
                        tokens_in = rec.get("tokens_in")
                        tokens_out = rec.get("tokens_out")

                oracle_rc = None
                if produced:
                    check_py = os.path.join(task_dir, "check.py")
                    try:
                        oc = subprocess.run(
                            [sys.executable, check_py, out_file],
                            capture_output=True, text=True, timeout=20,
                        )
                        oracle_rc = oc.returncode
                    except subprocess.TimeoutExpired:
                        oracle_rc = None
                    except Exception:
                        oracle_rc = None

                _append(out_dir, {
                    "task": tid,
                    "cond": cond,
                    "rep": rep,
                    "brief_check_rc": brief_check_rc,
                    "brief_refused": False,
                    "delegate_rc": delegate_rc,
                    "produced": produced,
                    "oracle_rc": oracle_rc,
                    "success": bool(oracle_rc == 0),
                    "secs": secs,
                    "tokens_in": tokens_in,
                    "tokens_out": tokens_out,
                })

    return 0


def wilson(k, n):
    if n <= 0:
        return (None, None)
    p = k / n
    denom = 1 + Z * Z / n
    center = (p + Z * Z / (2 * n)) / denom
    half = Z * math.sqrt(p * (1 - p) / n + Z * Z / (4 * n * n)) / denom
    return (center - half, center + half)


def diff_ci(k1, n1, k0, n0):
    if n1 <= 0 or n0 <= 0:
        return (None, None)
    p1 = k1 / n1
    p0 = k0 / n0
    l1, u1 = wilson(k1, n1)
    l0, u0 = wilson(k0, n0)
    d = p1 - p0
    lower = d - math.sqrt((p1 - l1) ** 2 + (u0 - p0) ** 2)
    upper = d + math.sqrt((u1 - p1) ** 2 + (p0 - l0) ** 2)
    return (lower, upper)


def _pct(v, default="n/a"):
    if v is None:
        return default
    return "%.2f%%" % (max(0.0, min(1.0, v)) * 100.0)


def _pct_signed(v, default="n/a"):
    if v is None:
        return default
    return "%.2f%%" % (max(-1.0, min(1.0, v)) * 100.0)


def cmd_report(args):
    out_dir = os.path.abspath(args.out)
    recs = load_results(out_dir)

    def group(cond):
        return [r for r in recs if r.get("cond") == cond]

    c0 = group("C0")
    c1 = group("C1")

    n0 = len(c0)
    n1 = len(c1)
    k0 = sum(1 for r in c0 if r.get("success") is True)
    k1 = sum(1 for r in c1 if r.get("success") is True)

    lo0, hi0 = wilson(k0, n0)
    lo1, hi1 = wilson(k1, n1)
    r0 = k0 / n0 if n0 else None
    r1 = k1 / n1 if n1 else None

    dlo, dhi = diff_ci(k1, n1, k0, n0)
    diff_pts = (r1 - r0) * 100.0 if (r0 is not None and r1 is not None) else None

    lines = []
    lines.append("# brief bench report")
    lines.append("")
    lines.append("## Conditions")
    lines.append("")
    lines.append("| condition | executions | successes | success rate | Wilson 95% CI |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    lines.append("| C0 | %d | %d | %s | [%s, %s] |" % (n0, k0, _pct(r0), _pct(lo0), _pct(hi0)))
    lines.append("| C1 | %d | %d | %s | [%s, %s] |" % (n1, k1, _pct(r1), _pct(lo1), _pct(hi1)))
    lines.append("")
    lines.append("## Difference (C1 - C0)")
    lines.append("")
    if diff_pts is None or dlo is None or dhi is None:
        lines.append("n/a")
    else:
        lines.append("%+.2f points, 95%% CI [%s, %s]" % (diff_pts, _pct_signed(dlo), _pct_signed(dhi)))
    lines.append("")

    tasks = sorted(set(r.get("task") for r in recs if r.get("task")))
    lines.append("## Paired view per task")
    lines.append("")
    lines.append("| task | C0 successes | C0 reps | C1 successes | C1 reps |")
    lines.append("| --- | ---: | ---: | ---: | ---: |")
    for tid in tasks:
        tc0 = [r for r in c0 if r.get("task") == tid]
        tc1 = [r for r in c1 if r.get("task") == tid]
        lines.append("| %s | %d | %d | %d | %d |" % (
            tid,
            sum(1 for r in tc0 if r.get("success") is True), len(tc0),
            sum(1 for r in tc1 if r.get("success") is True), len(tc1),
        ))
    lines.append("")

    ref0 = sum(1 for r in c0 if r.get("brief_check_rc") == 5)
    ref1 = sum(1 for r in c1 if r.get("brief_check_rc") == 5)
    lines.append("## Briefs refused by brief_check")
    lines.append("")
    lines.append("| condition | refused |")
    lines.append("| --- | ---: |")
    lines.append("| C0 | %d |" % ref0)
    lines.append("| C1 | %d |" % ref1)
    lines.append("")

    if r0 is not None and r1 is not None:
        d = r1 - r0
        if d >= 0.20 and dlo is not None and dlo > 0:
            verdict = "UTILE PROUVE"
        elif r1 < r0:
            verdict = "NUISIBLE"
        else:
            verdict = "NON PROUVE"
    else:
        verdict = "NON PROUVE"
    lines.append("verdict: %s" % verdict)

    print("\n".join(lines))
    return 0


def _run_cli(args, timeout=300):
    return subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True, text=True, timeout=timeout,
    )


def _line(i, ok, expected, obtained):
    return "%s %d: expected %s, got %s" % ("PASS" if ok else "FAIL", i, expected, obtained)


def _recs_summary(recs):
    parts = []
    for r in recs:
        parts.append("%s/%s/r%s success=%s bc=%s dr=%s" % (
            r.get("task"), r.get("cond"), r.get("rep"),
            r.get("success"), r.get("brief_check_rc"), r.get("delegate_rc"),
        ))
    return " ".join(parts)


def case1():
    d = tempfile.mkdtemp(prefix="bb1_")
    try:
        tasks = os.path.join(d, "tasks")
        home = os.path.join(d, "home")
        out = os.path.join(d, "out")
        models = os.path.join(d, "models.json")
        make_task(tasks, "p01", FIXED_BRIEF, FAULTY_BRIEF, REFERENCE_PROG, CHECK_CODE)
        server, port = start_fake_server(REFERENCE_PROG, WRONG_PROG)
        write_models(models, port)
        r = _run_cli(["run", "--tasks", tasks, "--bin", BIN,
                      "--models", models, "--home", home, "--role", "code",
                      "--out", out, "--ids", "p01", "--reps", "1", "--cond", "C0,C1"])
        recs = load_results(out)
        c0 = next((x for x in recs if x.get("cond") == "C0"), None)
        c1 = next((x for x in recs if x.get("cond") == "C1"), None)
        ok = (
            r.returncode == 0
            and len(recs) == 2
            and c0 is not None and c1 is not None
            and c0["brief_check_rc"] == 5 and c0["delegate_rc"] == 0
            and c0["produced"] is True and c0["oracle_rc"] == 1 and c0["success"] is False
            and c1["brief_check_rc"] == 0 and c1["delegate_rc"] == 0
            and c1["produced"] is True and c1["oracle_rc"] == 0 and c1["success"] is True
            and c0["tokens_in"] == 7 and c0["tokens_out"] == 3
            and c1["tokens_in"] == 7 and c1["tokens_out"] == 3
        )
        server.shutdown()
        print(_line(1, ok, "C0 fails and C1 succeeds with tokens recorded", _recs_summary(recs)))
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def case2():
    d = tempfile.mkdtemp(prefix="bb2_")
    try:
        tasks = os.path.join(d, "tasks")
        home = os.path.join(d, "home")
        out = os.path.join(d, "out")
        models = os.path.join(d, "models.json")
        make_task(tasks, "p01", FAULTY_BRIEF, FAULTY_BRIEF, REFERENCE_PROG, CHECK_CODE)
        server, port = start_fake_server(REFERENCE_PROG, WRONG_PROG)
        write_models(models, port)
        r = _run_cli(["run", "--tasks", tasks, "--bin", BIN,
                      "--models", models, "--home", home, "--role", "code",
                      "--out", out, "--ids", "p01", "--reps", "1", "--cond", "C1"])
        recs = load_results(out)
        rec = recs[0] if recs else None
        ok = (
            r.returncode == 0
            and len(recs) == 1
            and rec is not None
            and rec["brief_check_rc"] == 5 and rec["brief_refused"] is True
            and rec["delegate_rc"] is None and rec["produced"] is False
            and rec["oracle_rc"] is None and rec["success"] is False
            and len(server.bodies) == 0
        )
        server.shutdown()
        print(_line(2, ok, "C1 refused brief recorded brief_refused and failed without a send",
                    _recs_summary(recs)))
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def case3():
    d = tempfile.mkdtemp(prefix="bb3_")
    try:
        tasks = os.path.join(d, "tasks")
        home = os.path.join(d, "home")
        out = os.path.join(d, "out")
        models = os.path.join(d, "models.json")
        make_task(tasks, "p01", FIXED_BRIEF, FAULTY_BRIEF, REFERENCE_PROG, CHECK_CODE)
        server, port = start_fake_server(REFERENCE_PROG, WRONG_PROG)
        write_models(models, port)
        argv = ["run", "--tasks", tasks, "--bin", BIN,
                "--models", models, "--home", home, "--role", "code",
                "--out", out, "--ids", "p01", "--reps", "2", "--cond", "C0,C1"]
        r1 = _run_cli(argv)
        hits1 = len(server.bodies)
        r2 = _run_cli(argv)
        hits2 = len(server.bodies)
        recs = load_results(out)
        ok = (
            r1.returncode == 0 and r2.returncode == 0
            and len(recs) == 4 and hits1 == 4 and hits2 == 4
        )
        server.shutdown()
        print(_line(3, ok, "resume skips the 4 done triples", "recs=%d hits=%d->%d" % (len(recs), hits1, hits2)))
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def case4():
    d = tempfile.mkdtemp(prefix="bb4_")
    try:
        out = os.path.join(d, "out")
        os.makedirs(out)
        base = {"brief_check_rc": 5, "brief_refused": False, "delegate_rc": 0,
                "produced": True, "oracle_rc": 1, "secs": 0.1, "tokens_in": 7, "tokens_out": 3}
        recs = []
        for rep in (1, 2):
            recs.append(dict(base, task="p01", cond="C0", rep=rep, success=False))
        for rep in (1, 2):
            recs.append(dict(base, task="p01", cond="C1", rep=rep,
                             brief_check_rc=0, oracle_rc=0, success=True))
        with open(os.path.join(out, "results.jsonl"), "w", encoding="utf-8") as f:
            for rec in recs:
                f.write(json.dumps(rec) + "\n")
        r = _run_cli(["report", "--out", out])
        text = r.stdout
        lines = text.splitlines()
        c0_row = next((ln for ln in lines if ln.startswith("| C0 |")), "")
        c1_row = next((ln for ln in lines if ln.startswith("| C1 |")), "")
        ok = (
            r.returncode == 0
            and "0.00%" in c0_row and "100.00%" in c1_row
            and "+100.00 points" in text
            and "verdict: UTILE PROUVE" in text
        )
        print(_line(4, ok, "report rates 0.00%/100.00%, diff +100.00 points, verdict UTILE PROUVE",
                    text.replace("\n", " ")[:160]))
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


def case5():
    d = tempfile.mkdtemp(prefix="bb5_")
    try:
        tasks = os.path.join(d, "tasks")
        home = os.path.join(d, "home")
        out = os.path.join(d, "out")
        models = os.path.join(d, "models.json")
        make_task(tasks, "p01", FIXED_BRIEF, FAULTY_BRIEF, REFERENCE_PROG, CHECK_CODE)
        write_models(models, dead_port())
        r = _run_cli(["run", "--tasks", tasks, "--bin", BIN,
                      "--models", models, "--home", home, "--role", "code",
                      "--out", out, "--ids", "p01", "--reps", "1", "--cond", "C1"])
        recs = load_results(out)
        rec = recs[0] if recs else None
        ok = (
            r.returncode == 0
            and len(recs) == 1
            and rec is not None
            and rec["delegate_rc"] is not None and rec["delegate_rc"] != 0
            and rec["produced"] is False and rec["success"] is False
            and rec["oracle_rc"] is None
        )
        print(_line(5, ok, "delegate failure recorded as a failure without a crash",
                    _recs_summary(recs)))
        return 0 if ok else 1
    finally:
        shutil.rmtree(d, ignore_errors=True)


CASES = {1: case1, 2: case2, 3: case3, 4: case4, 5: case5}


def run_case(i):
    try:
        return CASES[i]()
    except Exception as e:
        print(_line(i, False, "the case to run to completion", "%s: %s" % (type(e).__name__, e)))
        return 1


def autotest():
    script = os.path.abspath(__file__)
    failures = 0
    for i in range(1, 6):
        try:
            p = subprocess.run([sys.executable, script, "--case", str(i)],
                               capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            print("FAIL %d: expected a PASS/FAIL line, got timeout" % i)
            failures += 1
            continue
        out = p.stdout.strip()
        if out:
            print(out)
        else:
            print("FAIL %d: expected a PASS/FAIL line, got empty stdout" % i)
            failures += 1
        if p.returncode != 0:
            failures += 1
    return 1 if failures else 0


def parse_args(argv):
    parser = argparse.ArgumentParser(
        prog="run_brief_bench.py",
        description="Bench whether a brief that passed the brief checker wins more often on the first attempt.",
    )
    parser.add_argument("--autotest", action="store_true", help="run the five-case self-test")
    parser.add_argument("--case", type=int, default=None, help=argparse.SUPPRESS)
    sub = parser.add_subparsers(dest="command")

    run_p = sub.add_parser("run", help="run the bench and append results.jsonl")
    run_p.add_argument("--tasks", required=True)
    run_p.add_argument("--bin", required=True)
    run_p.add_argument("--models", required=True)
    run_p.add_argument("--home", required=True)
    run_p.add_argument("--role", required=True)
    run_p.add_argument("--out", required=True)
    run_p.add_argument("--reps", type=int, default=3)
    run_p.add_argument("--ids", default=None)
    run_p.add_argument("--cond", default="C0,C1")
    run_p.add_argument("--trust", default="private")

    report_p = sub.add_parser("report", help="render a Markdown report from results.jsonl")
    report_p.add_argument("--out", required=True)

    return parser.parse_args(argv)


def main(argv):
    args = parse_args(argv)
    if args.case is not None:
        return run_case(args.case)
    if args.autotest:
        return autotest()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "report":
        return cmd_report(args)
    sys.stderr.write("usage: run_brief_bench.py run ... | report --out DIR | --autotest\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
