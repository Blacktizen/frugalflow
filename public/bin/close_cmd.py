#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""close_cmd.py - the closing pass: run the vault check, then say if the handoff is ready."""

import os
import re
import sys
import subprocess
import tempfile
import shutil

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE_MSG = "usage: close_cmd.py [--vault DIR] [--repo DIR] | --notice | --autotest"

NOTICE = (
    "NAME      close_cmd.py - the closing pass: runs vault_check.py, counts the sealed journal entries and says if the handoff is ready.\n"
    "READS     --vault DIR (default: ./vault) and --repo DIR (default: the folder holding the vault); the output of vault_check.py.\n"
    "WRITES    nothing: the check lines, then one closing line. Exit 0 ready, 2 usage, 3 no vault, else the exit code of vault_check.py (6 when a check failed).\n"
    "EXAMPLE   python3 close_cmd.py --vault ~/projects/demo/vault --repo ~/projects/demo\n"
    "PITFALLS  2026-11-12 the closing pass was a list of commands to remember by heart; it is now one command that prints whether the handoff is ready.\n"
)

PASS_LOG = re.compile(r"^PASS LOG (\d+) entries chained$")


def main(argv):
    """Parse arguments, run the vault check, print the closing line, return the exit code."""
    vault_dir = None
    repo_dir = None
    notice_flag = False
    autotest_flag = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--vault":
            i += 1
            if i >= len(argv):
                print(USAGE_MSG)
                return 2
            vault_dir = argv[i]
        elif arg == "--repo":
            i += 1
            if i >= len(argv):
                print(USAGE_MSG)
                return 2
            repo_dir = argv[i]
        elif arg == "--notice":
            notice_flag = True
        elif arg == "--autotest":
            autotest_flag = True
        else:
            print(USAGE_MSG)
            return 2
        i += 1

    if notice_flag:
        print(NOTICE)
        return 0

    if autotest_flag:
        return _run_autotest()

    if vault_dir is None:
        vault_dir = os.path.join(os.getcwd(), "vault")
    if repo_dir is None:
        repo_dir = os.path.dirname(os.path.abspath(vault_dir))

    if not os.path.isdir(vault_dir):
        print("NO VAULT: " + vault_dir)
        return 3

    result = subprocess.run(
        [sys.executable, "-I", os.path.join(BIN, "vault_check.py"),
         "--vault", vault_dir, "--repo", repo_dir],
        capture_output=True, text=True
    )
    sys.stdout.write(result.stdout)

    if result.returncode != 0:
        print("Closing not done: fix the FAIL lines above, then run frugalflow close again.")
        return result.returncode

    entries = 0
    for line in result.stdout.splitlines():
        match = PASS_LOG.match(line)
        if match:
            entries = int(match.group(1))
            break
    word = "decision" if entries == 1 else "decisions"
    print(str(entries) + " " + word + " sealed, handoff ready: frugalflow resume")
    return 0


def _run_autotest():
    """Two proofs: close on a fresh vault (exit 0 + sealed), close without a vault (exit 3)."""
    tmp_dir = tempfile.mkdtemp()
    try:
        failures = 0

        # Proof 1: a vault made by vault_new.py closes with exit 0 and the sealed line.
        proj_dir = os.path.join(tmp_dir, "PROJ")
        vault_dir = os.path.join(proj_dir, "vault")
        new = subprocess.run(
            [sys.executable, "-I", os.path.join(BIN, "vault_new.py"),
             "--root", proj_dir, "--name", "demo"],
            capture_output=True, text=True
        )
        close = subprocess.run(
            [sys.executable, "-I", os.path.abspath(__file__), "--vault", vault_dir],
            capture_output=True, text=True
        )
        ok1 = (
            new.returncode == 0
            and close.returncode == 0
            and "VAULT OK" in close.stdout
            and "sealed" in close.stdout
            and "frugalflow resume" in close.stdout
        )
        if not ok1:
            failures += 1
        print(("PASS" if ok1 else "FAIL") + " proof 1: close on a fresh vault: expected exit 0 + sealed, got exit "
              + str(close.returncode) + " and " + repr(close.stdout.splitlines()[-1] if close.stdout else ""))

        # Proof 2: a vault that does not exist is refused with exit 3.
        missing = subprocess.run(
            [sys.executable, "-I", os.path.abspath(__file__),
             "--vault", os.path.join(tmp_dir, "absent")],
            capture_output=True, text=True
        )
        ok2 = missing.returncode == 3 and "NO VAULT" in missing.stdout
        if not ok2:
            failures += 1
        print(("PASS" if ok2 else "FAIL") + " proof 2: close without a vault: expected exit 3 + NO VAULT, got exit "
              + str(missing.returncode))

        return 0 if failures == 0 else 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
