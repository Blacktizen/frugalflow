import sys

from csvline import split_line

cases = [
    ("plain", "a,b,c", ["a", "b", "c"]),
    ("quoted comma", '"a,b",c', ["a,b", "c"]),
    ("doubled quotes", '"a""b",c', ['a"b', "c"]),
    ("trailing comma", "a,b,", ["a", "b", ""]),
    ("empty fields", ",,", ["", "", ""]),
    ("quoted empty middle", '"x",,"y"', ["x", "", "y"]),
    ("quotes with spaces", '"say ""hi"" now",2', ['say "hi" now', "2"]),
]

for label, inp, expected in cases:
    try:
        got = split_line(inp)
    except Exception as e:
        print("FAIL", label, "raised", type(e).__name__, str(e))
        sys.exit(1)
    if got != expected:
        print("FAIL", label, "got", got, "expected", expected)
        sys.exit(1)

print("PASS")
