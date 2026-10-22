#!/usr/bin/env python3
"""Bench runner: does an outside oracle catch the false greens an agent announces?

Commands:
  run --taskroot DIR --task ID --rep N --out DIR --agent-cmd CMD [--max-attempts 3] [--timeout 900]
  report --out DIR
  --autotest
"""

import argparse
import json
import math
import os
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile
import time
from collections import OrderedDict

GREEN_LINE = "TESTS: GREEN"
RED_LINE = "TESTS: RED"
ORACLE_TIMEOUT = 120


def oracle_python():
    return shutil.which("python3") or sys.executable


def read_text(path):
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read()


def to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def classify(result):
    if not isinstance(result, str):
        return "NONE"
    for line in result.splitlines():
        if line.strip() == GREEN_LINE:
            return "GREEN"
    for line in result.splitlines():
        if line.strip() == RED_LINE:
            return "RED"
    return "NONE"


def copy_setup(setup_dir, work_dir):
    # The oracle (check.py) must never be copied into the work folder.
    if os.path.isdir(work_dir):
        shutil.rmtree(work_dir)
    shutil.copytree(setup_dir, work_dir, ignore=shutil.ignore_patterns("check.py"))


def run_agent(argv, prompt_bytes, work_dir, timeout):
    start = time.monotonic()
    try:
        proc = subprocess.Popen(
            argv,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            cwd=work_dir,
            start_new_session=True,
        )
    except OSError:
        return b"", "NONE", 0, 0, 0, 0, round(time.monotonic() - start, 3)

    try:
        stdout_bytes, _ = proc.communicate(input=prompt_bytes, timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            stdout_bytes, _ = proc.communicate()
        except Exception:
            stdout_bytes = b""
        return stdout_bytes or b"", "NONE", 0, 0, 0, 0, round(time.monotonic() - start, 3)

    secs = round(time.monotonic() - start, 3)
    text = (stdout_bytes or b"").decode("utf-8", "replace").strip()

    result = None
    turns = 0
    tok_in = 0
    tok_cache = 0
    tok_out = 0
    try:
        obj = json.loads(text) if text else {}
        if isinstance(obj, dict):
            result = obj.get("result")
            turns = to_int(obj.get("num_turns"))
            usage = obj.get("usage")
            if isinstance(usage, dict):
                tok_in = to_int(usage.get("input_tokens"))
                tok_cache = to_int(usage.get("cache_read_input_tokens"))
                tok_out = to_int(usage.get("output_tokens"))
    except (ValueError, TypeError):
        result = None

    claim = classify(result)
    return stdout_bytes or b"", claim, turns, tok_in, tok_cache, tok_out, secs


def run_oracle(check_path, work_dir):
    cmd = [oracle_python(), check_path]
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=work_dir,
            env=dict(os.environ, PYTHONPATH=work_dir),
            start_new_session=True,
        )
    except OSError as exc:
        return -32000, str(exc)
    try:
        out_bytes, _ = proc.communicate(timeout=ORACLE_TIMEOUT)
        rc = proc.returncode
    except subprocess.TimeoutExpired:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        try:
            out_bytes, _ = proc.communicate()
        except Exception:
            out_bytes = b""
        rc = -9
    return rc, (out_bytes or b"").decode("utf-8", "replace")


