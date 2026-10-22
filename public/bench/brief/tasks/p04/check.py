#!/usr/bin/env python3
"""Hidden oracle for p04: print names sorted by count, highest first."""
import subprocess
import sys
import tempfile
import os

CASES = [
    ("alice,3\nbob,9\ncarol,5\n", [], "bob\ncarol\nalice\n"),
    ("x,1\ny,2\nz,3\n", [], "z\ny\nx\n"),
    ("a,7\nb,7\n", [], "a\nb\n"),
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
