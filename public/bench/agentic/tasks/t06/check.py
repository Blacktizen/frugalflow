import sys

from textutil import dedupe

cases = [
    ("case insensitive", ["Apple", "apple", "APPLE"], ["Apple"]),
    ("whitespace ignored", ["  hello  ", "hello", "HELLO"], ["  hello  "]),
    ("nfc nfd accents", ["café", "café"], ["café"]),
    ("keeps first unchanged", ["Banana", " APPLE ", "apple", "banana "], ["Banana", " APPLE "]),
    ("order preserved", ["x", " y ", "X", "z"], ["x", " y ", "z"]),
    ("plain unique", ["a", "b", "c"], ["a", "b", "c"]),
]

for label, inp, expected in cases:
    try:
        got = dedupe(inp)
    except Exception as e:
        print("FAIL", label, "raised", type(e).__name__, str(e))
        sys.exit(1)
    if got != expected:
        print("FAIL", label, "got", got, "expected", expected)
        sys.exit(1)

print("PASS")
