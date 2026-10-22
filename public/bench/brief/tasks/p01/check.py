#!/usr/bin/env python3
"""Hidden oracle for p01: sum the count column of a semicolon-separated file."""
import subprocess
import sys
import tempfile
import os

CASES = [
    ("alice;3\nbob;5\ncarol;7\n", [], "15\n"),
    ("x;10\ny;20\nz;30\n", [], "60\n"),
    ("solo;0\n", [], "0\n"),
]


def run(prog, infile, args):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "in.txt")
        with open(path, "w") as f:
            f.write(infile)
        proc = subprocess.run(
            [sys.executable, prog, path] + args,
            capture_output=True, text=True, timeout=20,
        )
        return proc


def main():
    prog = sys.argv[1]
    for i, (infile, args, want) in enumerate(CASES, 1):
        proc = run(prog, infile, args)
        got = proc.stdout
        if proc.returncode != 0 or got != want:
            print("FAIL case %d: expected %r, got %r (exit %d)"
                  % (i, want, got, proc.returncode))
            sys.exit(1)
        print("PASS case %d" % i)
    sys.exit(0)


if __name__ == "__main__":
    main()
