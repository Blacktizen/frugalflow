import sys

TASK_ID = "ranges_from_ints"

def run_tests():
    discrepancies = []

    test_cases = [
        # (description, input, expected)
        ("empty list", [], ""),
        ("single element", [5], "5"),
        ("single negative", [-5], "-5"),
        ("three consecutive", [1, 2, 3], "1-3"),
        ("two consecutive positive", [4, 5], "4,5"),
        ("two consecutive negative", [-2, -1], "-2,-1"),
        ("three consecutive negative", [-3, -2, -1], "-3--1"),
        ("unordered with duplicates", [5, 3, 4, 1, 2], "1-5"),
        ("duplicates only", [1, 1, 1, 1], "1"),
        ("mixed ranges", [1, 2, 3, 5, 7, 8, 9], "1-3,5,7-9"),
        ("two non-consecutive", [1, 3], "1,3"),
        ("large consecutive run", [1, 2, 3, 10, 11, 12, 13], "1-3,10-13"),
        ("negative crossing zero three", [-1, 0, 1], "-1-1"),
        ("negative crossing zero two", [0, 1], "0,1"),
        ("two separate pairs", [1, 2, 10, 11], "1,2,10,11"),
        ("unordered duplicates in range", [4, 3, 2, 4, 1], "1-4"),
    ]

    try:
        from compress import ranges_from_ints
    except ImportError as e:
        msg = "FAIL " + TASK_ID + " | import error: " + str(e)[:200]
        print(msg[:600])
        sys.exit(1)

    for i, (desc, inp, expected) in enumerate(test_cases):
        try:
            result = ranges_from_ints(inp)
            if result != expected:
                discrepancies.append((desc, expected, result))
        except Exception as e:
            discrepancies.append((desc, expected, "EXC:" + str(e)))
        if len(discrepancies) >= 3:
            break

    if discrepancies:
        parts = ["FAIL " + TASK_ID]
        for desc, expected, obtained in discrepancies[:3]:
            parts.append("case: " + desc + " | expected: " + repr(expected)[:180] + " | obtained: " + repr(obtained)[:180])
        print(" | ".join(parts)[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run_tests()
