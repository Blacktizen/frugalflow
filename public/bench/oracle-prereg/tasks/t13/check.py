import sys

TASK_ID = "split_bill"

def run():
    failures = []
    try:
        from bill import split_bill
    except Exception as e:
        print("FAIL %s import error: %s" % (TASK_ID, str(e)))
        sys.exit(1)

    def check(label, expected, obtained):
        if expected != obtained:
            failures.append((label, expected, obtained))

    def expect_error(label, exc_type, fn):
        try:
            fn()
            failures.append((label, exc_type.__name__, "no exception"))
        except exc_type:
            pass
        except Exception as e:
            failures.append((label, exc_type.__name__, type(e).__name__ + ": " + str(e)))

    cases = []

    # 1 positive with remainder
    cases.append(("pos_rem", lambda: check("pos_rem", [4, 3, 3], split_bill(10, 3))))
    # 2 positive divisible
    cases.append(("pos_div", lambda: check("pos_div", [5, 5], split_bill(10, 2))))
    # 3 positive n=1
    cases.append(("pos_n1", lambda: check("pos_n1", [7], split_bill(7, 1))))
    # 4 zero total
    cases.append(("zero", lambda: check("zero", [0, 0, 0, 0], split_bill(0, 4))))
    # 5 negative with remainder
    cases.append(("neg_rem", lambda: check("neg_rem", [-4, -3, -3], split_bill(-10, 3))))
    # 6 negative divisible
    cases.append(("neg_div", lambda: check("neg_div", [-5, -5], split_bill(-10, 2))))
    # 7 negative n=1
    cases.append(("neg_n1", lambda: check("neg_n1", [-7], split_bill(-7, 1))))
    # 8 negative most-negative-first ordering
    cases.append(("neg_order", lambda: check("neg_order", [-4, -4, -3], split_bill(-11, 3))))
    # 9 n=0 raises ValueError
    cases.append(("n0", lambda: expect_error("n0", ValueError, lambda: split_bill(10, 0))))
    # 10 n=-1 raises ValueError
    cases.append(("neg_n", lambda: expect_error("neg_n", ValueError, lambda: split_bill(10, -1))))
    # 11 large remainder distribution
    cases.append(("pos_big", lambda: check("pos_big", [34, 33, 33], split_bill(100, 3))))
    # 12 small total large n
    cases.append(("small_n", lambda: check("small_n", [1, 1, 1, 1, 1, 0, 0, 0, 0, 0], split_bill(5, 10))))
    # 13 sum exactness positive
    cases.append(("sum_pos", lambda: check("sum_pos", 17, sum(split_bill(17, 5)))))
    # 14 sum exactness negative
    cases.append(("sum_neg", lambda: check("sum_neg", -17, sum(split_bill(-17, 5)))))
    # 15 negative zero total with n>0
    cases.append(("neg_zero", lambda: check("neg_zero", [0, 0, 0], split_bill(0, 3))))

    for _, fn in cases:
        try:
            fn()
        except Exception as e:
            failures.append((TASK_ID, "exception", str(e)))

    if failures:
        line = "FAIL %s " % TASK_ID
        for (label, exp, got) in failures[:3]:
            line += "|%s|expected=%s|got=%s|" % (label, str(exp), str(got))
        print(line[:600])
        sys.exit(1)
    print("PASS")
    sys.exit(0)

run()
