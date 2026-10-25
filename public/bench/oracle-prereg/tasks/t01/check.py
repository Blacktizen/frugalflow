import sys
sys.path.insert(0, ".")

TASK = "merge_intervals"

def run():
    failures = []

    try:
        from intervals import merge_intervals
    except Exception as exc:
        print(f"FAIL {TASK}: import error: {exc}")
        sys.exit(1)

    def case(name, fn):
        try:
            fn()
        except Exception as exc:
            failures.append((name, "expected OK", str(exc)))

    def expect_value_error(items):
        try:
            merge_intervals(items)
            failures.append(("start_gt_end", "ValueError", "no exception raised"))
        except ValueError:
            pass
        except Exception as exc:
            failures.append(("start_gt_end", "ValueError", str(exc)))

    def case_empty():
        r = merge_intervals([])
        if r != []:
            failures.append(("empty", "[]", str(r)))

    def case_single():
        r = merge_intervals([(3, 7)])
        if r != [(3, 7)]:
            failures.append(("single", "[(3, 7)]", str(r)))

    def case_overlap():
        r = merge_intervals([(1, 4), (2, 6)])
        if r != [(1, 6)]:
            failures.append(("overlap", "[(1, 6)]", str(r)))

    def case_touch():
        r = merge_intervals([(1, 5), (5, 9)])
        if r != [(1, 9)]:
            failures.append(("touch", "[(1, 9)]", str(r)))

    def case_no_overlap():
        r = merge_intervals([(1, 3), (6, 9)])
        if r != [(1, 3), (6, 9)]:
            failures.append(("no_overlap", "[(1, 3), (6, 9)]", str(r)))

    def case_unsorted_input():
        r = merge_intervals([(7, 9), (1, 4), (3, 6)])
        if r != [(1, 6), (7, 9)]:
            failures.append(("unsorted", "[(1, 6), (7, 9)]", str(r)))

    def case_input_not_modified():
        original = [(5, 8), (1, 3), (2, 6)]
        copy = list(original)
        merge_intervals(original)
        if original != copy:
            failures.append(("input_modified", f"{copy}", str(original)))

    def case_returns_new_list():
        items = [(1, 3), (2, 5)]
        r = merge_intervals(items)
        if r is items:
            failures.append(("same_object", "new list", "returned same object"))

    def case_nested():
        r = merge_intervals([(1, 10), (2, 5)])
        if r != [(1, 10)]:
            failures.append(("nested", "[(1, 10)]", str(r)))

    def case_chain_touch():
        r = merge_intervals([(1, 2), (2, 3), (3, 4)])
        if r != [(1, 4)]:
            failures.append(("chain_touch", "[(1, 4)]", str(r)))

    def case_start_gt_end():
        expect_value_error([(5, 3)])

    def case_start_eq_end():
        r = merge_intervals([(4, 4)])
        if r != [(4, 4)]:
            failures.append(("point", "[(4, 4)]", str(r)))

    def case_negative_ints():
        r = merge_intervals([(-5, -1), (-1, 0)])
        if r != [(-5, 0)]:
            failures.append(("negatives", "[(-5, 0)]", str(r)))

    def case_all_tuples():
        r = merge_intervals([(1, 3), (3, 5)])
        if not all(isinstance(t, tuple) for t in r):
            failures.append(("tuple_type", "all tuples", str(r)))

    def case_multiple_merges():
        r = merge_intervals([(1, 3), (2, 5), (7, 9), (8, 12), (12, 15)])
        if r != [(1, 5), (7, 15)]:
            failures.append(("multi_merge", "[(1, 5), (7, 15)]", str(r)))

    tests = [
        ("empty", case_empty),
        ("single", case_single),
        ("overlap", case_overlap),
        ("touch", case_touch),
        ("no_overlap", case_no_overlap),
        ("unsorted", case_unsorted_input),
        ("input_modified", case_input_not_modified),
        ("returns_new", case_returns_new_list),
        ("nested", case_nested),
        ("chain_touch", case_chain_touch),
        ("start_gt_end", case_start_gt_end),
        ("point", case_start_eq_end),
        ("negatives", case_negative_ints),
        ("tuple_type", case_all_tuples),
        ("multi_merge", case_multiple_merges),
    ]

    for name, fn in tests:
        try:
            fn()
        except Exception as exc:
            failures.append((name, "no exception", str(exc)))

    if failures:
        parts = []
        for name, exp, got in failures[:3]:
            exp = exp[:600]
            got = got[:600]
            parts.append(f"  case={name} expected={exp} obtained={got}")
        print(f"FAIL {TASK}" + "\n" + "\n".join(parts))
        sys.exit(1)
    else:
        print("PASS")
        sys.exit(0)

run()
