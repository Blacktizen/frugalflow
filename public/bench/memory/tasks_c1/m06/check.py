import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from table import split
    assert split.split("a|b\n1|2") == [["a", "b"], ["1", "2"]]
    assert split.split("|a|b|\n|c|d|") == [["a", "b"], ["c", "d"]]
    assert split.split("") == []
    assert split.split("a||b") == [["a", "", "b"]]
    assert split.split("  a | b  \n\n c|d") == [["a", "b"], ["c", "d"]]

def item2():
    from table import widths
    assert widths.widths([["a", "bb"], ["ccc", "d"]]) == [3, 2]
    assert widths.widths([]) == []
    assert widths.widths([["a"], ["bb", "cc"]]) == [2, 2]

def item3():
    from table import render
    assert render.render([["a", "bb"], ["ccc", "d"]]) == "| a   | bb |\n| --- | -- |\n| ccc | d  |\n"
    assert render.render([]) == ""

def item4():
    from table import align
    assert align.pad("a", 4, "left") == "a   "
    assert align.pad("a", 4, "right") == "   a"
    assert align.pad("a", 4, "center") == " a  "
    assert align.pad("ab", 5, "center") == " ab  "
    try:
        align.pad("a", 4, "x")
        raise AssertionError("unknown align accepted")
    except ValueError:
        pass

def item5():
    from table import escape
    assert escape.escape("a|b") == "a\\|b"
    assert escape.escape("abc") == "abc"
    assert escape.escape("") == ""

def item6():
    from table import markdown
    assert markdown.table("a|b\n1|2") == "| a | b |\n| - | - |\n| 1 | 2 |\n"
    assert markdown.table("") == ""

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
