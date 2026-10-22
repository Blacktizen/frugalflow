import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from plan import slot
    assert slot.parse_time("09:05") == 545
    assert slot.parse_time("00:00") == 0
    assert slot.parse_time("23:59") == 1439
    for bad in ["24:00", "12:60", "9:05", "12:3", "abc", "12", "1:2:3"]:
        try:
            slot.parse_time(bad)
            raise AssertionError("no error for " + bad)
        except ValueError:
            pass

def item2():
    from plan import overlap
    assert overlap.overlap((0, 10), (5, 15)) is True
    assert overlap.overlap((0, 10), (10, 20)) is False
    assert overlap.overlap((0, 10), (20, 30)) is False
    assert overlap.overlap((5, 10), (0, 10)) is True

def item3():
    from plan import fit
    assert fit.find_slot([], 30, 0, 120) == 0
    assert fit.find_slot([(0, 30)], 30, 0, 120) == 30
    assert fit.find_slot([(0, 30), (60, 90)], 30, 0, 120) == 30
    assert fit.find_slot([(10, 20)], 30, 0, 60) == 20
    assert fit.find_slot([(0, 120)], 30, 0, 120) is None
    try:
        fit.find_slot([], 0, 0, 120)
        raise AssertionError("zero duration accepted")
    except ValueError:
        pass

def item4():
    from plan import compress
    assert compress.merge([(0, 10), (5, 15)]) == [(0, 15)]
    assert compress.merge([(0, 10), (10, 20)]) == [(0, 20)]
    assert compress.merge([]) == []
    assert compress.merge([(3, 4), (0, 1)]) == [(0, 1), (3, 4)]
    assert compress.merge([(0, 10), (10, 20), (20, 30)]) == [(0, 30)]

def item5():
    from plan import total
    assert total.total([(0, 10), (10, 20)]) == 20
    assert total.total([]) == 0
    assert total.total([(0, 10), (30, 40)]) == 20

def item6():
    from plan import weekday
    assert weekday.day_index("Mon") == 0
    assert weekday.day_index("sun") == 6
    for bad in ["", "funday"]:
        try:
            weekday.day_index(bad)
            raise AssertionError("no error for " + bad)
        except ValueError:
            pass

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
