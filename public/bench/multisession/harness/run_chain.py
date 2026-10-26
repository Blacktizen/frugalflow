import argparse
import hashlib
import json
import os
import shutil
import signal
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
DEFAULT_W = os.path.join(os.getcwd(), "work")
W = os.environ.get("BENCH_MS_W") or DEFAULT_W
H = HERE
EXO = W + "/exo"
RUNS = W + "/runs"
FF_ROOT = os.environ.get("BENCH_MS_FF") or os.path.abspath(os.path.join(HERE, "..", "..", "..", ".."))
FFBIN = FF_ROOT + "/public/bin"
FFMAIN = FFBIN + "/frugalflow.py"
RESUME = FF_ROOT + "/public/bench/memory/resume_note.py"
PYTEST_PY = "python3"
MAXTURNS = 80
WALL = 1800
AGENT = os.environ.get("RUNCHAIN_AGENT") or "claude"


def make_paths(w, agent, h=None):
    return {
        "W": w,
        "H": h or HERE,
        "EXO": w + "/exo",
        "RUNS": w + "/runs",
        "FFBIN": FFBIN,
        "FFMAIN": FFMAIN,
        "RESUME": RESUME,
        "AGENT": agent,
    }


def module_of(slug):
    return slug.replace("-", "_")


def read_text(path):
    with open(path, encoding="utf-8") as handle:
        return handle.read()


def write_text(path, content):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def read_json(path, default):
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return default


def write_json(path, obj):
    write_text(path, json.dumps(obj, sort_keys=True, indent=1) + "\n")


def run_json(cmd):
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except ValueError:
        return {}


