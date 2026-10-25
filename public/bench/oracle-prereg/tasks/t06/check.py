import sys

TASK_ID = "wrap_text"
failures = []

def check(label, expected, obtained):
    if expected != obtained:
        failures.append((label, expected, obtained))

def expect_raises(label, fn, exc_type):
    try:
        fn()
        failures.append((label, exc_type.__name__ + " raised", "no exception"))
    except exc_type:
        pass
    except Exception as e:
        failures.append((label, exc_type.__name__ + " raised", type(e).__name__))

try:
    from wrap import wrap_text
except ImportError as e:
    print("FAIL " + TASK_ID + " case=import expected=module obtained=" + str(e)[:600])
    sys.exit(1)

cases = [
    # 1 basic fit
    ("1", wrap_text("hello world", 11), ["hello world"]),
    # 2 greedy wrap on spaces
    ("2", wrap_text("hello world", 5), ["hello", "world"]),
    # 3 multiple spaces reduced to one
    ("3", wrap_text("a   b", 10), ["a b"]),
    # 4 word longer than width cut into exact chunks
    ("4", wrap_text("abcdef", 3), ["abc", "def"]),
    # 5 long word partial last chunk
    ("5", wrap_text("abcdefgh", 3), ["abc", "def", "gh"]),
    # 6 paragraph separation by newline
    ("6", wrap_text("hello\nworld", 10), ["hello", "world"]),
    # 7 empty paragraph between two paragraphs
    ("7", wrap_text("a\n\nb", 10), ["a", "", "b"]),
    # 8 empty text yields one empty line
    ("8", wrap_text("", 10), [""]),
    # 9 single newline yields two empty paragraphs
    ("9", wrap_text("\n", 10), ["", ""]),
    # 10 width < 1 raises ValueError
    ("10", None, None),
    # 11 width = -1 raises ValueError
    ("11", None, None),
    # 12 word exactly width fits on one line
    ("12", wrap_text("hello", 5), ["hello"]),
    # 13 no line exceeds width with multiple spaces
    ("13", wrap_text("ab  cd  ef", 5), ["ab cd", "ef"]),
    # 14 long word inside paragraph boundary
    ("14", wrap_text("abcdefgh\nx", 3), ["abc", "def", "gh", "x"]),
    # 15 spaces-only text yields empty line
    ("15", wrap_text("   ", 10), [""]),
]

# case 10
expect_raises("10", lambda: wrap_text("abc", 0), ValueError)
# case 11
expect_raises("11", lambda: wrap_text("abc", -1), ValueError)

# collect non-None cases
for label, expected, obtained in cases:
    if expected is not None:
        check(label, expected, obtained)

if failures:
    parts = []
    for label, expected, obtained in failures[:3]:
        parts.append("case=" + label + " expected=" + str(expected) + " obtained=" + str(obtained))
    msg = "FAIL " + TASK_ID + " " + " | ".join(parts)
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
