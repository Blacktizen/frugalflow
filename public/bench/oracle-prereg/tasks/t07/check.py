import sys
import os
import copy

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TASK = "flat"

def run():
    try:
        import flat
        from flat import flatten
    except Exception as e:
        print("FAIL " + TASK + " | case: import | expected: module loads | obtained: " + str(e)[:600])
        sys.exit(1)

    cases = []

    # 1 - basic dict flattening
    cases.append(({"a": {"b": 1}}, ".", {"a.b": 1}, None))
    # 2 - list indexing
    cases.append(({"a": [10, 20]}, ".", {"a.0": 10, "a.1": 20}, None))
    # 3 - dict inside list
    cases.append(({"a": [{"b": 1}]}, ".", {"a.0.b": 1}, None))
    # 4 - empty dict as leaf value
    cases.append(({"a": {}}, ".", {"a": {}}, None))
    # 5 - empty list as leaf value
    cases.append(({"a": []}, ".", {"a": []}, None))
    # 6 - top-level empty dict
    cases.append(({}, ".", {}, None))
    # 7 - top-level empty list
    cases.append(([], ".", {}, None))
    # 8 - top-level int -> ValueError
    cases.append((5, ".", None, ValueError))
    # 9 - top-level str -> ValueError
    cases.append(("hello", ".", None, ValueError))
    # 10 - non-str keys converted
    cases.append(({1: "x", 2.5: "y"}, ".", {"1": "x", "2.5": "y"}, None))
    # 11 - deep nesting
    cases.append(({"a": {"b": {"c": 1}}}, ".", {"a.b.c": 1}, None))
    # 12 - mixed list of list
    cases.append(({"a": [1, [2, 3]]}, ".", {"a.0": 1, "a.1.0": 2, "a.1.1": 3}, None))
    # 13 - custom separator
    cases.append(({"a": {"b": 1}}, "__", {"a__b": 1}, None))
    # 14 - top-level float -> ValueError
    cases.append((3.14, ".", None, ValueError))
    # 15 - top-level None -> ValueError
    cases.append((None, ".", None, ValueError))
    # 16 - input not modified
    obj16 = {"a": {"b": [1, 2]}, "c": 3}
    obj16_copy = copy.deepcopy(obj16)
    cases.append((obj16, ".", {"a.b.0": 1, "a.b.1": 2, "c": 3}, None))

    discrepancies = []

    for idx, (inp, sep, expected, exc) in enumerate(cases):
        try:
            if exc is not None:
                try:
                    flatten(inp, sep)
                    discrepancies.append((idx, "raises " + exc.__name__, "no exception"))
                except exc:
                    pass
            else:
                obtained = flatten(inp, sep)
                if obtained != expected:
                    discrepancies.append((idx, repr(expected), repr(obtained)))
                if idx == 15 and inp != obj16_copy:
                    discrepancies.append((15, "input unchanged", "input mutated"))
        except Exception as e:
            if exc is not None:
                discrepancies.append((idx, "raises " + exc.__name__, str(e)[:200]))
            else:
                discrepancies.append((idx, repr(expected), "exception: " + str(e)[:200]))

        # 16 check input not modified
        if idx == 15 and inp != obj16_copy:
            discrepancies.append((15, "input unchanged", "input mutated"))

    if discrepancies:
        parts = []
        for d in discrepancies[:3]:
            parts.append("case " + str(d[0]) + " | expected: " + str(d[1])[:180] + " | obtained: " + str(d[2])[:180])
        msg = " | ".join(parts)
        print("FAIL " + TASK + " | " + msg[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run()
