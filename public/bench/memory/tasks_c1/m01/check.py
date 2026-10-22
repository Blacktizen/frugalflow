import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from stock import parse
    assert parse.parse_line("widget,12,kg") == ("widget", 12, "kg")
    assert parse.parse_line("bolt,3") == ("bolt", 3, "pcs")
    assert parse.parse_line(" nut , 7 , ") == ("nut", 7, "pcs")
    assert parse.parse_line("a,0") == ("a", 0, "pcs")
    for bad in ["x,-1,kg", "x,abc", ",5", "", "a,1,kg,extra"]:
        try:
            parse.parse_line(bad)
            raise AssertionError("no error for " + bad)
        except ValueError:
            pass

def item2():
    from stock import stats
    assert stats.total([("a", 2, "kg"), ("a", 3, "kg"), ("b", 1, "pcs")]) == {"a": 5, "b": 1}
    assert stats.total([]) == {}

def item3():
    from stock import report
    assert report.render({"b": 1, "a": 2}) == "a: 2\nb: 1\n"
    assert report.render({}) == ""

def item4():
    from stock import adjust
    totals = {"a": 5}
    out = adjust.apply(totals, "a", 3)
    assert out == {"a": 8} and out is totals
    assert adjust.apply({"a": 5}, "b", 2) == {"a": 5, "b": 2}
    assert adjust.apply({}, "a", 0) == {"a": 0}
    try:
        adjust.apply({"a": 2}, "a", -5)
        raise AssertionError("negative result accepted")
    except ValueError:
        pass

def item5():
    from stock import merge
    left = {"a": 1, "b": 2}
    right = {"b": 3, "c": 4}
    assert merge.merge(left, right) == {"a": 1, "b": 5, "c": 4}
    assert left == {"a": 1, "b": 2} and right == {"b": 3, "c": 4}
    assert merge.merge({}, {}) == {}

def item6():
    from stock import low
    assert low.below({"a": 1, "b": 5, "c": 3}, 4) == ["a", "c"]
    assert low.below({}, 0) == []
    assert low.below({"a": 0}, 1) == ["a"]

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
