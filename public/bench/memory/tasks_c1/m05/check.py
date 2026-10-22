import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from ledger import entry
    assert entry.parse("2026-10-22 coffee 1.50") == ("2026-10-22", "coffee", 1.5)
    assert entry.parse("2026-10-22 coffee beans -5.25") == ("2026-10-22", "coffee beans", -5.25)
    assert entry.parse("2026-10-22 x 0") == ("2026-10-22", "x", 0.0)
    for bad in ["2026-13-01 x 1", "2026-10-32 x 1", "bad x 1", "2026-10-22  1", "2026-10-22 x abc"]:
        try:
            entry.parse(bad)
            raise AssertionError("no error for " + bad)
        except ValueError:
            pass

def item2():
    from ledger import balance
    assert balance.balance([("a", "x", 1.0), ("a", "y", -0.5)]) == 0.5
    assert balance.balance([]) == 0.0

def item3():
    from ledger import filter
    entries = [("2026-10-22", "a", 1.0), ("2026-10-21", "b", 2.0)]
    assert filter.by_date(entries, "2026-10-22") == [("2026-10-22", "a", 1.0)]
    assert filter.by_date(entries, "2026-10-21") == [("2026-10-21", "b", 2.0)]

def item4():
    from ledger import order
    entries = [("2026-10-22", "b", 1.0), ("2026-10-22", "a", 2.0), ("2026-10-21", "c", 3.0)]
    assert order.sorted_entries(entries) == [("2026-10-21", "c", 3.0), ("2026-10-22", "a", 2.0), ("2026-10-22", "b", 1.0)]

def item5():
    from ledger import monthly
    entries = [("2026-10-22", "a", 1.0), ("2026-10-21", "b", 2.0), ("2026-11-01", "c", 3.0)]
    assert monthly.by_month(entries) == {"2026-10": 3.0, "2026-11": 3.0}
    assert monthly.by_month([]) == {}

def item6():
    from ledger import statement
    entries = [("2026-10-22", "coffee", 1.0), ("2026-10-21", "tea", 2.5)]
    assert statement.render(entries) == "2026-10-21 tea 2.5\n2026-10-22 coffee 1.0\n"
    assert statement.render([]) == ""

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
