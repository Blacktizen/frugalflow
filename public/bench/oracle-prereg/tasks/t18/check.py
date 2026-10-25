import sys

try:
    from brackets import balanced
except Exception as e:
    print("FAIL TASK01 import error: " + str(e)[:600])
    sys.exit(1)

# Each case: (input, expected)
cases = [
    # 1: basic open/close
    ("()", True),
    # 2: proper nesting
    ("([{}])", True),
    # 3: incorrect nesting (mismatched open)
    ("([)]", False),
    # 4: unclosed open bracket
    ("(", False),
    # 5: unmatched close bracket
    (")", False),
    # 6: bracket inside single-quoted string is ignored
    ("'('", True),
    # 7: brackets inside double-quoted string are ignored
    ("\"()\"", True),
    # 8: backslash inside string escapes the closing quote -> unterminated -> False
    ("'\\'", False),
    # 9: double backslash in single-quoted string -> escaped backslash, quote closes -> True
    ("'\\\\'", True),
    # 10: escaped quote outside string -> quote does not start string -> True
    ("\\\"", True),
    # 11: escaped open paren outside string -> not a bracket -> True
    ("\\(", True),
    # 12: open paren, escaped close paren does not match -> False
    ("(\\)", False),
    # 13: backslash in single-quoted string escapes closing quote -> unterminated -> False
    ("'\\')", False),
    # 14: backslash in double-quoted string escapes closing quote -> unterminated -> False
    ("\"\\\"", False),
    # 15: double backslash in double-quoted string -> escaped backslash, quote closes -> True
    ("\"\\\\\"", True),
    # 16: empty string
    ("", True),
]

fails = []
for idx, (inp, expected) in enumerate(cases):
    try:
        got = balanced(inp)
    except Exception as e:
        got = "EXCEPTION:" + str(e)
    if got != expected:
        fails.append((idx, expected, got))

if fails:
    parts = []
    for f in fails[:3]:
        parts.append("case %d expected=%s got=%s" % (f[0], f[1], str(f[2])))
    msg = "FAIL TASK01 " + " | ".join(parts)
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
