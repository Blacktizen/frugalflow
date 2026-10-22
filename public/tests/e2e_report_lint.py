#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the report and lint commands."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
EX = os.path.join(ROOT, "examples")

TRACE = os.path.join(EX, "report_trace.jsonl")
DELEGATIONS = os.path.join(EX, "report_delegations.jsonl")

ACCEPTED_BRIEF = (
    "NATURE: creation\n"
    "PRODUIT: controle\n"  # lang-ok
    "\n"
    "Write one new file: parse_csv.py. It reads a CSV file and prints the number of rows.\n"
    "FORBIDDEN: touching any other file.\n"
    "FORBIDDEN: accented byte literals in the code.\n"
    "Write nothing after the code block.\n"
)
REFUSED_BRIEF = "Write a CSV parser.\n"

USAGE = "usage: e2e_report_lint.py [--notice | --autotest]\n"

NOTICE = (
    "NAME      e2e_report_lint.py - end-to-end test of the report and lint: runs frugalflow.py report and lint in subprocesses on the example traces and on temporary brief files.\n"
    "READS     the tools in ../bin, frugalflow.py and its neighbours, and the example traces in ../examples.\n"
    "WRITES    only temporary brief files, always removed, even on failure. Exit 0 all five steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_report_lint.py\n"
    "PITFALLS  2026-10-04 the report examples are ignored by git: they are added with git add -f.\n"
)


def run_tool(*args):
    """Run frugalflow.py from the bin folder beside the tests folder."""
    return subprocess.run(
        [sys.executable, os.path.join(BIN, "frugalflow.py")] + list(args),
        capture_output=True, text=True)


def _step1(tmp):
    p = run_tool("report", TRACE)
    lines = p.stdout.splitlines()
    ok = (p.returncode == 0
          and "turns: 4 [observed]" in lines
          and any(l.startswith("context reread: 90 500 total") for l in lines))
    expected = ("report on the example trace exits 0, with the line "
                "'turns: 4 [observed]' and a line starting 'context reread: 90 500 total'")
    got = "code={} head={}".format(p.returncode, repr(lines[:2]))
    return ok, expected, got


def _step2(tmp):
    p = run_tool("report", TRACE, "--log", DELEGATIONS)
    lines = p.stdout.splitlines()
    ok = (p.returncode == 0
          and any(l.startswith("DELEGATIONS 3 | success 2") for l in lines))
    expected = ("report with --log on the example delegations exits 0, "
                "with a line starting 'DELEGATIONS 3 | success 2'")
    got = "code={} tail={}".format(p.returncode, repr(lines[-2:]))
    return ok, expected, got


def _step3(tmp):
    missing = os.path.join(tmp, "absent_trace.jsonl")
    p = run_tool("report", missing)
    ok = p.returncode == 2
    expected = "report on a trace path that does not exist exits 2"
    got = "code={}".format(p.returncode)
    return ok, expected, got


def _step4(tmp):
    p = run_tool("lint", "--check-examples")
    lines = p.stdout.splitlines()
    ok = p.returncode == 0 and "CHECKED 27 rules, 0 failed" in lines
    expected = "lint --check-examples exits 0 with the line 'CHECKED 27 rules, 0 failed'"
    got = "code={} last={}".format(p.returncode, repr(lines[-1:]))
    return ok, expected, got


def _step5(tmp):
    acc = os.path.join(tmp, "accepted_brief.txt")
    ref = os.path.join(tmp, "refused_brief.txt")
    with open(acc, "w", encoding="utf-8", newline="") as f:
        f.write(ACCEPTED_BRIEF)
    with open(ref, "w", encoding="utf-8", newline="") as f:
        f.write(REFUSED_BRIEF)
    p_acc = run_tool("lint", acc)
    p_ref = run_tool("lint", ref)
    refused_line = any("REFUSED" in l for l in p_ref.stdout.splitlines())
    ok = p_acc.returncode == 0 and p_ref.returncode != 0 and refused_line
    expected = ("lint accepts the accepted brief (exit 0) and refuses the "
                "refused brief (non-zero exit, a line containing REFUSED)")
    got = "accepted code={} refused code={} refused line={}".format(
        p_acc.returncode, p_ref.returncode, refused_line)
    return ok, expected, got


def steps(tmp):
    labels = ["report", "report-log", "report-missing", "lint-examples", "lint-brief"]
    fns = [_step1, _step2, _step3, _step4, _step5]
    results = []
    for label, fn in zip(labels, fns):
        try:
            ok, expected, got = fn(tmp)
        except Exception:
            ok, expected, got = False, "the step runs", "exception"
        results.append((label, bool(ok), expected, got))
    return results


def main_run(parent):
    tmp = tempfile.mkdtemp(dir=parent)
    try:
        results = steps(tmp)
    finally:
        shutil.rmtree(tmp)
    lines = []
    for label, ok, expected, got in results:
        if ok:
            lines.append("PASS " + label)
        else:
            lines.append("FAIL {} | expected {} | got {}".format(label, expected, got))
    k = sum(1 for label, ok, expected, got in results if not ok)
    if k == 0:
        lines.append("E2E REPORT LINT OK")
    else:
        lines.append("E2E REPORT LINT FAILED {}".format(k))
    return (0 if k == 0 else 1, lines)


