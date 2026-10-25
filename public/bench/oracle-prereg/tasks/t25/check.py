import sys

def main():
    try:
        from bucket import TokenBucket
    except Exception as e:
        print("FAIL TASK_BUCKET import: " + str(e)[:600])
        sys.exit(1)

    discrepancies = []

    def check(name, expected, obtained):
        if expected != obtained:
            discrepancies.append((name, repr(expected), repr(obtained)))

    # 1: starts full, first call True
    b = TokenBucket(5, 1.0)
    check("1", True, b.allow(0.0))

    # 2: normal refill over 1s
    check("2", True, b.allow(1.0))

    # 3: boundary balance == cost -> True
    b2 = TokenBucket(3, 1.0)
    b2.allow(0.0)
    b2.allow(1.0)
    check("3", True, b2.allow(2.0, 3))

    # 4: denial when balance < cost, no deduction
    b3 = TokenBucket(2, 1.0)
    b3.allow(0.0)
    check("4", False, b3.allow(0.0, 2))

    # 5: refill capped at capacity
    b4 = TokenBucket(5, 100.0)
    b4.allow(0.0)
    check("5", True, b4.allow(10.0, 5))

    # 6: cost > capacity always False (after long refill)
    b5 = TokenBucket(5, 100.0)
    b5.allow(0.0)
    check("6", False, b5.allow(10.0, 6))

    # 7: now recules: no refill, last_now unchanged, balance intact
    b6 = TokenBucket(10, 10.0)
    check("7a", True, b6.allow(5.0))
    check("7b", True, b6.allow(3.0))

    # 8: after backward time, forward time uses correct last_now
    b7 = TokenBucket(10, 1.0)
    b7.allow(5.0)
    b7.allow(3.0)
    check("8", True, b7.allow(5.0))

    # 9: cost > capacity on very first call, no side effects on state
    b8 = TokenBucket(3, 1.0)
    check("9", False, b8.allow(0.0, 4))
    check("9b", True, b8.allow(1.0))

    # 10: now == last_now no refill
    b9 = TokenBucket(5, 2.0)
    b9.allow(0.0)
    check("10", True, b9.allow(0.0))

    # 11: refill_per_sec = 0 never refills
    b10 = TokenBucket(3, 0.0)
    check("11a", True, b10.allow(0.0))
    check("11b", True, b10.allow(100.0))
    check("11c", False, b10.allow(200.0, 3))

    # 12: multiple sequential denials no accumulation
    b11 = TokenBucket(1, 1.0)
    b11.allow(0.0)
    check("12a", False, b11.allow(0.0, 2))
    check("12b", False, b11.allow(0.0, 2))
    check("12c", True, b11.allow(1.0, 1))

    # 13: cost=0 always True
    b12 = TokenBucket(5, 1.0)
    check("13", True, b12.allow(0.0, 0))

    # 14: capacity=1 single token then wait for refill
    b13 = TokenBucket(1, 1.0)
    check("14a", True, b13.allow(0.0))
    check("14b", False, b13.allow(0.0))
    check("14c", True, b13.allow(1.0))

    if discrepancies:
        parts = []
        for name, exp, got in discrepancies[:3]:
            parts.append("case=" + name + " expected=" + exp + " obtained=" + got)
        print("FAIL TASK_BUCKET " + " | ".join(parts)[:600])
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
