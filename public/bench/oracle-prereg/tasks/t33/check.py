import sys

TASK = "hist"

try:
    from hist import histogram
except Exception as exc:
    print(f"FAIL {TASK} import error: {exc}"[:600])
    sys.exit(1)

cases = [
    (1, "basic", lambda: histogram([1, 3, 7], [0, 5, 10]), [2, 1]),
    (2, "last bin closed", lambda: histogram([10], [0, 5, 10]), [0, 1]),
    (3, "value at e0", lambda: histogram([0], [0, 5, 10]), [1, 0]),
    (4, "value at e1 boundary", lambda: histogram([5], [0, 5, 10]), [0, 1]),
    (5, "edges not strictly increasing equal", lambda: histogram([1], [0, 5, 5, 10]), ValueError),
    (6, "edges decreasing", lambda: histogram([1], [10, 5, 0]), ValueError),
    (7, "single edge", lambda: histogram([1], [5]), ValueError),
    (8, "empty edges", lambda: histogram([1], []), ValueError),
    (9, "nan ignored single", lambda: histogram([float("nan"), 3], [0, 5, 10]), [1, 0]),
    (10, "nan ignored multiple", lambda: histogram([float("nan"), float("nan"), 3, 7], [0, 5, 10]), [1, 1]),
    (11, "below e0 ignored", lambda: histogram([-1, -5], [0, 5, 10]), [0, 0]),
    (12, "above e_last ignored", lambda: histogram([11, 20], [0, 5, 10]), [0, 0]),
    (13, "empty values", lambda: histogram([], [0, 5, 10]), [0, 0]),
    (14, "single bin closed", lambda: histogram([1, 2, 3], [0, 10]), [3]),
    (15, "multi-bin boundary values", lambda: histogram([0, 1, 2], [0, 1, 2, 3]), [1, 1, 1]),
    (16, "negative last bin closed", lambda: histogram([0], [-10, -5, 0]), [0, 1]),
]

discrepancies = []

for case_id, label, fn, expected in cases:
    try:
        if isinstance(expected, type) and issubclass(expected, Exception):
            try:
                result = fn()
                discrepancies.append((case_id, label, f"expected {expected.__name__}", f"got {result}"))
            except expected:
                pass
        else:
            result = fn()
            if result != expected:
                discrepancies.append((case_id, label, f"expected {expected}", f"got {result}"))
    except Exception as exc:
        discrepancies.append((case_id, label, f"expected {expected}", f"raised {exc}"))

if discrepancies:
    summary = "; ".join(f"case {c[0]}({c[1]}): {c[2]} / {c[3]}" for c in discrepancies[:3])
    print(f"FAIL {TASK}: {summary}"[:600])
    sys.exit(1)

print("PASS")