def _emit(num, expected, got, ok):
    if ok:
        print("PASS {} expected {} | got {}".format(num, expected, got))
    else:
        print("FAIL {} expected {} | got {}".format(num, expected, got))
    return 0 if ok else 1


def _copy_tree(parent, label):
    copy = os.path.join(parent, label)
    shutil.copytree(ROOT, copy)
    return copy


def _autotest():
    script = os.path.abspath(__file__)
    failures = 0

    # Proof 1: on the intact tree the run exits 0.
    r = subprocess.run([sys.executable, script], capture_output=True, text=True)
    lines = r.stdout.splitlines()
    ok1 = (r.returncode == 0
           and len(lines) == 6
           and all(l.startswith("PASS ") for l in lines[:5])
           and lines[5] == "E2E REPORT LINT OK")
    expected1 = "no argument: code 0, five PASS lines, last line E2E REPORT LINT OK"
    got1 = "code={} lines={} last={}".format(
        r.returncode, len(lines), repr(lines[-1]) if lines else "empty")
    failures += _emit(1, expected1, got1, ok1)

    # Proof 2: --notice passes, anything else is usage with code 2.
    r_notice = subprocess.run([sys.executable, script, "--notice"],
                              capture_output=True, text=True)
    r_bogus = subprocess.run([sys.executable, script, "--bogus"],
                             capture_output=True, text=True)
    ok2 = (r_notice.returncode == 0
           and r_notice.stdout.startswith("NAME      e2e_report_lint.py")
           and r_bogus.returncode == 2
           and r_bogus.stdout == USAGE)
    expected2 = "--notice exits 0 starting NAME, --bogus exits 2 with the usage line"
    got2 = "notice code={} starts={} bogus code={} usage={}".format(
        r_notice.returncode,
        r_notice.stdout.startswith("NAME      e2e_report_lint.py"),
        r_bogus.returncode, r_bogus.stdout == USAGE)
    failures += _emit(2, expected2, got2, ok2)

    # Proof 3: a copy missing the example trace exits 1 with a FAIL report line.
    expected3 = "copy with the example trace removed: code 1, a line starting FAIL report"
    got3 = "not run"
    ok3 = False
    base3 = tempfile.mkdtemp()
    try:
        copy3 = _copy_tree(base3, "copy3")
        os.remove(os.path.join(copy3, "examples", "report_trace.jsonl"))
        r3 = subprocess.run([sys.executable, os.path.join(copy3, "tests", "e2e_report_lint.py")],
                            capture_output=True, text=True)
        lines3 = r3.stdout.splitlines()
        ok3 = r3.returncode == 1 and any(l.startswith("FAIL report") for l in lines3)
        got3 = "code={} last={}".format(r3.returncode, repr(lines3[-1]) if lines3 else "empty")
    except Exception as e:
        got3 = "exception: {}".format(e)
    finally:
        shutil.rmtree(base3, ignore_errors=True)
    failures += _emit(3, expected3, got3, ok3)

    # Proof 4: a copy whose examples file lost one rule exits 1 with FAIL lint-examples.
    expected4 = "copy whose examples lost one rule: code 1, a line starting FAIL lint-examples"
    got4 = "not run"
    ok4 = False
    base4 = tempfile.mkdtemp()
    try:
        copy4 = _copy_tree(base4, "copy4")
        examples = os.path.join(copy4, "config", "brief_rules_examples.json")
        with open(examples, encoding="utf-8") as f:
            doc = json.load(f)
        doc["rules"].pop(next(iter(doc["rules"])))
        with open(examples, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        r4 = subprocess.run([sys.executable, os.path.join(copy4, "tests", "e2e_report_lint.py")],
                            capture_output=True, text=True)
        lines4 = r4.stdout.splitlines()
        ok4 = r4.returncode == 1 and any(l.startswith("FAIL lint-examples") for l in lines4)
        got4 = "code={} last={}".format(r4.returncode, repr(lines4[-1]) if lines4 else "empty")
    except Exception as e:
        got4 = "exception: {}".format(e)
    finally:
        shutil.rmtree(base4, ignore_errors=True)
    failures += _emit(4, expected4, got4, ok4)

    # Proof 5: a copy missing the rules file exits 1 with FAIL lint-brief.
    expected5 = "copy missing the rules file: code 1, a line starting FAIL lint-brief"
    got5 = "not run"
    ok5 = False
    base5 = tempfile.mkdtemp()
    try:
        copy5 = _copy_tree(base5, "copy5")
        os.remove(os.path.join(copy5, "config", "brief_rules.json"))
        r5 = subprocess.run([sys.executable, os.path.join(copy5, "tests", "e2e_report_lint.py")],
                            capture_output=True, text=True)
        lines5 = r5.stdout.splitlines()
        ok5 = r5.returncode == 1 and any(l.startswith("FAIL lint-brief") for l in lines5)
        got5 = "code={} last={}".format(r5.returncode, repr(lines5[-1]) if lines5 else "empty")
    except Exception as e:
        got5 = "exception: {}".format(e)
    finally:
        shutil.rmtree(base5, ignore_errors=True)
    failures += _emit(5, expected5, got5, ok5)

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        code, lines = main_run(None)
        for line in lines:
            print(line)
        sys.exit(code)
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
