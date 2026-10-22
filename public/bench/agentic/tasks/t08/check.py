import sys

from durations import parse_duration

good = [
    ("1h30m", 5400),
    ("90s", 90),
    ("2d", 172800),
    ("1d2h3m4s", 93784),
    ("1H30M", 5400),
    ("1h 30m", 5400),
    ("  2 d 4 h ", 187200),
    ("0s", 0),
    ("2D", 172800),
    ("  90S  ", 90),
]

for text, expected in good:
    try:
        got = parse_duration(text)
    except Exception as e:
        print("FAIL", repr(text), "raised", type(e).__name__, str(e))
        sys.exit(1)
    if got != expected:
        print("FAIL", repr(text), "got", got, "expected", expected)
        sys.exit(1)

bad = ["", "   ", "90", "1x", "1d2x", "h", "1h 2", "12.5s", "-5s"]
for text in bad:
    try:
        parse_duration(text)
    except ValueError:
        continue
    except Exception as e:
        print("FAIL", repr(text), "raised non-ValueError", type(e).__name__, str(e))
        sys.exit(1)
    print("FAIL", repr(text), "did not raise ValueError")
    sys.exit(1)

print("PASS")
