import sys

FAILED = []

def near(a, b):
    return abs(a - b) < 1e-9

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from conv import length
    assert length.convert(1, "km", "m") == 1000.0
    assert length.convert(100, "cm", "m") == 1.0
    assert near(length.convert(1, "mi", "km"), 1.609344)
    assert length.convert(0, "m", "km") == 0.0
    try:
        length.convert(1, "m", "inch")
        raise AssertionError("unknown unit accepted")
    except ValueError:
        pass

def item2():
    from conv import mass
    assert mass.convert(1, "kg", "g") == 1000.0
    assert near(mass.convert(1, "lb", "kg"), 0.45359237)
    try:
        mass.convert(1, "kg", "stone")
        raise AssertionError("unknown unit accepted")
    except ValueError:
        pass

def item3():
    from conv import temp
    assert temp.c_to_f(0) == 32.0
    assert temp.c_to_f(100) == 212.0
    assert temp.f_to_c(32) == 0.0
    assert temp.f_to_c(212) == 100.0
    assert temp.c_to_k(0) == 273.15

def item4():
    from conv import time
    assert time.to_hours(3600, "s") == 1.0
    assert time.to_hours(30, "min") == 0.5
    assert time.to_hours(1, "day") == 24.0
    try:
        time.to_hours(1, "week")
        raise AssertionError("unknown unit accepted")
    except ValueError:
        pass

def item5():
    from conv import format
    assert format.fmt(0, "m") == "0 m"
    assert format.fmt(1000, "m") == "1000 m"
    assert format.fmt(1.5, "kg") == "1.5 kg"
    assert format.fmt(2.0, "s") == "2 s"

def item6():
    from conv import square
    assert square.area(3, "m") == (9, "m2")
    assert square.area(0, "km") == (0, "km2")

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
