import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from backoff import delays
    assert delays.exponential(2, 3, 3) == [2, 6, 18]
    assert delays.exponential(2, 3, 0) == []
    assert delays.exponential(1.5, 2, 3) == [1.5, 3.0, 6.0]
    for bad in [-1, 2.5]:
        try:
            delays.exponential(2, 3, bad)
            raise AssertionError("bad n accepted")
        except ValueError:
            pass

def item2():
    from backoff import caps
    assert caps.cap(5, 10) == 5
    assert caps.cap(15, 10) == 10
    assert caps.cap(0, 0) == 0
    try:
        caps.cap(5, -1)
        raise AssertionError("negative maximum accepted")
    except ValueError:
        pass

def item3():
    from backoff import sums
    assert sums.total([1, 2, 3]) == 6
    assert sums.total([]) == 0.0

def item4():
    from backoff import retry
    assert retry.should_retry(0, 3, ValueError("x"), {ValueError}) is True
    assert retry.should_retry(3, 3, ValueError("x"), {ValueError}) is False
    assert retry.should_retry(0, 3, ValueError("x"), {TypeError}) is False
    assert retry.should_retry(0, 3, TypeError("x"), {ValueError}) is False

def item5():
    from backoff import steps
    assert steps.delay_at(2, 3, 0) == 2
    assert steps.delay_at(2, 3, 2) == 18
    assert steps.delay_at(2, 3, 3) == 54
    try:
        steps.delay_at(2, 3, -1)
        raise AssertionError("negative attempt accepted")
    except ValueError:
        pass

def item6():
    from backoff import budget
    assert budget.within_budget([5, 5, 5], 12) == [5, 5]
    assert budget.within_budget([], 10) == []
    assert budget.within_budget([3, 4, 2], 10) == [3, 4, 2]
    assert budget.within_budget([10, 1], 9) == []

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
