#!/usr/bin/env python3
"""Validate every benchmark task.

For each task:
  - copy setup/ to a temp dir, overlay naive/ -> check.py must FAIL,
    and test_visible.py (if present) must PASS;
  - copy setup/ to a temp dir, overlay solution/ -> check.py must PASS,
    and test_visible.py (if present) must PASS.
"""
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent
TASKS = ["t01", "t02", "t03", "t04", "t05", "t06", "t07", "t08", "t09", "t10"]


def run(cmd, cwd):
    return subprocess.run(cmd, cwd=str(cwd), capture_output=True, text=True)


def overlay(src, dst):
    for item in os.listdir(src):
        s = Path(src) / item
        d = Path(dst) / item
        if s.is_dir():
            shutil.copytree(s, d, dirs_exist_ok=True)
        else:
            shutil.copy2(s, d)


def main():
    errors = []
    with tempfile.TemporaryDirectory() as tmp:
        for name in TASKS:
            task = ROOT / name
            setup = task / "setup"
            check = task / "check.py"
            naive = task / "naive"
            solution = task / "solution"
            if not (setup.is_dir() and check.is_file() and naive.is_dir() and solution.is_dir()):
                errors.append("%s missing files" % name)
                print("%s ERROR missing files" % name)
                continue

            # --- naive overlay ---
            d = Path(tmp) / (name + "-naive")
            shutil.copytree(setup, d)
            overlay(naive, d)
            shutil.copy2(check, d / "check.py")

            vis = d / "test_visible.py"
            if vis.exists():
                r = run([sys.executable, "test_visible.py"], cwd=d)
                if r.returncode != 0:
                    errors.append("%s naive visible tests failed" % name)
                    print("%s ERROR naive visible tests failed" % name)
                    continue

            r = run([sys.executable, "check.py"], cwd=d)
            if r.returncode == 0:
                errors.append("%s naive check unexpectedly passed" % name)
                print("%s ERROR naive=GREEN" % name)
                continue

            # --- solution overlay ---
            d2 = Path(tmp) / (name + "-solution")
            shutil.copytree(setup, d2)
            overlay(solution, d2)
            shutil.copy2(check, d2 / "check.py")

            vis2 = d2 / "test_visible.py"
            if vis2.exists():
                r2 = run([sys.executable, "test_visible.py"], cwd=d2)
                if r2.returncode != 0:
                    errors.append("%s solution visible tests failed" % name)
                    print("%s ERROR solution visible tests failed" % name)
                    continue

            r3 = run([sys.executable, "check.py"], cwd=d2)
            if r3.returncode != 0:
                errors.append("%s solution check failed" % name)
                print("%s ERROR solution=RED" % name)
                continue

            print("%s naive=RED solution=GREEN" % name)

    if errors:
        print("ERRORS:", "; ".join(errors))
        sys.exit(1)
    print("all tasks validated")


if __name__ == "__main__":
    main()
