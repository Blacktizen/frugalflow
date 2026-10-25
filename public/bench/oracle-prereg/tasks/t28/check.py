import sys
import traceback

TASK = "envexp"
discrepancies = []

def check(name, fn):
    try:
        from envexp import env_expand
    except ImportError:
        print("FAIL " + TASK + " cannot import envexp")
        sys.exit(1)
    try:
        fn()
    except AssertionError as e:
        discrepancies.append(name + " | expected vs obtained")
        return False
    except Exception as e:
        discrepancies.append(name + " | unexpected exception: " + str(e))
        return False
    return True

def t1():
    from envexp import env_expand
    assert env_expand("${VAR}", {"VAR": "hello"}) == "hello"

def t2():
    from envexp import env_expand
    assert env_expand("${ABSENT}", {}) == ""

def t3():
    from envexp import env_expand
    assert env_expand("${X:-def}", {}) == "def"

def t4():
    from envexp import env_expand
    assert env_expand("${X:-def}", {"X": ""}) == "def"

def t5():
    from envexp import env_expand
    assert env_expand("${X:-def}", {"X": "val"}) == "val"

def t6():
    from envexp import env_expand
    assert env_expand("$$", {}) == "$"

def t7():
    from envexp import env_expand
    assert env_expand("price$", {}) == "price$"

def t8():
    from envexp import env_expand
    assert env_expand("$VAR", {"VAR": "x"}) == "$VAR"

def t9():
    from envexp import env_expand
    assert env_expand("${A}", {"A": "${B}"}) == "${B}"

def t10():
    from envexp import env_expand
    try:
        env_expand("${VAR", {})
        assert False, "expected ValueError"
    except ValueError:
        pass

def t11():
    from envexp import env_expand
    assert env_expand("$$${VAR}", {"VAR": "hi"}) == "$hi"

def t12():
    from envexp import env_expand
    assert env_expand("a${X}b${Y}c", {"X": "1", "Y": "2"}) == "a1b2c"

def t13():
    from envexp import env_expand
    assert env_expand("${X:-}", {}) == ""

def t14():
    from envexp import env_expand
    assert env_expand("a$b", {}) == "a$b"

def t15():
    from envexp import env_expand
    assert env_expand("${X:-a:b}", {}) == "a:b"

def t16():
    from envexp import env_expand
    try:
        env_expand("${X:-fallback", {})
        assert False, "expected ValueError"
    except ValueError:
        pass

def t17():
    from envexp import env_expand
    assert env_expand("${X:-def}", {"X": "val"}) == "val"

def t18():
    from envexp import env_expand
    assert env_expand("$$$", {}) == "$$"

def t19():
    from envexp import env_expand
    assert env_expand("$$${A:-d}", {"A": ""}) == "$d"

tests = [
    ("t1_basic", t1),
    ("t2_absent", t2),
    ("t3_default_absent", t3),
    ("t4_default_empty", t4),
    ("t5_default_present", t5),
    ("t6_dollar_dollar", t6),
    ("t7_isolated_dollar", t7),
    ("t8_no_braces", t8),
    ("t9_no_recursive", t9),
    ("t10_unclosed", t10),
    ("t11_dd_expansion", t11),
    ("t12_multiple", t12),
    ("t13_empty_default", t13),
    ("t14_dollar_mid", t14),
    ("t15_colon_in_default", t15),
    ("t16_unclosed_with_default", t16),
    ("t17_present_not_empty", t17),
    ("t18_triple_dollar", t18),
    ("t19_dd_empty_default", t19),
]

fail_count = 0
for name, fn in tests:
    if not check(name, fn):
        fail_count += 1

if fail_count > 0:
    parts = discrepancies[:3]
    msg = "FAIL " + TASK + " "
    for p in parts:
        msg += p[:200] + " | "
    msg = msg[:600]
    print(msg)
    sys.exit(1)

print("PASS")
sys.exit(0)
