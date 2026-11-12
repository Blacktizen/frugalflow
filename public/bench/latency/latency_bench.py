#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""latency_bench.py - measures what the FrugalFlow PreToolUse hook costs per tool call."""

import json
import math
import os
import platform
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "..", "bin"))
HOOK = os.path.join(BIN, "guard_hook.py")
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")

USAGE = "usage: latency_bench.py [--runs N] [--json OUT] | --notice | --autotest\n"

NOTICE = (
    "NAME      latency_bench.py - measures the wall time of the guard hook per tool call: five realistic Claude Code payloads, each run N times as its own subprocess.\n"
    "READS     the hook in ../../bin/guard_hook.py, frugalflow.py and its neighbours.\n"
    "WRITES    only a temporary folder, always removed, even on failure: a disposable HOME, a FrugalFlow home initialized by init in active mode, a small project with one file to read and to edit, and the JSON file named by --json. Exit 0 every hook call ran, 1 a hook call failed, 2 bad usage.\n"
    "EXAMPLE   python3 latency_bench.py --runs 50 --json out.json\n"
    "PITFALLS  2026-11-12 timing the hook inside one python would hide the interpreter startup Claude Code really pays: every call is a fresh 'python3 -I guard_hook.py --hook' subprocess with the JSON on stdin, as the installed hook runs.\n"
    "          2026-11-12 init refuses a settings change from a Claude Code session: the bench pops CLAUDECODE and gives HOME and FRUGALFLOW_HOME to throwaway folders, never the real ones.\n"
    "          2026-11-12 p95 is the value at rank ceil(0.95 n) in the sorted list, not an average: with few runs p95 can equal max, and a slow first call shows in max, not in p50.\n"
)

KINDS = ["Read", "Write", "Edit", "Bash_simple", "Bash_pipeline"]


