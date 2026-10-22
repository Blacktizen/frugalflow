#!/usr/bin/env python3
"""Hidden oracle for p03: count events strictly after a threshold date (DD/MM/YYYY)."""
import subprocess
import sys
import tempfile
import os

CASES = [
    ("15/01/2024,launch\n01/06/2024,review\n10/03/2025,ship\n", ["31/12/2024"], "1\n"),
    ("01/01/2023,a\n05/05/2024,b\n", ["01/06/2023"], "1\n"),
    ("01/01/2020,x\n01/01/2019,y\n", ["01/01/2021"], "0\n"),
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
