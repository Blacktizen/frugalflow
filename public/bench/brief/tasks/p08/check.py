#!/usr/bin/env python3
"""Hidden oracle for p08: read a nested suffix from config.json and append it."""
import json
import os
import subprocess
import sys
import tempfile

CASES = [
    ({"output": {"format": {"suffix": ".done"}}}, ["report"], "report.done\n"),
    ({"output": {"format": {"suffix": ".bak"}}}, ["notes"], "notes.bak\n"),
]


def run(prog, cfg, args):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with open(path, "w") as f:
            json.dump(cfg, f)
        proc = subprocess.run(
            [sys.executable, prog, path] + args,
            capture_output=True, text=True, timeout=20,
        )
        return proc


def main():
    prog = sys.argv[1]
    for i, (cfg, args, want) in enumerate(CASES, 1):
        proc = run(prog, cfg, args)
        got = proc.stdout
        if proc.returncode != 0 or got != want:
            print("FAIL case %d: expected %r, got %r (exit %d)"
                  % (i, want, got, proc.returncode))
            sys.exit(1)
        print("PASS case %d" % i)
    sys.exit(0)


if __name__ == "__main__":
    main()