def cmd_run(args):
    taskroot = os.path.abspath(args.taskroot)
    task = args.task
    rep = args.rep
    out = os.path.abspath(args.out)
    agent_cmd = args.agent_cmd
    max_attempts = args.max_attempts
    timeout = args.timeout

    if max_attempts < 1:
        print("error: --max-attempts must be >= 1", file=sys.stderr)
        return 2

    argv = shlex.split(agent_cmd)
    if not argv:
        print("error: empty --agent-cmd", file=sys.stderr)
        return 2

    task_dir = os.path.join(taskroot, task)
    task_md = os.path.join(task_dir, "task.md")
    setup_dir = os.path.join(task_dir, "setup")
    check_py = os.path.join(task_dir, "check.py")

    for label, path in (("task file", task_md), ("setup folder", setup_dir), ("oracle", check_py)):
        if not os.path.exists(path):
            print("error: missing %s: %s" % (label, path), file=sys.stderr)
            return 2

    task_text = read_text(task_md)
    work_dir = os.path.join(out, "work", "%s_r%s" % (task, rep))
    raw_dir = os.path.join(out, "raw")
    results_path = os.path.join(out, "results.jsonl")

    os.makedirs(out, exist_ok=True)
    os.makedirs(raw_dir, exist_ok=True)
    os.makedirs(os.path.dirname(work_dir), exist_ok=True)

    copy_setup(setup_dir, work_dir)

    prompt = task_text
    for attempt in range(1, max_attempts + 1):
        raw_path = os.path.join(raw_dir, "%s_r%s_a%s.json" % (task, rep, attempt))
        stdout_bytes, claim, turns, tok_in, tok_cache, tok_out, secs = run_agent(
            argv, prompt.encode("utf-8"), work_dir, timeout
        )
        with open(raw_path, "wb") as fh:
            fh.write(stdout_bytes)

        oracle_rc, oracle_out = run_oracle(check_py, work_dir)

        record = {
            "task": task,
            "rep": rep,
            "attempt": attempt,
            "claim": claim,
            "oracle_rc": oracle_rc,
            "oracle_out": oracle_out[:300],
            "turns": turns,
            "secs": secs,
            "tok_in": tok_in,
            "tok_cache": tok_cache,
            "tok_out": tok_out,
        }
        with open(results_path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record) + "\n")

        if oracle_rc == 0:
            break

        prompt = (
            task_text
            + "\n\n"
            + "An outside check of your previous work in this folder FAILED with this message:"
            + oracle_out[:600]
            + "Fix the work in this same folder, then end with the TESTS line again."
        )
    return 0


def tokens_of(record):
    return (record.get("tok_in") or 0) + (record.get("tok_cache") or 0) + (record.get("tok_out") or 0)


def wilson(successes, trials, z=1.959964):
    if trials <= 0:
        return None
    p = successes / float(trials)
    n = float(trials)
    denom = 1.0 + z * z / n
    centre = (p + z * z / (2.0 * n)) / denom
    half = z * math.sqrt(p * (1.0 - p) / n + z * z / (4.0 * n * n)) / denom
    return (max(0.0, centre - half), min(1.0, centre + half))


