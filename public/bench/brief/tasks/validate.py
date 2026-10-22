#!/usr/bin/env python3
"""Validates every task: faulty brief refused with the intended rule id, fixed
brief accepted, oracle passes the reference, and the fixed/faulty diff exists."""
import os
import subprocess
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
CHECKER = os.path.join(BASE, "..", "..", "..", "bin", "brief_check.py")
RULES = os.path.join(BASE, "..", "..", "..", "config", "brief_rules.json")

FAULTS = {}
for p in range(1, 7):
    FAULTS["p%02d" % p] = "E21"
for p in range(7, 12):
    FAULTS["p%02d" % p] = "E13"
for p in range(12, 16):
    FAULTS["p%02d" % p] = "E3"


def run(args):
    return subprocess.run(args, capture_output=True, text=True)


def refused_ids(stdout):
    return [ln.split()[1] for ln in stdout.splitlines() if ln.startswith("REFUSED ")]


def check_task(task, rule):
    errs = []
    d = os.path.join(BASE, task)
    fixed = os.path.join(d, "brief_fixed.md")
    faulty = os.path.join(d, "brief_faulty.md")
    oracle = os.path.join(d, "check.py")
    ref = os.path.join(d, "reference", "prog.py")

    r = run([sys.executable, CHECKER, "--brief", faulty,
             "--rules", RULES, "--trust", "untrusted_third_party"])
    ids = refused_ids(r.stdout)
    if r.returncode != 5 or ids != [rule]:
        errs.append("faulty: exit %d refused %s (want exit 5, [%s])"
                    % (r.returncode, ids, rule))

    r = run([sys.executable, CHECKER, "--brief", fixed,
             "--rules", RULES, "--trust", "untrusted_third_party"])
    if r.returncode != 0:
        errs.append("fixed: exit %d (want 0)" % r.returncode)
        extra = [ln for ln in r.stdout.splitlines() if ln.startswith("REFUSED ")]
        if extra:
            errs.append("  fixed refused: " + " | ".join(extra[:4]))

    r = run([sys.executable, oracle, ref])
    if r.returncode != 0:
        errs.append("oracle: exit %d out=%r" % (r.returncode, r.stdout.strip()[:160]))

    with open(fixed) as fa, open(faulty) as fb:
        if fa.read() == fb.read():
            errs.append("fixed and faulty are identical")

    return errs


def main():
    failures = []
    for task in sorted(FAULTS):
        errs = check_task(task, FAULTS[task])
        if errs:
            failures.append((task, errs))
            print("%s FAIL" % task)
            for e in errs:
                print("    " + e)
        else:
            print("%s OK" % task)

    print()
    if failures:
        print("FAILED %d/%d tasks" % (len(failures), len(FAULTS)))
        sys.exit(1)
    print("ALL %d TASKS CLEAN" % len(FAULTS))
    sys.exit(0)


if __name__ == "__main__":
    main()
