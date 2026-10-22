#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: the bench runs a mini catalog, resumes, the report sums the conditions, and the real catalog is solved by a reference condition."""

import os
import re
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))
BENCH = os.path.normpath(os.path.join(HERE, "..", "bench"))
BENCH_TASKS = os.path.join(BENCH, "tasks")
BENCH_TASKS_JSON = os.path.join(BENCH, "tasks.json")
BENCH_RUN = os.path.join(BIN, "bench_run.py")
BENCH_REPORT = os.path.join(BIN, "bench_report.py")

USAGE = "usage: e2e_bench.py | --notice\n"

NOTICE = (
    "NAME      e2e_bench.py - end-to-end test: runs bench_run.py on a planted mini bench, "
    "resumes it, sums it with bench_report.py, then runs the real public/bench catalog under a "
    "reference condition that copies each task's own solution.\n"
    "READS     the tools in ../bin, bench_run.py and bench_report.py, and the catalog in ../bench.\n"
    "WRITES    only a temporary folder, always removed, even on failure: the mini tasks, the "
    "conditions files, the reference script and the two results files. Exit 0 all four steps pass, "
    "1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_bench.py\n"
    "PITFALLS  2026-10-10 the subprocesses get a HOME of their own and no *_API_KEY: the bench must "
    "run on the planted fixtures only.\n"
    "          2026-10-10 every RESULT line is matched whole: a bench that prints solvd= instead of "
    "solved= still counts its runs, so only the line itself proves the check verdict travelled.\n"
)

RESULT_RE = re.compile(
    r"\ARESULT (t01|t02) (solver|idle) ([12]) solved=(true|false) cost=0\.000120 seconds=[0-9]+\.[0-9]\Z")

USAGE_JSON = json.dumps({
    "type": "result", "is_error": False, "num_turns": 1,
    "usage": {"input_tokens": 100, "cache_creation_input_tokens": 0,
              "cache_read_input_tokens": 0, "output_tokens": 10}})

SOLVER_SRC = (
    "import json\n"
    "with open('answer.txt', 'w', encoding='utf-8') as handle:\n"
    "    handle.write('42\\n')\n"
    "print(" + repr(USAGE_JSON) + ")\n"
)

IDLE_SRC = (
    "import json\n"
    "print(" + repr(USAGE_JSON) + ")\n"
)

CHECK_SRC = (
    "import sys\n"
    "try:\n"
    "    data = open('answer.txt', 'r', encoding='utf-8').read()\n"
    "except OSError:\n"
    "    sys.exit(1)\n"
    "sys.exit(0 if '42' in data else 1)\n"
)

PREPARE_SRC = (
    "with open('data.txt', 'w', encoding='utf-8') as handle:\n"
    "    handle.write('line one\\nline two\\n')\n"
)

REFERENCE_SRC = (
    "import json, os, shutil, sys\n"
    "with open(sys.argv[1], 'r', encoding='utf-8') as handle:\n"
    "    wanted = handle.read()\n"
    "base = sys.argv[2]\n"
    "found = None\n"
    "for task_id in sorted(os.listdir(base)):\n"
    "    md_path = os.path.join(base, task_id, 'task.md')\n"
    "    if not os.path.isfile(md_path):\n"
    "        continue\n"
    "    with open(md_path, 'r', encoding='utf-8') as handle:\n"
    "        if handle.read() == wanted:\n"
    "            found = task_id\n"
    "            break\n"
    "if found is not None:\n"
    "    src = os.path.join(base, found, 'solution')\n"
    "    for name in sorted(os.listdir(src)):\n"
    "        shutil.copy2(os.path.join(src, name), os.path.join(os.getcwd(), name))\n"
    "print(" + repr(USAGE_JSON) + ")\n"
)

MINI_TASKS = json.dumps({"schema_version": "1", "tasks": [
    {"id": "t01", "title": "write the answer", "kind": "code"},
    {"id": "t02", "title": "read the logs", "kind": "logs"}]})

MINI_CONDITIONS = json.dumps({"schema_version": "1", "conditions": [
    {"name": "solver", "command": ["python3", "solver.py"],
     "prices": {"input": 1.0, "cached_input": 0.1, "output": 2.0}},
    {"name": "idle", "command": ["python3", "idle.py"],
     "prices": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}]})