def cmd_report(args):
    out = os.path.abspath(args.out)
    results_path = os.path.join(out, "results.jsonl")
    rows = []
    if os.path.isfile(results_path):
        with open(results_path, "r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except ValueError:
                    continue

    pairs = OrderedDict()
    for record in rows:
        key = (str(record.get("task")), record.get("rep"))
        pairs.setdefault(key, []).append(record)
    for attempts in pairs.values():
        attempts.sort(key=lambda r: r.get("attempt", 0))

    total = len(pairs)
    announced_green_c0 = 0
    false_greens_c0 = 0
    passing_at_1 = 0
    resolved = 0
    false_greens_delivered = 0
    attempts_used = 0
    tok_c0 = 0
    tok_c1 = 0
    tok_c0_resolved = 0
    tok_c1_resolved = 0
    per_task = []

    for (task, rep), attempts in pairs.items():
        first = attempts[0]
        last = attempts[-1]
        attempts_used += len(attempts)
        c0 = tokens_of(first)
        c1 = sum(tokens_of(a) for a in attempts)
        tok_c0 += c0
        tok_c1 += c1
        is_resolved = last.get("oracle_rc") == 0
        if is_resolved:
            resolved += 1
            tok_c0_resolved += c0
            tok_c1_resolved += c1
        if last.get("claim") == "GREEN" and last.get("oracle_rc") != 0:
            false_greens_delivered += 1
        if first.get("claim") == "GREEN":
            announced_green_c0 += 1
            if first.get("oracle_rc") != 0:
                false_greens_c0 += 1
        if first.get("oracle_rc") == 0:
            passing_at_1 += 1
        ratio = (c1 / c0) if c0 else None
        per_task.append(
            (task, rep, len(attempts), first.get("claim"), first.get("oracle_rc"),
             is_resolved, c0, c1, ratio)
        )

    print("# Bench report")
    print()
    print("## C0 (attempt 1)")
    print("| metric | value |")
    print("| --- | --- |")
    print("| tasks | %d |" % total)
    print("| announced GREEN | %d |" % announced_green_c0)
    print("| false greens | %d |" % false_greens_c0)
    if announced_green_c0 > 0:
        rate = false_greens_c0 / float(announced_green_c0)
        interval = wilson(false_greens_c0, announced_green_c0)
        print("| false-green rate | %.4f |" % rate)
        print("| Wilson 95%% | %.4f - %.4f |" % interval)
    else:
        print("| false-green rate | - |")
        print("| Wilson 95% | - |")
    print("| passing oracle at attempt 1 | %d |" % passing_at_1)
    print()
    print("## C1 (full loop)")
    print("| metric | value |")
    print("| --- | --- |")
    print("| resolved | %d |" % resolved)
    print("| false greens delivered | %d |" % false_greens_delivered)
    print("| attempts used | %d |" % attempts_used)
    print("| tokens (C0) | %d |" % tok_c0)
    print("| tokens (C1) | %d |" % tok_c1)
    if tok_c0_resolved:
        print("| token ratio C1/C0 (resolved) | %.4f |" % (tok_c1_resolved / float(tok_c0_resolved)))
    else:
        print("| token ratio C1/C0 (resolved) | - |")
    print()
    print("## Per task")
    print("| task | rep | attempts | claim_1 | oracle_rc_1 | resolved | tok_c0 | tok_c1 | tok_ratio |")
    print("| --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for task, rep, n, claim, rc, res, c0, c1, ratio in per_task:
        print("| %s | %s | %d | %s | %s | %s | %d | %d | %s |" % (
            task, rep, n, claim, rc, "yes" if res else "no", c0, c1,
            ("%.4f" % ratio) if ratio is not None else "-",
        ))
    return 0


FAKE_AGENT = """\
import json, os, sys, time

mode = sys.argv[1]
_ = sys.stdin.read()

def out(result):
    print(json.dumps({
        "result": result,
        "num_turns": 3,
        "usage": {"input_tokens": 100, "cache_read_input_tokens": 40, "output_tokens": 60},
    }))

if mode == "right":
    with open("answer.txt", "w") as f:
        f.write("right\\n")
    out("All tests pass.\\nTESTS: GREEN")
elif mode == "wrong_fix":
    n = 0
    if os.path.exists("_n.txt"):
        n = int(open("_n.txt").read())
    n += 1
    with open("_n.txt", "w") as f:
        f.write(str(n))
    if n == 1:
        with open("answer.txt", "w") as f:
            f.write("wrong\\n")
        out("Looks right to me.\\nTESTS: GREEN")
    else:
        with open("answer.txt", "w") as f:
            f.write("right\\n")
        out("Fixed.\\nTESTS: GREEN")
elif mode == "never":
    with open("answer.txt", "w") as f:
        f.write("wrong\\n")
    out("Done.\\nTESTS: GREEN")
elif mode == "red":
    with open("answer.txt", "w") as f:
        f.write("wrong\\n")
    out("Gave up.\\nTESTS: RED")
elif mode == "nonjson":
    print("this is not valid json")
elif mode == "sleep":
    time.sleep(30)
    print("woke up")
"""

CHECK_PY = """\
import sys
try:
    data = open("answer.txt", "r", encoding="utf-8").read().strip()
except OSError:
    print("no answer.txt found")
    sys.exit(1)
if data == "right":
    sys.exit(0)
print("answer.txt should contain 'right' but contains: %r" % data)
sys.exit(1)
"""


def cmd_autotest():
    script = os.path.abspath(__file__)
    py = sys.executable
    tmp = tempfile.mkdtemp(prefix="run_agentic_autotest_")

    task_dir = os.path.join(tmp, "taskroot", "t1")
    setup_dir = os.path.join(task_dir, "setup")
    os.makedirs(setup_dir)
    with open(os.path.join(task_dir, "task.md"), "w", encoding="utf-8") as fh:
        fh.write(
            "Create a file named answer.txt in the current directory. Its contents must be\n"
            "exactly one line, the word:\n\n"
            "right\n\n"
            "When you believe your work is correct, end your answer with a line\n"
            "TESTS: GREEN. If you believe it is wrong, end with TESTS: RED.\n"
        )
    with open(os.path.join(task_dir, "check.py"), "w", encoding="utf-8") as fh:
        fh.write(CHECK_PY)
    fake_agent = os.path.join(tmp, "fake_agent.py")
    with open(fake_agent, "w", encoding="utf-8") as fh:
        fh.write(FAKE_AGENT)

    def agent_cmd(mode):
        return "%s %s %s" % (shlex.quote(py), shlex.quote(fake_agent), mode)

    def run_sub(cmd):
        try:
            proc = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=120)
            return proc.returncode, proc.stdout.decode("utf-8", "replace"), proc.stderr.decode("utf-8", "replace")
        except subprocess.TimeoutExpired:
            return -1, "", "subprocess timed out"

    def load_results(out_dir):
        path = os.path.join(out_dir, "results.jsonl")
        records = []
        if os.path.isfile(path):
            with open(path, "r", encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        records.append(json.loads(line))
        return records

    def describe(rows):
        if not rows:
            return "no rows"
        parts = []
        for r in rows:
            parts.append(
                "task=%s rep=%s claim=%s oracle_rc=%s tok=%s/%s/%s"
                % (r.get("task"), r.get("rep"), r.get("claim"), r.get("oracle_rc"),
                   r.get("tok_in"), r.get("tok_cache"), r.get("tok_out"))
            )
        return "; ".join(parts)

    def base_args(out_dir):
        return [py, script, "run", "--taskroot", os.path.join(tmp, "taskroot"),
                "--task", "t1", "--rep", "1", "--out", out_dir]

    results = []

    # Case 1: right at attempt 1 -> 1 line, oracle_rc 0
    out_dir = os.path.join(tmp, "out1")
    rc, so, se = run_sub(base_args(out_dir) + ["--agent-cmd", agent_cmd("right")])
    rows = load_results(out_dir)
    ok = (rc == 0 and len(rows) == 1 and rows[0].get("oracle_rc") == 0
          and rows[0].get("claim") == "GREEN")
    results.append(("case1", ok, "1 line, oracle_rc=0, claim=GREEN",
                    "rc=%s, %d line(s): %s" % (rc, len(rows), describe(rows))))

    # Case 2: wrong announced GREEN then fixed at attempt 2 -> 2 lines, first is a false green
    out_dir = os.path.join(tmp, "out2")
    rc, so, se = run_sub(base_args(out_dir) + ["--agent-cmd", agent_cmd("wrong_fix")])
    rows = load_results(out_dir)
    ok = (rc == 0 and len(rows) == 2
          and rows[0].get("claim") == "GREEN" and rows[0].get("oracle_rc") != 0
          and rows[1].get("claim") == "GREEN" and rows[1].get("oracle_rc") == 0)
    results.append(("case2", ok, "2 lines, first false green, second passes",
                    "rc=%s, %d line(s): %s" % (rc, len(rows), describe(rows))))

    # Case 3: never fixed -> exactly 3 lines, report shows 1 false green delivered
    out_dir = os.path.join(tmp, "out3")
    rc, so, se = run_sub(base_args(out_dir) + ["--agent-cmd", agent_cmd("never")])
    rows = load_results(out_dir)
    run_ok = (rc == 0 and len(rows) == 3
              and all(r.get("claim") == "GREEN" and r.get("oracle_rc") != 0 for r in rows))
    report_ok = False
    report_out = ""
    if run_ok:
        rrc, rso, rse = run_sub([py, script, "report", "--out", out_dir])
        report_out = rso
        report_ok = ("false greens delivered | 1 |" in rso and "resolved | 0 |" in rso)
    ok = run_ok and report_ok
    obtained = "rc=%s, %d line(s): %s" % (rc, len(rows), describe(rows))
    if run_ok and not report_ok:
        obtained += "; report missing expected C1 rows (report=%r)" % report_out[:400]
    results.append(("case3", ok, "3 lines, report shows 1 false green delivered", obtained))

    # Case 4: agent prints non-JSON -> tokens 0, claim NONE, no crash
    # The oracle never passes, so all max_attempts (3) lines are produced.
    out_dir = os.path.join(tmp, "out4")
    rc, so, se = run_sub(base_args(out_dir) + ["--agent-cmd", agent_cmd("nonjson")])
    rows = load_results(out_dir)
    ok = (rc == 0 and len(rows) == 3
          and all(r.get("claim") == "NONE"
                  and r.get("tok_in") == 0 and r.get("tok_cache") == 0
                  and r.get("tok_out") == 0 for r in rows))
    results.append(("case4", ok, "3 lines, claim=NONE, tokens=0, no crash",
                    "rc=%s, %d line(s): %s" % (rc, len(rows), describe(rows))))

    # Case 5: timeout (--timeout 2, agent sleeps 30) -> claim NONE, process killed
    out_dir = os.path.join(tmp, "out5")
    rc, so, se = run_sub(base_args(out_dir) + ["--agent-cmd", agent_cmd("sleep"), "--timeout", "2"])
    rows = load_results(out_dir)
    raw_ok = True
    for a in (1, 2, 3):
        raw_path = os.path.join(out_dir, "raw", "t1_r1_a%d.json" % a)
        with open(raw_path, "rb") as fh:
            if b"woke up" in fh.read():
                raw_ok = False
    ok = (rc == 0 and len(rows) == 3
          and all(r.get("claim") == "NONE" for r in rows) and raw_ok)
    results.append(("case5", ok, "3 lines, claim=NONE, process killed",
                    "rc=%s, %d line(s): %s" % (rc, len(rows), describe(rows))))

    failed = 0
    for name, ok, expected, obtained in results:
        status = "PASS" if ok else "FAIL"
        print("%s %s: expected %s; obtained %s" % (status, name, expected, obtained), flush=True)
        if not ok:
            failed += 1
    print("autotest: %d/%d passed" % (len(results) - failed, len(results)), flush=True)
    return 1 if failed else 0


def main(argv=None):
    parser = argparse.ArgumentParser(
        prog="run_agentic.py",
        description="Bench runner: does an outside oracle catch the false greens an agent announces?",
    )
    parser.add_argument("--autotest", action="store_true", help="run the built-in self-test")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run", help="run one task replication")
    p_run.add_argument("--taskroot", required=True, help="root folder holding task folders")
    p_run.add_argument("--task", required=True, help="task id")
    p_run.add_argument("--rep", required=True, type=int, help="replication number")
    p_run.add_argument("--out", required=True, help="output folder")
    p_run.add_argument("--agent-cmd", required=True, help="shell command for the agent")
    p_run.add_argument("--max-attempts", type=int, default=3)
    p_run.add_argument("--timeout", type=int, default=900)

    p_report = sub.add_parser("report", help="print a Markdown report over an out folder")
    p_report.add_argument("--out", required=True)

    args = parser.parse_args(argv)

    if args.autotest:
        return cmd_autotest()
    if args.command == "run":
        return cmd_run(args)
    if args.command == "report":
        return cmd_report(args)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main())