def snapshot(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    if os.path.isdir(src):
        shutil.copytree(src, dst)


def restore(src, dst):
    if os.path.isdir(dst):
        shutil.rmtree(dst)
    shutil.copytree(src, dst)


def has_assistant(path):
    try:
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and obj.get("type") == "assistant":
                    return True
    except OSError:
        pass
    return False


def setup_chain(P, cond, chain_dir, proj):
    if not os.path.isdir(proj):
        if cond == "B":
            env = dict(os.environ)
            env["FRUGALFLOW_HOME"] = os.path.join(chain_dir, "ffhome")
            proc = subprocess.run(
                [PYTEST_PY, P["FFMAIN"], "new-project", "proj", "--root", chain_dir],
                env=env,
            )
            if proc.returncode != 0:
                print("erreur: new-project a echoue (code %d)" % proc.returncode)
                return 1
        os.makedirs(proj, exist_ok=True)
        write_text(os.path.join(proj, "README.md"), "Projet kata : un module Python par exercice.\n")
        os.makedirs(os.path.join(proj, "kata"), exist_ok=True)
        write_text(os.path.join(proj, "kata", "__init__.py"), "")
        os.makedirs(os.path.join(proj, "tests"), exist_ok=True)
        os.makedirs(os.path.join(proj, "docs"), exist_ok=True)
    hashes_path = os.path.join(chain_dir, "hashes.json")
    if not os.path.exists(hashes_path):
        write_json(hashes_path, {})
    return 0


def deliver(P, chain_dir, proj, slugs):
    hashes = read_json(os.path.join(chain_dir, "hashes.json"), {})
    for slug in slugs:
        module = module_of(slug)
        shutil.copyfile(
            os.path.join(P["EXO"], slug, "stub.py"),
            os.path.join(proj, "kata", module + ".py"),
        )
        shutil.copyfile(
            os.path.join(P["EXO"], slug, "test.py"),
            os.path.join(proj, "tests", "test_" + module + ".py"),
        )
        shutil.copyfile(
            os.path.join(P["EXO"], slug, "doc.md"),
            os.path.join(proj, "docs", slug + ".md"),
        )
        rel = "tests/test_" + module + ".py"
        with open(os.path.join(proj, rel), "rb") as handle:
            hashes[rel] = hashlib.sha256(handle.read()).hexdigest()
    write_json(os.path.join(chain_dir, "hashes.json"), hashes)


def build_prompt(P, cond, chain_dir, proj, k, slugs):
    lines = ["NATURE: creation", "PRODUIT: controle", "EPREUVES: 5", ""]
    if cond == "B" and k >= 2:
        lines.append("## Resume de la session precedente")
        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = os.path.join(chain_dir, "ffhome")
        proc = subprocess.run(
            [PYTEST_PY, P["RESUME"], "--vault", os.path.join(proj, "vault")],
            env=env,
            capture_output=True,
            text=True,
        )
        lines.append((proc.stdout or "").rstrip("\n"))
        lines.append("")
    tpl_name = "s1.md" if k == 1 else "sk.md"
    tpl = read_text(os.path.join(P["H"], "tpl", tpl_name))
    exercises = "\n".join("- %s : %s" % (s, module_of(s)) for s in slugs)
    tpl = tpl.replace("{EXERCISES}", exercises).replace("{K}", str(k))
    lines.append(tpl)
    if cond == "B":
        lines.append("")
        b_block = read_text(os.path.join(P["H"], "tpl", "b_block.md"))
        lines.append(b_block.replace("{BIN}", P["FFBIN"]))
    write_text(os.path.join(chain_dir, "prompt_%d.md" % k), "\n".join(lines))


def run_agent(P, cond, chain_dir, proj, k):
    env = dict(os.environ)
    if cond == "B":
        env["FRUGALFLOW_HOME"] = os.path.join(chain_dir, "ffhome")
    keep_awake = ["caffeinate", "-i"] if shutil.which("caffeinate") else []
    cmd = keep_awake + [
        P["AGENT"],
        "-p",
        "--permission-mode",
        "bypassPermissions",
        "--output-format",
        "stream-json",
        "--verbose",
        "--max-turns",
        str(MAXTURNS),
    ]
    t0 = time.time()
    killed = False
    with open(os.path.join(chain_dir, "prompt_%d.md" % k), "rb") as fin, \
            open(os.path.join(chain_dir, "stream_%d.jsonl" % k), "wb") as fout, \
            open(os.path.join(chain_dir, "stderr_%d.txt" % k), "wb") as ferr:
        proc = subprocess.Popen(
            cmd,
            cwd=proj,
            stdin=fin,
            stdout=fout,
            stderr=ferr,
            env=env,
            start_new_session=True,
        )
        try:
            proc.wait(timeout=WALL)
        except subprocess.TimeoutExpired:
            killed = True
            try:
                os.killpg(os.getpgid(proc.pid), signal.SIGKILL)
            except OSError:
                pass
            proc.wait()
    return time.time() - t0, killed


def count_ok(tests_out, modules):
    n = 0
    if isinstance(tests_out, dict):
        for module in modules:
            entry = tests_out.get(module)
            if isinstance(entry, dict) and entry.get("ok") is True:
                n += 1
    return n


def run_session(P, cond, chain_id, chain_dir, proj, k, slugs, all_slugs, results_path):
    modules = [module_of(s) for s in slugs]
    all_modules = [module_of(s) for s in all_slugs]
    proj_snap = os.path.join(chain_dir, "proj_avant_k")
    ffhome = os.path.join(chain_dir, "ffhome")
    ffhome_snap = os.path.join(chain_dir, "ffhome_avant_k")
    snapshot(proj, proj_snap)
    if cond == "B":
        snapshot(ffhome, ffhome_snap)
    attempt = 1
    while True:
        deliver(P, chain_dir, proj, slugs)
        build_prompt(P, cond, chain_dir, proj, k, slugs)
        wall, killed = run_agent(P, cond, chain_dir, proj, k)
        stream_path = os.path.join(chain_dir, "stream_%d.jsonl" % k)
        measure = os.path.join(P["H"], "measure.py")
        tokens = run_json([PYTEST_PY, "-I", measure, "tokens", stream_path])
        tests_session = run_json([PYTEST_PY, "-I", measure, "tests", proj, ",".join(modules)])
        tests_cum = run_json([PYTEST_PY, "-I", measure, "tests", proj, ",".join(all_modules)])
        slugs_map = {module_of(s): s for s in all_slugs}
        slugs_path = os.path.join(chain_dir, "slugs.json")
        write_json(slugs_path, slugs_map)
        rules = run_json([
            PYTEST_PY,
            "-I",
            os.path.join(P["H"], "check_rules.py"),
            proj,
            "--hashes",
            os.path.join(chain_dir, "hashes.json"),
            "--slugs-json",
            slugs_path,
        ])
        infra = (
            not isinstance(tokens, dict)
            or tokens.get("total", 0) == 0
            or not has_assistant(stream_path)
        )
        if infra and attempt == 1:
            time.sleep(60)
            restore(proj_snap, proj)
            if cond == "B":
                restore(ffhome_snap, ffhome)
            attempt = 2
            continue
        break
    solved_session = count_ok(tests_session, modules)
    solved_cum = count_ok(tests_cum, all_modules)
    result = {
        "chain": chain_id,
        "cond": cond,
        "k": k,
        "slugs": slugs,
        "wall_s": int(round(wall)),
        "killed": killed,
        "infra": infra,
        "attempt": attempt,
        "tokens": tokens,
        "tests_session": tests_session,
        "tests_cum": tests_cum,
        "solved_session": solved_session,
        "solved_cum": solved_cum,
        "rules": rules,
    }
    with open(results_path, "a", encoding="utf-8") as handle:
        handle.write(json.dumps(result, sort_keys=True) + "\n")
    tokens_total = tokens.get("total", 0) if isinstance(tokens, dict) else 0
    rules_modules = rules.get("modules", {}) if isinstance(rules, dict) else {}
    rules_summary = rules.get("summary", {}) if isinstance(rules, dict) else {}
    print(
        "%s %d solved=%d/%d cum=%d/%d tokens=%d wall=%ds killed=%s conformes=%d/%d"
        % (
            chain_id,
            k,
            solved_session,
            len(modules),
            solved_cum,
            len(all_modules),
            tokens_total,
            int(round(wall)),
            killed,
            rules_summary.get("conformes", 0),
            len(rules_modules),
        )
    )
    shutil.rmtree(proj_snap, ignore_errors=True)
    shutil.rmtree(ffhome_snap, ignore_errors=True)
    if infra:
        return 3
    return 0


def run_chain(P, cond, chain_id, plan_key):
    plan = read_json(os.path.join(P["H"], "plan.json"), None)
    if not isinstance(plan, dict) or plan_key not in plan:
        print("erreur: plan %s introuvable dans %s" % (plan_key, os.path.join(P["H"], "plan.json")))
        return 1
    sessions = plan[plan_key]
    chain_dir = os.path.join(P["RUNS"], chain_id)
    proj = os.path.join(chain_dir, "proj")
    os.makedirs(chain_dir, exist_ok=True)
    if setup_chain(P, cond, chain_dir, proj) != 0:
        return 1
    results_path = os.path.join(chain_dir, "results.jsonl")
    done = set()
    if os.path.isfile(results_path):
        with open(results_path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                if isinstance(obj, dict) and isinstance(obj.get("k"), int):
                    done.add(obj["k"])
    all_slugs = []
    for k, slugs in enumerate(sessions, 1):
        all_slugs = all_slugs + list(slugs)
        if k in done:
            continue
        code = run_session(P, cond, chain_id, chain_dir, proj, k, list(slugs), all_slugs, results_path)
        if code != 0:
            return code
    return 0


FAKE_AGENT_SH = """#!/bin/sh
PROMPT=$(cat)
printf '%s\\n' '{"type":"assistant","message":{"id":"m1","usage":{"input_tokens":10,"output_tokens":5}}}'
printf '%s\\n' '{"type":"result","usage":{"input_tokens":10,"output_tokens":5},"num_turns":1}'
q='\"\"\"'
printf '%s\\n' "$PROMPT" | grep -E '^- [a-z0-9-]+ : [a-z_]+$' | while IFS= read -r line; do
  slug=$(printf '%s' "$line" | sed -E 's/^- ([a-z0-9-]+) : .*/\\1/')
  mod=$(printf '%s' "$line" | sed -E 's/.* : //')
  mkdir -p kata
  printf '%sKata: %s%s\\n\\n\\ndef solve(x: int) -> int:\\n    return x\\n' "$q" "$slug" "$q" > "kata/$mod.py"
done
exit 0
"""

FALLBACK_MEASURE = """import json
import os
import sys

def main():
    if sys.argv[1] == "tokens":
        total_in = 0
        total_out = 0
        with open(sys.argv[2], encoding="utf-8") as handle:
            for raw in handle:
                try:
                    obj = json.loads(raw)
                except ValueError:
                    continue
                usage = obj.get("usage") or (obj.get("message") or {}).get("usage") or {}
                total_in += usage.get("input_tokens", 0)
                total_out += usage.get("output_tokens", 0)
        print(json.dumps({"input": total_in, "output": total_out, "total": total_in + total_out}))
    else:
        project = sys.argv[2]
        out = {}
        for module in sys.argv[3].split(","):
            if not module:
                continue
            ok = os.path.isfile(os.path.join(project, "kata", module + ".py"))
            out[module] = {"passed": 1 if ok else 0, "failed": 0, "total": 1 if ok else 0, "ok": ok}
        print(json.dumps(out))

main()
"""

FALLBACK_RULES = """import json

print(json.dumps({"modules": {}, "summary": {"conformes": 0, "delivered": 0}}))
"""

FALLBACK_TPL = {
    "s1.md": "## Session 1 du projet kata\n{EXERCISES}\n",
    "sk.md": "## Session {K} du projet kata\n{EXERCISES}\n",
    "b_block.md": "journal_add {BIN}\n",
}


def fake_test(slug):
    module = module_of(slug)
    return (
        "import os\n"
        "import sys\n"
        "\n"
        "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
        "\n"
        "from kata." + module + " import solve\n"
        "\n"
        "\n"
        "def test_" + module + "():\n"
        "    assert solve(2) == 2\n"
    )


def run_quiet(P, cond, chain_id, plan_key):
    saved = sys.stdout
    sys.stdout = open(os.devnull, "w")
    try:
        return run_chain(P, cond, chain_id, plan_key)
    finally:
        sys.stdout.close()
        sys.stdout = saved


def read_results(path):
    lines = []
    if os.path.isfile(path):
        with open(path, encoding="utf-8") as handle:
            for raw in handle:
                raw = raw.strip()
                if raw:
                    lines.append(raw)
    return lines


def autotest():
    base = tempfile.mkdtemp(prefix="run_chain_autotest_")
    epreuves = []
    try:
        w = os.path.join(base, "w")
        harness = os.path.join(w, "harness")
        os.makedirs(os.path.join(harness, "tpl"))
        real_harness = HERE
        for name in ("measure.py", "check_rules.py"):
            src = os.path.join(real_harness, name)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(harness, name))
            elif name == "measure.py":
                write_text(os.path.join(harness, name), FALLBACK_MEASURE)
            else:
                write_text(os.path.join(harness, name), FALLBACK_RULES)
        for name in ("s1.md", "sk.md", "b_block.md"):
            src = os.path.join(real_harness, "tpl", name)
            if os.path.isfile(src):
                shutil.copyfile(src, os.path.join(harness, "tpl", name))
            else:
                write_text(os.path.join(harness, "tpl", name), FALLBACK_TPL[name])
        write_json(os.path.join(harness, "plan.json"), {"pilot": [["demo"]], "main": [["demo"], ["demo2"]]})
        for slug in ("demo", "demo2"):
            d = os.path.join(w, "exo", slug)
            os.makedirs(d)
            write_text(os.path.join(d, "stub.py"), "def solve(x):\n    raise NotImplementedError\n")
            write_text(os.path.join(d, "test.py"), fake_test(slug))
            write_text(os.path.join(d, "doc.md"), "Enonce factice pour " + slug + ".\n")
        agent_path = os.path.join(base, "fake_agent.sh")
        write_text(agent_path, FAKE_AGENT_SH)
        os.chmod(agent_path, 0o755)
        P = make_paths(w, agent_path, harness)

        code = run_quiet(P, "A", "t1", "pilot")
        res = read_results(os.path.join(P["RUNS"], "t1", "results.jsonl"))
        got_k = None
        got_total = None
        if len(res) == 1:
            try:
                obj = json.loads(res[0])
                got_k = obj.get("k")
                got_total = (obj.get("tokens") or {}).get("total")
            except ValueError:
                pass
        prompt1 = ""
        p1 = os.path.join(P["RUNS"], "t1", "prompt_1.md")
        if os.path.isfile(p1):
            prompt1 = read_text(p1)
        p1_lines = prompt1.splitlines()
        first_ok = bool(p1_lines) and p1_lines[0] == "NATURE: creation"
        line_ok = "- demo : demo" in p1_lines
        passed1 = code == 0 and got_k == 1 and got_total == 15 and first_ok and line_ok
        epreuves.append((
            "epreuve1_chaine_A",
            "exit=0 lignes=1 k=1 tokens.total=15 prompt commence par NATURE: creation et contient - demo : demo",
            "exit=%s lignes=%d k=%s total=%s premiere_ligne=%s ligne_exercice=%s"
            % (code, len(res), got_k, got_total, first_ok, line_ok),
            passed1,
        ))

        code2 = run_quiet(P, "A", "t1", "pilot")
        res2 = read_results(os.path.join(P["RUNS"], "t1", "results.jsonl"))
        passed2 = code2 == 0 and len(res2) == 1
        epreuves.append((
            "epreuve2_reprise",
            "exit=0 lignes=1 (session 1 non rejouee)",
            "exit=%s lignes=%d" % (code2, len(res2)),
            passed2,
        ))

        code3 = run_quiet(P, "A", "t3", "main")
        pr1 = ""
        pr2 = ""
        f1 = os.path.join(P["RUNS"], "t3", "prompt_1.md")
        f2 = os.path.join(P["RUNS"], "t3", "prompt_2.md")
        if os.path.isfile(f1):
            pr1 = read_text(f1)
        if os.path.isfile(f2):
            pr2 = read_text(f2)
        no_resume = "Resume" not in pr2
        no_journal_2 = "journal_add" not in pr2
        no_journal_1 = "journal_add" not in pr1
        passed3 = code3 == 0 and bool(pr2) and no_resume and no_journal_2 and no_journal_1
        epreuves.append((
            "epreuve3_condition_A_sans_resume_ni_journal",
            "exit=0 prompt_2 sans Resume ni journal_add, prompt_1 sans journal_add",
            "exit=%s resume=%s journal_2=%s journal_1=%s"
            % (code3, no_resume, no_journal_2, no_journal_1),
            passed3,
        ))
    finally:
        shutil.rmtree(base, ignore_errors=True)
    all_ok = True
    for name, expected, obtained, passed in epreuves:
        if not passed:
            all_ok = False
        print("%s %s attendu=%s obtenu=%s" % ("PASS" if passed else "FAIL", name, expected, obtained))
    return 0 if all_ok else 1


def main():
    parser = argparse.ArgumentParser(prog="run_chain.py")
    parser.add_argument("--cond", choices=["A", "B"])
    parser.add_argument("--chain")
    parser.add_argument("--plan", choices=["pilot", "main"])
    parser.add_argument("--autotest", action="store_true")
    args = parser.parse_args()
    if args.autotest:
        sys.exit(autotest())
    if not args.cond or not args.chain or not args.plan:
        parser.error("--cond, --chain et --plan sont requis (sauf avec --autotest)")
    P = make_paths(W, AGENT)
    sys.exit(run_chain(P, args.cond, args.chain, args.plan))


if __name__ == "__main__":
    main()
