import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile


def build_initial_prompt(task_dir, target):
    parts = []
    with open(os.path.join(task_dir, "task.md"), "r") as f:
        parts.append(f.read())

    setup_dir = os.path.join(task_dir, "setup")
    files = []
    if os.path.isdir(setup_dir):
        for entry in sorted(os.listdir(setup_dir)):
            full = os.path.join(setup_dir, entry)
            if os.path.isdir(full):
                continue
            if entry.startswith("."):
                continue
            files.append(entry)

    lines = ["Current files in the folder (name, then content):"]
    for fname in files:
        with open(os.path.join(setup_dir, fname), "r") as f:
            content = f.read()
        lines.append("=== " + fname + " ===")
        lines.append(content)
    parts.append("\n".join(lines))

    instruction = (
        "Reply with the full new content of `" + target + "` in ONE python code block. "
        "After the code block write one last line, exactly `TESTS: GREEN` if you are "
        "confident the automatic checker will pass, or `TESTS: RED` if not. No other text."
    )
    parts.append(instruction)
    return "\n\n".join(parts)


def build_retry_prompt(initial_prompt, prev_code, rc, checker_output):
    if prev_code is not None:
        body = (
            "Your previous attempt:\n"
            "```python\n" + prev_code + "\n```\n"
            "The checker said (exit code " + str(rc) + "):\n" +
            checker_output[-1500:] + "\n"
            "Fix it. Same reply format."
        )
    else:
        body = (
            "Your previous attempt:\n"
            "none\n"
            "The checker said (exit code 1):\n"
            "no code block found\n"
            "Fix it. Same reply format."
        )
    return initial_prompt + "\n\n" + body


def call_model(prompt, models_path, effort, no_thinking, frugalflow_home, bin_dir):
    prompt_file = tempfile.NamedTemporaryFile(
        mode="w", suffix=".txt", delete=False
    )
    prompt_file.write(prompt)
    prompt_file.close()
    try:
        cmd = [
            sys.executable,
            os.path.join(bin_dir, "delegate.py"),
            "--role", "documents",
            "--file", prompt_file.name,
            "--models", models_path,
            "--effort", effort,
            "--brief-waiver", "bench prompt, not a code brief",
        ]
        if no_thinking:
            cmd.append("--no-thinking")
        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = frugalflow_home
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=600, env=env
            )
            if result.returncode != 0:
                return "", result.returncode
            return result.stdout, result.returncode
        except subprocess.TimeoutExpired:
            return "", -1
    finally:
        try:
            os.unlink(prompt_file.name)
        except OSError:
            pass


def extract_code(stdout_text):
    if not stdout_text:
        return None
    m = re.search(r"^```[^\n]*\n(.*?)^```", stdout_text, re.MULTILINE | re.DOTALL)
    if m:
        return m.group(1)
    return None


def extract_announce(stdout_text):
    if not stdout_text:
        return "NONE"
    for line in reversed(stdout_text.split("\n")):
        stripped = line.strip()
        if stripped:
            m = re.match(r"^TESTS: (GREEN|RED)$", stripped)
            if m:
                return m.group(1)
            return "NONE"
    return "NONE"


def read_tokens(frugalflow_home):
    path = os.path.join(frugalflow_home, "delegations.jsonl")
    if not os.path.isfile(path):
        return 0, 0
    with open(path, "r") as f:
        lines = f.readlines()
    if not lines:
        return 0, 0
    try:
        obj = json.loads(lines[-1])
        return obj.get("tokens_in", 0), obj.get("tokens_out", 0)
    except (json.JSONDecodeError, IndexError):
        return 0, 0


