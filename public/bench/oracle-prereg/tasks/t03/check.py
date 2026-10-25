import sys

TASK = "windows-sliding"
discrepancies = []

def run():
    try:
        from chunks import windows
    except Exception as e:
        print("FAIL " + TASK + " | import error: " + str(e))
        sys.exit(1)

    cases = [
        # (description, call, expected, expect_error)
        ("empty seq", lambda: windows([], 3, 0), [], False),
        ("single element size larger", lambda: windows([7], 3, 0), [[7]], False),
        ("no overlap exact fit", lambda: windows([1,2,3,4,5,6], 3, 0), [[1,2,3],[4,5,6]], False),
        ("no overlap trailing partial new", lambda: windows([1,2,3,4,5,6,7], 3, 0), [[1,2,3],[4,5,6],[7]], False),
        ("overlap 1 step 2 full", lambda: windows([1,2,3,4,5,6], 3, 1), [[1,2,3],[3,4,5],[5,6]], False),
        ("overlap 1 trailing partial dup", lambda: windows([1,2,3,4,5], 3, 1), [[1,2,3],[3,4,5]], False),
        ("overlap 1 partial all in prev", lambda: windows([1,2,3,4,5,6,7], 3, 1), [[1,2,3],[3,4,5],[5,6,7]], False),
        ("overlap 2 max step 1", lambda: windows([1,2,3], 3, 2), [[1,2,3]], False),
        ("overlap 2 partial all in prev", lambda: windows([1,2,3,4], 3, 2), [[1,2,3],[2,3,4]], False),
        ("size 4 overlap 1 partial dup", lambda: windows([1,2,3,4], 4, 1), [[1,2,3,4]], False),
        ("size 1 all singles", lambda: windows([1,2,3], 1, 0), [[1],[2],[3]], False),
        ("all same elements partial dup", lambda: windows([1,1,1], 3, 2), [[1,1,1]], False),
        ("overlap 1 new element partial", lambda: windows([1,2,3,4,5,6,7,8], 3, 1), [[1,2,3],[3,4,5],[5,6,7],[7,8]], False),
        ("size 1 invalid size", lambda: windows([1,2,3], 0), None, True),
        ("size -1 invalid", lambda: windows([1,2,3], -1), None, True),
        ("overlap -1 invalid", lambda: windows([1,2,3], 3, -1), None, True),
        ("overlap equals size invalid", lambda: windows([1,2,3], 3, 3), None, True),
        ("overlap greater size invalid", lambda: windows([1,2,3], 3, 5), None, True),
    ]

    case_num = 0
    for (desc, fn, expected, expect_error) in cases:
        case_num += 1
        try:
            result = fn()
            if expect_error:
                discrepancies.append(
                    "case %d '%s': expected ValueError, got %s" % (case_num, desc, str(result))
                )
            else:
                if result != expected:
                    discrepancies.append(
                        "case %d '%s': expected %s, got %s" % (case_num, desc, str(expected), str(result))
                    )
        except ValueError as e:
            if not expect_error:
                discrepancies.append(
                    "case %d '%s': unexpected ValueError: %s" % (case_num, desc, str(e))
                )
        except Exception as e:
            discrepancies.append(
                "case %d '%s': unexpected exception: %s" % (case_num, desc, str(e))
            )

    if discrepancies:
        msg = "FAIL " + TASK + " | " + " | ".join(discrepancies[:3])
        print(msg[:600])
        sys.exit(1)
    else:
        print("PASS")
        sys.exit(0)

run()
