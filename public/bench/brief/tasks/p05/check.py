#!/usr/bin/env python3
"""Hidden oracle for p05: sum counts whose CSV fields are double-quoted."""
import subprocess
import sys
import tempfile
import os

CASES = [
    ('"alice","3"\n"bob","5"\n"carol","7"\n', [], "15\n"),
    ('"x","10"\n"y","20"\n', [], "30\n"),
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