def run_controller(task_dir, target, code):
    tmp = tempfile.mkdtemp()
    try:
        setup_dir = os.path.join(task_dir, "setup")
        if os.path.isdir(setup_dir):
            for entry in os.listdir(setup_dir):
                src = os.path.join(setup_dir, entry)
                if os.path.isfile(src) and not entry.startswith("."):
                    shutil.copy2(src, os.path.join(tmp, entry))
        with open(os.path.join(tmp, target), "w") as f:
            f.write(code)
        shutil.copy2(os.path.join(task_dir, "check.py"), os.path.join(tmp, "check.py"))
        try:
            result = subprocess.run(
                [sys.executable, "check.py"],
                cwd=tmp, capture_output=True, text=True, timeout=60
            )
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return 124, "timeout"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def get_target(task_dir):
    solution_dir = os.path.join(task_dir, "solution")
    for entry in os.listdir(solution_dir):
        if os.path.isfile(os.path.join(solution_dir, entry)):
            return entry
    raise RuntimeError("no solution file in " + solution_dir)


def cmd_run(args):
    tasks_dir = args.tasks
    ids = [x.strip() for x in args.ids.split(",") if x.strip()]
    reps = int(args.reps)
    bin_dir = args.bin
    models = args.models
    tries = args.tries
    effort = args.effort
    no_thinking = args.no_thinking

    if not os.path.isdir(tasks_dir):
        print("error: tasks directory not found: " + tasks_dir, file=sys.stderr)
        sys.exit(2)
    if not os.path.isdir(bin_dir):
        print("error: bin directory not found: " + bin_dir, file=sys.stderr)
        sys.exit(2)
    if not os.path.isfile(models):
        print("error: models file not found: " + models, file=sys.stderr)
        sys.exit(2)

    frugalflow_home = tempfile.mkdtemp()
    try:
        records = []
        for tid in ids:
            task_dir = os.path.join(tasks_dir, tid)
            if not os.path.isdir(task_dir):
                print("error: task not found: " + task_dir, file=sys.stderr)
                sys.exit(2)
            target = get_target(task_dir)
            initial_prompt = build_initial_prompt(task_dir, target)
            for rep in range(1, reps + 1):
                attempts = []
                prompt = initial_prompt
                prev_code = None
                prev_rc = 1
                prev_output = ""
                for attempt_idx in range(tries):
                    if attempt_idx > 0:
                        prompt = build_retry_prompt(initial_prompt, prev_code, prev_rc, prev_output)
                    stdout, exit_code = call_model(
                        prompt, models, effort, no_thinking, frugalflow_home, bin_dir
                    )
                    code = extract_code(stdout)
                    announce = extract_announce(stdout)
                    tokens_in, tokens_out = read_tokens(frugalflow_home)
                    if code is not None:
                        rc, checker_out = run_controller(task_dir, target, code)
                        oracle_pass = (rc == 0)
                    else:
                        rc, checker_out = 1, "no code block found"
                        oracle_pass = False
                    attempts.append({
                        "announce": announce,
                        "oracle_pass": oracle_pass,
                        "tokens_in": tokens_in,
                        "tokens_out": tokens_out,
                    })
                    if oracle_pass:
                        break
                    prev_code = code
                    prev_rc = rc
                    prev_output = checker_out
                records.append({"task": tid, "rep": rep, "attempts": attempts})
        with open(args.out, "w") as f:
            json.dump({"records": records}, f)
    finally:
        shutil.rmtree(frugalflow_home, ignore_errors=True)


