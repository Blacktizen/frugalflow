#!/usr/bin/env python3
"""Hidden oracle for p13: sum the sizes of the .log files only."""
import os
import subprocess
import sys
import tempfile

CASES = [
    ({"a.log": b"1234567890", "b.txt": b"x" * 100, "c.log": b"y" * 20, "d.md": b"z" * 5}, "30\n"),
    ({"x.txt": b"1234567"}, "0\n"),
]


def run(prog, files):
    with tempfile.TemporaryDirectory() as d:
        for name, content in files.items():
            with open(os.path.join(d, name), "wb") as f:
                f.write(content)
        proc = subprocess.run(
            [sys.executable, prog, d],
            capture_output=True, text=True, timeout=20,
        )
        return proc


def main():
    prog = sys.argv[1]
    for i, (files, want) in enumerate(CASES, 1):
        proc = run(prog, files)
        got = proc.stdout
        if proc.returncode != 0 or got != want:
            print("FAIL case %d: expected %r, got %r (exit %d)"
                  % (i, want, got, proc.returncode))
            sys.exit(1)
        print("PASS case %d" % i)
    sys.exit(0)


if __name__ == "__main__":
    main()