def _env(home_user, ff_home):
    """The environment of every child: throwaway HOME and FRUGALFLOW_HOME, no session keys."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_") or key.startswith("FRUGALFLOW_") or key.endswith("_API_KEY"):
            del env[key]
    # init changes a setting: frugalflow.py refuses it from a Claude Code session.
    env.pop("CLAUDECODE", None)
    env["HOME"] = home_user
    env["FRUGALFLOW_HOME"] = ff_home
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PATH"] = "/opt/homebrew/bin:/usr/bin:/bin"
    return env


def _setup(tmp):
    """A real init in active mode into a throwaway home, and a small project beside it."""
    home_user = os.path.join(tmp, "home")
    ff_home = os.path.join(tmp, "ff")
    claude_dir = os.path.join(tmp, "claude")
    project = os.path.join(tmp, "project")
    for folder in (home_user, ff_home, claude_dir, project):
        os.makedirs(folder)
    notes = os.path.join(project, "notes.md")
    with open(notes, "w", encoding="utf-8") as handle:
        handle.write("# Notes\n\nalpha line for the Edit payload.\nsecond line.\n")
    env = _env(home_user, ff_home)
    proc = subprocess.run(
        [sys.executable, "-I", FRUGALFLOW, "init", "--mode", "active",
         "--home", ff_home, "--claude-dir", claude_dir,
         "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
        capture_output=True, text=True, input="", env=env, cwd=tmp, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError("init rc=" + str(proc.returncode)
                           + " out=" + repr(proc.stdout.splitlines()[:2]))
    return env, project, notes


def _payloads(project, notes):
    """Five tool calls in the shape Claude Code sends to a PreToolUse hook."""
    def one(tool, tool_input):
        return {"tool_name": tool, "tool_input": tool_input,
                "cwd": project, "hook_event_name": "PreToolUse"}
    return {
        "Read": one("Read", {"file_path": notes}),
        "Write": one("Write", {"file_path": os.path.join(project, "draft.md"),
                               "content": "# Draft\n\nA new file for the Write payload.\n"}),
        "Edit": one("Edit", {"file_path": notes,
                             "old_string": "alpha line", "new_string": "beta line"}),
        "Bash_simple": one("Bash", {"command": "ls -l"}),
        "Bash_pipeline": one("Bash", {"command": "ls -1 | grep md | sort | head -n 3 > /dev/null && echo done > /dev/null"}),
    }


def _measure(env, project, payloads, runs):
    """runs hook calls per kind, each a fresh 'python3 -I guard_hook.py --hook'."""
    samples = {}
    failures = []
    for kind in KINDS:
        text = json.dumps(payloads[kind])
        times = []
        for _ in range(runs):
            start = time.perf_counter()
            try:
                proc = subprocess.run(
                    [sys.executable, "-I", HOOK, "--hook"],
                    input=text, capture_output=True, text=True,
                    env=env, cwd=project, timeout=30)
                code = proc.returncode
            except Exception as error:
                code = -1
                failures.append(kind + " exception: " + str(error))
            times.append((time.perf_counter() - start) * 1000.0)
            if code != 0:
                failures.append(kind + " hook exit " + str(code))
        samples[kind] = times
    return samples, failures


def _stats(times):
    """p50 and p95 as the values at rank ceil(0.50 n) and ceil(0.95 n), max as the last."""
    ordered = sorted(times)
    n = len(ordered)

    def at(fraction):
        rank = max(1, math.ceil(fraction * n))
        return ordered[rank - 1]

    return {"p50_ms": round(at(0.50), 1),
            "p95_ms": round(at(0.95), 1),
            "max_ms": round(ordered[-1], 1)}


def _print_table(results):
    print("%-14s %8s %8s %8s" % ("KIND", "p50 ms", "p95 ms", "max ms"))
    for kind in KINDS:
        entry = results[kind]
        print("%-14s %8.1f %8.1f %8.1f" % (kind, entry["p50_ms"], entry["p95_ms"], entry["max_ms"]))


def _bench(runs, out_path):
    tmp = tempfile.mkdtemp(prefix="latency-bench-")
    try:
        env, project, notes = _setup(tmp)
        payloads = _payloads(project, notes)
        samples, failures = _measure(env, project, payloads, runs)
        results = {kind: _stats(samples[kind]) for kind in KINDS}
        _print_table(results)
        if out_path:
            doc = {"runs": runs,
                   "python": platform.python_version(),
                   "platform": platform.platform(terse=True),
                   "results": results}
            with open(out_path, "w", encoding="utf-8") as handle:
                json.dump(doc, handle, indent=2)
                handle.write("\n")
        if failures:
            for line in failures:
                print("FAIL " + line)
            print("LATENCY FAIL " + str(len(failures)) + " hook calls of " + str(runs * len(KINDS)))
            return 1
        print("LATENCY OK " + str(runs) + " runs per kind, python " + platform.python_version())
        return 0
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _autotest():
    self = os.path.abspath(__file__)
    all_pass = True
    tmp = tempfile.mkdtemp(prefix="latency-autotest-")
    try:
        out_path = os.path.join(tmp, "bench.json")
        proc = subprocess.run(
            [sys.executable, self, "--runs", "3", "--json", out_path],
            capture_output=True, text=True, timeout=300)
        data = None
        keys_ok = proc.returncode == 0 and os.path.isfile(out_path)
        if keys_ok:
            try:
                with open(out_path, "r", encoding="utf-8") as handle:
                    data = json.load(handle)
            except (OSError, ValueError):
                keys_ok = False
        if keys_ok:
            res = data.get("results")
            if data.get("runs") != 3 or not isinstance(res, dict):
                keys_ok = False
            else:
                for kind in KINDS:
                    entry = res.get(kind)
                    if not isinstance(entry, dict):
                        keys_ok = False
                        break
                    for field in ("p50_ms", "p95_ms", "max_ms"):
                        value = entry.get(field)
                        if isinstance(value, bool) or not isinstance(value, (int, float)):
                            keys_ok = False
                            break
                    if not keys_ok:
                        break
        if keys_ok:
            print("PASS autotest 1: bench --runs 3 --json exits 0 and its JSON holds runs=3 and the five kinds with p50_ms, p95_ms, max_ms")
        else:
            print("FAIL autotest 1: expected code 0 + runs=3 + five kinds with three numbers, got code "
                  + str(proc.returncode) + " out=" + repr(proc.stdout.splitlines()[-2:]))
            all_pass = False
        for kind in KINDS:
            if not keys_ok:
                print("FAIL autotest 2 " + kind + ": no JSON to check")
                all_pass = False
                continue
            entry = data["results"][kind]
            if 0 < entry["p50_ms"] <= entry["p95_ms"] <= entry["max_ms"]:
                print("PASS autotest 2 " + kind + ": 0 < p50 " + str(entry["p50_ms"])
                      + " <= p95 " + str(entry["p95_ms"]) + " <= max " + str(entry["max_ms"]))
            else:
                print("FAIL autotest 2 " + kind + ": expected 0 < p50 <= p95 <= max, got "
                      + json.dumps(entry))
                all_pass = False
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]
    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if args == ["--autotest"]:
        return _autotest()
    runs = 50
    out_path = None
    index = 0
    while index < len(args):
        if args[index] == "--runs" and index + 1 < len(args) and args[index + 1].isdigit() and int(args[index + 1]) >= 1:
            runs = int(args[index + 1])
            index += 2
        elif args[index] == "--json" and index + 1 < len(args):
            out_path = args[index + 1]
            index += 2
        else:
            sys.stdout.write(USAGE)
            return 2
    return _bench(runs, out_path)


if __name__ == "__main__":
    sys.exit(main())