def cmd_report(args):
    result_path = args.result
    if not os.path.isfile(result_path):
        print("error: result file not found: " + result_path, file=sys.stderr)
        sys.exit(2)
    with open(result_path, "r") as f:
        data = json.load(f)
    records = data.get("records", [])

    n = len(records)

    c0_green = 0
    c0_red = 0
    c0_none = 0
    c0_false_green = 0
    c0_passed = 0
    c0_tokens = 0
    for rec in records:
        att = rec["attempts"][0]
        ann = att["announce"]
        if ann == "GREEN":
            c0_green += 1
        elif ann == "RED":
            c0_red += 1
        else:
            c0_none += 1
        if ann == "GREEN" and not att["oracle_pass"]:
            c0_false_green += 1
        if att["oracle_pass"]:
            c0_passed += 1
        c0_tokens += att["tokens_in"] + att["tokens_out"]

    c1_resolved = 0
    c1_attempts = 0
    c1_tokens = 0
    for rec in records:
        resolved = False
        for att in rec["attempts"]:
            c1_attempts += 1
            c1_tokens += att["tokens_in"] + att["tokens_out"]
            if att["oracle_pass"]:
                resolved = True
        if resolved:
            c1_resolved += 1

    c1_unresolved = n - c1_resolved

    fg_pct = round(c0_false_green / c0_green * 100, 1) if c0_green > 0 else 0.0
    passed_pct = round(c0_passed / n * 100, 1) if n > 0 else 0.0
    resolved_pct = round(c1_resolved / n * 100, 1) if n > 0 else 0.0
    overhead_ratio = round(c1_tokens / c0_tokens, 2) if c0_tokens > 0 else 0.0
    tps_c0 = round(c0_tokens / c0_passed, 1) if c0_passed > 0 else None
    tps_c1 = round(c1_tokens / c1_resolved, 1) if c1_resolved > 0 else None

    by_task_map = {}
    for rec in records:
        t = rec["task"]
        if t not in by_task_map:
            by_task_map[t] = {"n": 0, "c0_passed": 0, "c0_false_green": 0, "c1_resolved": 0}
        by_task_map[t]["n"] += 1
        att0 = rec["attempts"][0]
        if att0["oracle_pass"]:
            by_task_map[t]["c0_passed"] += 1
        if att0["announce"] == "GREEN" and not att0["oracle_pass"]:
            by_task_map[t]["c0_false_green"] += 1
        if any(a["oracle_pass"] for a in rec["attempts"]):
            by_task_map[t]["c1_resolved"] += 1

    by_task = [
        {"task": k, "n": v["n"], "c0_passed": v["c0_passed"],
         "c0_false_green": v["c0_false_green"], "c1_resolved": v["c1_resolved"]}
        for k, v in sorted(by_task_map.items())
    ]

    output = {
        "C0": {
            "n": n,
            "announced_green": c0_green,
            "announced_red": c0_red,
            "announced_none": c0_none,
            "false_green": c0_false_green,
            "false_green_pct": fg_pct,
            "passed": c0_passed,
            "passed_pct": passed_pct,
            "tokens": c0_tokens,
        },
        "C1": {
            "n": n,
            "resolved": c1_resolved,
            "resolved_pct": resolved_pct,
            "unresolved": c1_unresolved,
            "attempts": c1_attempts,
            "tokens": c1_tokens,
        },
        "overhead_ratio": overhead_ratio,
        "tokens_per_solved_c0": tps_c0,
        "tokens_per_solved_c1": tps_c1,
        "by_task": by_task,
    }
    print(json.dumps(output, indent=2))


