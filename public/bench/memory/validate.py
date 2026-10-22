#!/usr/bin/env python3
"""Validate the benchmark: projects, roots, hidden oracles, solutions, vaults."""
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
TOOL_BIN = os.path.join(HERE, "..", "..", "bin")
ROOTS = ["tasks_c0", "tasks_c1"]
PROJECTS = sorted(
    d for d in os.listdir(os.path.join(HERE, "tasks_c0"))
    if d.startswith("m") and os.path.isdir(os.path.join(HERE, "tasks_c0", d))
)

failures = []


def report(label, ok, detail=""):
    line = ("ok   " if ok else "FAIL ") + label
    if not ok:
        failures.append(label)
    if detail and not ok:
        line += "\n      " + detail.replace("\n", "\n      ")
    print(line)
    return ok


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def tree_files(root):
    out = {}
    for dirpath, dirnames, filenames in os.walk(root):
        for fn in filenames:
            full = os.path.join(dirpath, fn)
            rel = os.path.relpath(full, root)
            with open(full, "rb") as f:
                out[rel] = f.read()
    return out


def overlay(dst, src):
    for dirpath, dirnames, filenames in os.walk(src):
        rel = os.path.relpath(dirpath, src)
        for fn in filenames:
            sp = os.path.join(dirpath, fn)
            dp = os.path.join(dst, rel, fn)
            os.makedirs(os.path.dirname(dp), exist_ok=True)
            shutil.copyfile(sp, dp)


def check_env(tmp):
    env = dict(os.environ)
    env["PYTHONPATH"] = tmp + os.pathsep + env.get("PYTHONPATH", "")
    return env


def main():
    for root in ROOTS:
        for pid in PROJECTS:
            setup_dir = os.path.join(HERE, root, pid, "setup")
            check_py = os.path.join(HERE, root, pid, "check.py")
            solution_dir = os.path.join(HERE, root, pid, "solution")

            # bare setup: check must FAIL
            bare = tempfile.mkdtemp(prefix="bench-bare-")
            shutil.copytree(setup_dir, bare, dirs_exist_ok=True)
            p = run([sys.executable, check_py], cwd=bare, env=check_env(bare))
            ok = p.returncode == 1 and p.stdout.startswith("FAIL")
            report(f"{pid} {root} bare-check FAIL", ok, p.stdout + p.stderr)

            # bare setup: visible tests must pass
            p = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                    cwd=bare, env=check_env(bare))
            ok = p.returncode == 0
            report(f"{pid} {root} bare-tests pass", ok, p.stdout + p.stderr)
            shutil.rmtree(bare, ignore_errors=True)

            # overlay solution -> check must PASS
            solved = tempfile.mkdtemp(prefix="bench-solved-")
            shutil.copytree(setup_dir, solved, dirs_exist_ok=True)
            overlay(solved, solution_dir)
            p = run([sys.executable, check_py], cwd=solved, env=check_env(solved))
            ok = p.returncode == 0 and p.stdout.strip() == "PASS"
            report(f"{pid} {root} solved-check PASS", ok, p.stdout + p.stderr)

            # overlay solution -> visible tests still pass
            p = run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                    cwd=solved, env=check_env(solved))
            ok = p.returncode == 0
            report(f"{pid} {root} solved-tests pass", ok, p.stdout + p.stderr)
            shutil.rmtree(solved, ignore_errors=True)

        # c1-only vault checks
        if root == "tasks_c1":
            for pid in PROJECTS:
                c1setup = os.path.join(HERE, root, pid, "setup")
                vault = os.path.join(c1setup, "vault")
                p = run([sys.executable, os.path.join(TOOL_BIN, "vault_check.py"),
                         "--vault", vault])
                ok = p.returncode == 0 and "VAULT OK" in p.stdout
                report(f"{pid} {root} vault_check OK", ok, p.stdout + p.stderr)

                log_path = os.path.join(vault, "log.md")
                with open(log_path, "r", encoding="utf-8") as f:
                    log_text = f.read()
                has_entry = ("Session 1 closing note" in log_text
                             and log_text.count("## [") == 2
                             and "How to test" in log_text)
                report(f"{pid} {root} journal entry present", has_entry,
                       "log.md missing expected entry")

    # c1 setup minus vault/ equals c0 setup byte for byte
    for pid in PROJECTS:
        c0 = tree_files(os.path.join(HERE, "tasks_c0", pid, "setup"))
        c1all = tree_files(os.path.join(HERE, "tasks_c1", pid, "setup"))
        c1 = {k: v for k, v in c1all.items() if not k.startswith("vault/")}
        if c0 != c1:
            detail = "only c0: " + ", ".join(sorted(set(c0) - set(c1))) + \
                     " | only c1: " + ", ".join(sorted(set(c1) - set(c0))) + \
                     " | differing: " + ", ".join(sorted(k for k in set(c0) & set(c1) if c0[k] != c1[k]))
        else:
            detail = ""
        report(f"{pid} c1-minus-vault == c0", c0 == c1, detail)

    print()
    if failures:
        print("RESULT: FAIL (" + str(len(failures)) + " failing checks)")
        sys.exit(1)
    print("RESULT: ALL OK")


if __name__ == "__main__":
    main()
