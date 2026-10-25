import sys
import math

TASK_ID = "movavg"
discrepancies = []

def run_tests():
    try:
        from movavg import moving_average
    except Exception as e:
        discrepancies.append(("import", "module imports", repr(e)))
        return

    cases = [
        # 1: basic k=2
        (lambda: moving_average([1, 2, 3, 4], 2),
         [1.5, 2.5, 3.5]),
        # 2: k=1 identity
        (lambda: moving_average([1, 2, 3, 4], 1),
         [1.0, 2.0, 3.0, 4.0]),
        # 3: k == len(xs)
        (lambda: moving_average([1, 2, 3, 4], 4),
         [2.5]),
        # 4: k > len(xs) returns []
        (lambda: moving_average([1, 2, 3], 5),
         []),
        # 5: k=0 raises ValueError
        (lambda: moving_average([1, 2, 3], 0),
         "ValueError"),
        # 6: k=-1 raises ValueError
        (lambda: moving_average([1, 2, 3], -1),
         "ValueError"),
        # 7: k=-100 raises ValueError
        (lambda: moving_average([1, 2, 3], -100),
         "ValueError"),
        # 8: empty list k=1 returns []
        (lambda: moving_average([], 1),
         []),
        # 9: single element
        (lambda: moving_average([7.0], 1),
         [7.0]),
        # 10: negative values
        (lambda: moving_average([-1, -2, -3], 2),
         [-1.5, -2.5]),
        # 11: precision - cumulative sum fails here
        (lambda: moving_average([1e16, 1.0, 2.0], 2),
         [math.fsum([1e16, 1.0]) / 2, math.fsum([1.0, 2.0]) / 2]),
        # 12: precision second window with large values
        (lambda: moving_average([1e16, 1e16, 1.0, -1e16, -1e16], 3),
         [math.fsum([1e16, 1e16, 1.0]) / 3,
          math.fsum([1e16, 1.0, -1e16]) / 3,
          math.fsum([1.0, -1e16, -1e16]) / 3]),
        # 13: all zeros
        (lambda: moving_average([0, 0, 0, 0], 2),
         [0.0, 0.0, 0.0]),
        # 14: result length check len(xs)-k+1
        (lambda: len(moving_average(list(range(100)), 10)),
         91),
        # 15: floats in input
        (lambda: moving_average([0.1, 0.2, 0.3], 2),
         [math.fsum([0.1, 0.2]) / 2, math.fsum([0.2, 0.3]) / 2]),
    ]

    for idx, (fn, expected) in enumerate(cases):
        try:
            obtained = fn()
            if expected == "ValueError":
                discrepancies.append((idx, "ValueError raised", "no exception"))
                return
            if obtained != expected:
                discrepancies.append((idx, str(expected)[:120], str(obtained)[:120]))
                return
        except ValueError as e:
            if expected == "ValueError":
                continue
            discrepancies.append((idx, str(expected)[:120], "ValueError: " + str(e)[:120]))
            return
        except Exception as e:
            discrepancies.append((idx, str(expected)[:120], type(e).__name__ + ": " + str(e)[:120]))
            return


run_tests()

if discrepancies:
    msg = "FAIL " + TASK_ID + " | "
    for d in discrepancies[:3]:
        msg += "[" + str(d[0]) + " expected=" + str(d[1]) + " obtained=" + str(d[2]) + "] "
    print(msg[:600])
    sys.exit(1)
else:
    print("PASS")
    sys.exit(0)