def cmd_autotest():
    self_path = os.path.abspath(sys.argv[0])
    all_pass = True
    results = []

    tmp_base = tempfile.mkdtemp()
    bin_dir = os.path.join(tmp_base, "bin")
    tasks_dir = os.path.join(tmp_base, "tasks")
    os.makedirs(bin_dir)

    with open(os.path.join(bin_dir, "delegate.py"), "w") as f:
        f.write(
            "import json\nimport os\nimport sys\n\n"
            "t = open(sys.argv[sys.argv.index(\"--file\") + 1]).read()\n"
            "home = os.environ[\"FRUGALFLOW_HOME\"]\n"
            "with open(os.path.join(home, \"delegations.jsonl\"), \"a\") as g:\n"
            "    g.write(json.dumps({\"tokens_in\": 10, \"tokens_out\": 20}) + \"\\n\")\n"
            "retry = \"checker said\" in t\n"
            "if \"TASK_A\" in t:\n"
            "    v, tag = (\"1\", \"GREEN\") if retry else (\"5\", \"GREEN\")\n"
            "elif \"TASK_B\" in t:\n"
            "    v, tag = \"2\", \"GREEN\"\n"
            "elif \"TASK_C\" in t:\n"
            "    v, tag = (\"3\", \"GREEN\") if retry else (\"0\", \"RED\")\n"
            "else:\n"
            "    print(\"I cannot do this.\")\n"
            "    sys.exit(0)\n"
            "print(\"```python\\ndef f():\\n    return \" + v + \"\\n```\\nTESTS: \" + tag)\n"
        )

    task_defs = {
        "tA": ("TASK_A make f return 1", 1),
        "tB": ("TASK_B make f return 2", 2),
        "tC": ("TASK_C make f return 3", 3),
        "tD": ("TASK_D make f return 4", 4),
    }
    for tid, (desc, nval) in task_defs.items():
        tdir = os.path.join(tasks_dir, tid)
        os.makedirs(os.path.join(tdir, "setup"))
        os.makedirs(os.path.join(tdir, "solution"))
        with open(os.path.join(tdir, "task.md"), "w") as f:
            f.write(desc)
        setup_content = "def f():\n    return 0\n"
        with open(os.path.join(tdir, "setup", "f.py"), "w") as f:
            f.write(setup_content)
        with open(os.path.join(tdir, "solution", "f.py"), "w") as f:
            f.write(setup_content)
        with open(os.path.join(tdir, "check.py"), "w") as f:
            f.write(
                "import sys\n"
                "sys.dont_write_bytecode = True\n"
                "sys.path.insert(0, \".\")\n"
                "import f\n"
                "sys.exit(0 if f.f() == " + str(nval) + " else 1)\n"
            )

    models_path = os.path.join(tmp_base, "MODELS.json")
    with open(models_path, "w") as f:
        f.write("{}")

    result_path = os.path.join(tmp_base, "RESULT.json")

    def run_sub(args_list):
        return subprocess.run(
            [sys.executable, self_path] + args_list,
            capture_output=True, text=True
        )

    def check(name, condition, expected_str, got_str):
        nonlocal all_pass
        if condition:
            results.append("PASS " + name + " expected=" + expected_str + " got=" + got_str)
        else:
            results.append("FAIL " + name + " expected=" + expected_str + " got=" + got_str)
            all_pass = False

    r1 = run_sub([
        "run", "--tasks", tasks_dir, "--ids", "tA,tB,tC,tD",
        "--reps", "1", "--bin", bin_dir, "--models", models_path,
        "--out", result_path
    ])
    check("test1_rc", r1.returncode == 0, "0", str(r1.returncode))
    if r1.returncode == 0 and os.path.isfile(result_path):
        with open(result_path, "r") as f:
            data = json.load(f)
        recs = data["records"]
        check("test1_count", len(recs) == 4, "4", str(len(recs)))
        attempts_per_task = {r["task"]: len(r["attempts"]) for r in recs}
        expected_attempts = {"tA": 2, "tB": 1, "tC": 2, "tD": 3}
        for t, exp in expected_attempts.items():
            got = attempts_per_task.get(t, 0)
            check("test1_attempts_" + t, got == exp, str(exp), str(got))
        tC_rec = next((r for r in recs if r["task"] == "tC"), None)
        if tC_rec:
            check("test1_tC_ann", tC_rec["attempts"][0]["announce"] == "RED",
                  "RED", tC_rec["attempts"][0]["announce"])
        tD_rec = next((r for r in recs if r["task"] == "tD"), None)
        if tD_rec:
            check("test1_tD_ann", tD_rec["attempts"][0]["announce"] == "NONE",
                  "NONE", tD_rec["attempts"][0]["announce"])

    r2 = run_sub(["report", "--result", result_path])
    check("test2_rc", r2.returncode == 0, "0", str(r2.returncode))
    if r2.returncode == 0:
        report_data = json.loads(r2.stdout)
        c0 = report_data["C0"]
        check("test2_C0", (c0["n"] == 4 and c0["announced_green"] == 2 and
              c0["announced_red"] == 1 and c0["announced_none"] == 1 and
              c0["false_green"] == 1 and c0["false_green_pct"] == 50.0 and
              c0["passed"] == 1 and c0["passed_pct"] == 25.0 and
              c0["tokens"] == 120),
              "n=4,ag=2,ar=1,an=1,fg=1,fgp=50.0,p=1,pp=25.0,t=120",
              str(c0))

    if r2.returncode == 0:
        c1 = report_data["C1"]
        check("test3_C1", (c1["n"] == 4 and c1["resolved"] == 3 and
              c1["resolved_pct"] == 75.0 and c1["unresolved"] == 1 and
              c1["attempts"] == 8 and c1["tokens"] == 240),
              "n=4,res=3,rp=75.0,unres=1,att=8,t=240",
              str(c1))
        check("test3_overhead", report_data["overhead_ratio"] == 2.0, "2.0", str(report_data["overhead_ratio"]))
        check("test3_tps_c0", report_data["tokens_per_solved_c0"] == 120.0, "120.0", str(report_data["tokens_per_solved_c0"]))
        check("test3_tps_c1", report_data["tokens_per_solved_c1"] == 80.0, "80.0", str(report_data["tokens_per_solved_c1"]))

    if r2.returncode == 0:
        bt = report_data["by_task"]
        check("test4_bt_len", len(bt) == 4, "4", str(len(bt)))
        tA_bt = next((x for x in bt if x["task"] == "tA"), None)
        if tA_bt:
            check("test4_tA", (tA_bt["c0_passed"] == 0 and tA_bt["c0_false_green"] == 1 and
                  tA_bt["c1_resolved"] == 1),
                  "c0_passed=0,c0_false_green=1,c1_resolved=1",
                  str(tA_bt))

    result2_path = os.path.join(tmp_base, "RESULT2.json")
    r5a = run_sub([
        "run", "--tasks", tasks_dir, "--ids", "tA,tB,tC,tD",
        "--reps", "1", "--bin", bin_dir, "--models", models_path,
        "--out", result2_path, "--effort", "low", "--no-thinking"
    ])
    check("test5_effort_nothink_rc", r5a.returncode == 0, "0", str(r5a.returncode))

    r5b = run_sub([
        "run", "--tasks", tasks_dir, "--ids", "tA",
        "--reps", "1", "--bin", bin_dir, "--models", models_path
    ])
    check("test5_no_out_rc", r5b.returncode == 2, "2", str(r5b.returncode))

    r5c = run_sub(["report", "--result", os.path.join(tmp_base, "nonexistent.json")])
    check("test5_missing_file_rc", r5c.returncode == 2, "2", str(r5c.returncode))

    shutil.rmtree(tmp_base, ignore_errors=True)

    for line in results:
        print(line)

    sys.exit(0 if all_pass else 1)


def main():
    if len(sys.argv) < 2:
        print("usage: run_b3.py run|report|--autotest ...", file=sys.stderr)
        sys.exit(2)

    mode = sys.argv[1]

    if mode == "--autotest":
        cmd_autotest()

    elif mode == "run":
        parser = argparse.ArgumentParser(prog="run_b3.py run")
        parser.add_argument("--tasks", required=True)
        parser.add_argument("--ids", required=True)
        parser.add_argument("--reps", required=True, type=int)
        parser.add_argument("--bin", required=True)
        parser.add_argument("--models", required=True)
        parser.add_argument("--out", required=True)
        parser.add_argument("--tries", type=int, default=3)
        parser.add_argument("--effort", default="medium")
        parser.add_argument("--no-thinking", action="store_true", default=False)
        try:
            args = parser.parse_args(sys.argv[2:])
        except SystemExit as e:
            sys.exit(2)
        cmd_run(args)

    elif mode == "report":
        parser = argparse.ArgumentParser(prog="run_b3.py report")
        parser.add_argument("--result", required=True)
        try:
            args = parser.parse_args(sys.argv[2:])
        except SystemExit as e:
            sys.exit(2)
        cmd_report(args)

    else:
        print("usage: run_b3.py run|report|--autotest ...", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
