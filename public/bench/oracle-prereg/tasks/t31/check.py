import sys
sys.path.insert(0, ".")

TASK = "normalize_path"

cases = [
    ("//foo//bar", "/foo/bar"),
    ("/foo/./bar", "/foo/bar"),
    ("/foo/bar/../baz", "/foo/baz"),
    ("/../..", "/"),
    ("/..", "/"),
    ("../foo/bar", "../foo/bar"),
    ("../../foo", "../../foo"),
    ("/foo/bar/", "/foo/bar"),
    ("foo/", "foo"),
    ("/", "/"),
    ("//", "/"),
    ("", "."),
    ("foo/..", "."),
    (".", "."),
    ("foo/../../bar", "../bar"),
    ("/a/./b/./c", "/a/b/c"),
    ("/foo//bar", "/foo/bar"),
    ("a/./b/../c", "a/c"),
]

try:
    from paths import normalize_path
except Exception:
    print("FAIL " + TASK + " | case import | expected module import | obtained ImportError")
    sys.exit(1)

discrepancies = []

for idx, (inp, expected) in enumerate(cases):
    try:
        obtained = normalize_path(inp)
    except Exception as e:
        obtained = "<EXC:" + repr(e) + ">"
    if obtained != expected:
        discrepancies.append((idx, expected, obtained))
        if len(discrepancies) >= 3:
            break

if discrepancies:
    msg = "FAIL " + TASK
    for (case_idx, expected, obtained) in discrepancies[:3]:
        msg += " | case " + str(case_idx) + " | expected " + repr(expected) + " | obtained " + repr(obtained)
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
