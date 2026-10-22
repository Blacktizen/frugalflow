import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from cfg import types
    assert types.is_int("12") is True
    assert types.is_int("-3") is True
    assert types.is_int("12.0") is False
    assert types.is_int("") is False
    assert types.is_int(12) is False
    assert types.is_float("1.5") is True
    assert types.is_float("1e3") is True
    assert types.is_float("abc") is False
    assert types.is_bool("TRUE") is True
    assert types.is_bool(" yes ") is True
    assert types.is_bool("on") is False
    assert types.is_bool(1) is False

def item2():
    from cfg import get
    assert get.get({"a": 1}, "a", 9) == 1
    assert get.get({"a": 1}, "b", 9) == 9
    assert get.get({"a": None}, "a", 9) == 9
    assert get.get({}, "x") is None

def item3():
    from cfg import intval
    assert intval.to_int(None, 5, 0, 10) == 5
    assert intval.to_int("7", 0, 0, 10) == 7
    assert intval.to_int(7, 0, 0, 10) == 7
    for bad in ["11", "abc", True]:
        try:
            intval.to_int(bad, 0, 0, 10)
            raise AssertionError("bad value accepted")
        except ValueError:
            pass

def item4():
    from cfg import schema
    assert schema.check({"a": 5}, {"a": lambda v: v > 0, "b": lambda v: v > 0}) == ["b"]
    assert schema.check({"a": -1}, {"a": lambda v: v > 0}) == ["a"]
    assert schema.check({}, {"a": lambda v: True, "b": lambda v: True}) == ["a", "b"]
    assert schema.check({"a": 1}, {"a": lambda v: v > 0}) == []

def item5():
    from cfg import merge
    assert merge.merge({"a": 1, "b": 2}, {"b": 3, "c": 4}) == {"a": 1, "b": 3, "c": 4}
    assert merge.merge({"a": 1}, {"a": None}) == {"a": 1}
    base = {"a": 1}
    merge.merge(base, {"b": 2})
    assert base == {"a": 1}

def item6():
    from cfg import defaults
    assert defaults.with_defaults({"a": 1}, {"a": 9, "b": 2}) == {"a": 1, "b": 2}
    assert defaults.with_defaults({"a": None}, {"a": 9}) == {"a": 9}
    assert defaults.with_defaults({}, {"b": 2}) == {"b": 2}

check(1, item1)
check(2, item2)
check(3, item3)
check(4, item4)
check(5, item5)
check(6, item6)

if FAILED:
    print("FAIL " + " ".join(str(n) for n in FAILED))
    sys.exit(1)
print("PASS")
sys.exit(0)
