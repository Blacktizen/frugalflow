#!/usr/bin/env python3
"""Hidden oracle for p11: read a nested flag and transform lines."""
import json
import os
import subprocess
import sys
import tempfile

CASES = [
    ({"features": {"logging": {"enabled": True}}}, "a\nb\n", "LOG: a\nLOG: b\n"),
    ({"features": {"logging": {"enabled": False}}}, "a\nb\n", "a\nb\n"),
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