EXPECTED_REPORT_LINES = [
    "CONDITION solver runs=4 solved=4 cost=0.000480 per_solved=0.000120 unpriced=0",
    "CONDITION idle runs=4 solved=0 cost=0.000480 per_solved=n/a unpriced=0",
]


def make_env(tmp):
    env = dict(os.environ)
    env["HOME"] = tmp
    env["PYTHONPYCACHEPREFIX"] = os.path.join(tmp, "pycache")
    for name in list(env):
        if name.endswith("_API_KEY") or name == "FRUGALFLOW_HOME":
            env.pop(name)
    return env


def run_tool(env, cwd, tool, args):
    return subprocess.run(
        [sys.executable, tool] + list(args),
        stdin=subprocess.DEVNULL, capture_output=True, text=True, env=env, cwd=cwd)


def write_text(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def read_lines(path):
    if not os.path.isfile(path):
        return []
    with open(path, "r", encoding="utf-8") as handle:
        return [line for line in handle.read().splitlines() if line.strip() != ""]


def build_mini_bench(tmp):
    tasks_path = os.path.join(tmp, "mini_tasks.json")
    conditions_path = os.path.join(tmp, "mini_conditions.json")
    write_text(tasks_path, MINI_TASKS)
    write_text(conditions_path, MINI_CONDITIONS)
    for task_id in ("t01", "t02"):
        task_dir = os.path.join(tmp, "tasks", task_id)
        os.makedirs(os.path.join(task_dir, "setup"))
        write_text(os.path.join(task_dir, "task.md"), "Put 42 in answer.txt.\n")
        write_text(os.path.join(task_dir, "setup", "solver.py"), SOLVER_SRC)
        write_text(os.path.join(task_dir, "setup", "idle.py"), IDLE_SRC)
        write_text(os.path.join(task_dir, "check.py"), CHECK_SRC)
    write_text(os.path.join(tmp, "tasks", "t02", "prepare.py"), PREPARE_SRC)
    return tasks_path, conditions_path


def _step1(env, tmp, tasks_path, conditions_path, out_path):
    proc = run_tool(env, tmp, BENCH_RUN,
                    ["run-all", "--tasks", tasks_path, "--conditions", conditions_path,
                     "--out", out_path, "--reps", "2"])
    lines = proc.stdout.splitlines()
    result_lines = [line for line in lines if line.startswith("RESULT ")]
    matched = [RESULT_RE.match(line) for line in result_lines]
    verdicts = sorted((m.group(1), m.group(2), m.group(3), m.group(4))
                      for m in matched if m is not None)
    expected_verdicts = sorted(
        (task, condition, str(rep), "true" if condition == "solver" else "false")
        for task in ("t01", "t02") for condition in ("solver", "idle") for rep in (1, 2))
    out_lines = read_lines(out_path)
    ok = (proc.returncode == 0
          and lines[-1:] == ["DONE 8 runs, 0 skipped, 0 refused"]
          and len(result_lines) == 8 and all(m is not None for m in matched)
          and verdicts == expected_verdicts
          and len(out_lines) == 8)
    expected = ("run-all --reps 2 exits 0, prints 8 RESULT lines solved=true for solver and "
                "solved=false for idle at cost=0.000120 and the line 'DONE 8 runs, 0 skipped, "
                "0 refused', and --out holds 8 lines")
    got = ("code=" + str(proc.returncode)
           + " last_line=" + repr(lines[-1:] or [""])
           + " result_lines=" + str(len(result_lines))
           + " matched=" + str(sum(1 for m in matched if m is not None))
           + " verdicts_ok=" + str(verdicts == expected_verdicts)
           + " out_lines=" + str(len(out_lines)))
    return ok, expected, got


def _step2(env, tmp, tasks_path, conditions_path, out_path):
    proc = run_tool(env, tmp, BENCH_RUN,
                    ["run-all", "--tasks", tasks_path, "--conditions", conditions_path,
                     "--out", out_path, "--reps", "2"])
    lines = proc.stdout.splitlines()
    out_lines = read_lines(out_path)
    ok = (proc.returncode == 0
          and lines[-1:] == ["DONE 0 runs, 8 skipped, 0 refused"]
          and len(out_lines) == 8)
    expected = ("the same run-all --reps 2 exits 0, prints 'DONE 0 runs, 8 skipped, 0 refused' "
                "and --out still holds 8 lines")
    got = ("code=" + str(proc.returncode)
           + " last_line=" + repr(lines[-1:] or [""])
           + " out_lines=" + str(len(out_lines)))
    return ok, expected, got


def _step3(env, tmp, out_path):
    proc = run_tool(env, tmp, BENCH_REPORT, [out_path])
    lines = proc.stdout.splitlines()
    ok = proc.returncode == 0 and lines == EXPECTED_REPORT_LINES
    expected = ("bench_report.py exits 0 and prints exactly the two lines "
                + repr(EXPECTED_REPORT_LINES))
    got = "code=" + str(proc.returncode) + " out=" + repr(lines)
    return ok, expected, got


def _step4(env, tmp):
    reference_path = os.path.join(tmp, "reference.py")
    write_text(reference_path, REFERENCE_SRC)
    conditions_path = os.path.join(tmp, "reference_conditions.json")
    write_text(conditions_path, json.dumps({"schema_version": "1", "conditions": [
        {"name": "reference",
         "command": ["python3", reference_path, "{task}", BENCH_TASKS],
         "prices": {"input": 1.0, "cached_input": 0.1, "output": 2.0}}]}))
    out_path = os.path.join(tmp, "real_results.jsonl")
    proc = run_tool(env, tmp, BENCH_RUN,
                    ["run-all", "--tasks", BENCH_TASKS_JSON, "--conditions", conditions_path,
                     "--out", out_path, "--reps", "1"])
    lines = proc.stdout.splitlines()
    out_lines = read_lines(out_path)
    expected = ("run-all on public/bench/tasks.json --reps 1 exits 0 with 'DONE 20 runs, "
                "0 skipped, 0 refused' and 20 out lines, and bench_report.py prints a line "
                "starting with 'CONDITION reference runs=20 solved=20 '")
    got = ("code=" + str(proc.returncode)
           + " last_line=" + repr(lines[-1:] or [""])
           + " out_lines=" + str(len(out_lines)))
    if not (proc.returncode == 0
            and lines[-1:] == ["DONE 20 runs, 0 skipped, 0 refused"]
            and len(out_lines) == 20):
        return False, expected, got
    report = run_tool(env, tmp, BENCH_REPORT, [out_path])
    report_lines = report.stdout.splitlines()
    prefix_ok = (report.returncode == 0 and len(report_lines) == 1
                 and report_lines[0].startswith("CONDITION reference runs=20 solved=20 "))
    got += " | report code=" + str(report.returncode) + " out=" + repr(report_lines)
    return prefix_ok, expected, got


def main_run():
    tmp = tempfile.mkdtemp()
    try:
        env = make_env(tmp)
        tasks_path, conditions_path = build_mini_bench(tmp)
        out_path = os.path.join(tmp, "results.jsonl")
        fns = [
            lambda: _step1(env, tmp, tasks_path, conditions_path, out_path),
            lambda: _step2(env, tmp, tasks_path, conditions_path, out_path),
            lambda: _step3(env, tmp, out_path),
            lambda: _step4(env, tmp),
        ]
        results = []
        for num, fn in enumerate(fns, start=1):
            try:
                ok, expected, got = fn()
            except Exception as error:
                ok, expected, got = False, "the step runs", "exception: " + str(error)
            results.append((num, bool(ok), expected, got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = None
    for num, ok, expected, got in results:
        if ok:
            print("PASS {} expected {} | got {}".format(num, expected, got))
        else:
            print("FAIL {} expected {} | got {}".format(num, expected, got))
            if failed is None:
                failed = (num, got)
    if failed is None:
        print("E2E BENCH OK")
        return 0
    print("E2E BENCH FAIL {} {}".format(failed[0], failed[1]))
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main_run())
    elif sys.argv[1:] == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
