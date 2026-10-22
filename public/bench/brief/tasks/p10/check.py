#!/usr/bin/env python3
"""Hidden oracle for p10: read a nested extension list and filter file names."""
import json
import os
import subprocess
import sys
import tempfile

CASES = [
    ({"filters": {"allowed": {"extensions": [".txt", ".md"]}}},
     "a.txt\nb.pdf\nc.md\nd.csv\n", "a.txt\nc.md\n"),
    ({"filters": {"allowed": {"extensions": [".py"]}}},
     "x.py\ny.txt\n", "x.py\n"),
]


def run(prog, cfg, stdin_text):
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "config.json")
        with open(path, "w") as f:
            json.dump(cfg, f)
        proc = subprocess.run(
            [sys.executable, prog, path],
            input=stdin_text, capture_output=True, text=True, timeout=20,
        )
        return proc


def main():
    prog = sys.argv[1]
    for i, (cfg, stdin_text, want) in enumerate(CASES, 1):
        proc = run(prog, cfg, stdin_text)
        got = proc.stdout
        if proc.returncode != 0 or got != want:
            print("FAIL case %d: expected %r, got %r (exit %d)"
                  % (i, want, got, proc.returncode))
            sys.exit(1)
        print("PASS case %d" % i)
    sys.exit(0)


if __name__ == "__main__":
    main()
