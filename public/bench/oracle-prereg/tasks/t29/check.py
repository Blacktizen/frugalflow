import sys
import copy

TASK_ID = "transpose_ragged"

def main():
    try:
        from ragged import transpose_ragged
    except Exception as e:
        print("FAIL " + TASK_ID + " | import error: " + str(e)[:600])
        sys.exit(1)

    cases = []

    def add(case_name, func):
        cases.append((case_name, func))

    def c1():
        r = transpose_ragged([])
        return (r == [], repr(r), repr([]))

    def c2():
        r = transpose_ragged([[]])
        return (r == [], repr(r), repr([]))

    def c3():
        r = transpose_ragged([[], []])
        return (r == [], repr(r), repr([]))

    def c4():
        r = transpose_ragged([[1]])
        return (r == [[1]], repr(r), repr([[1]]))

    def c5():
        r = transpose_ragged([[1, 2], [3]])
        return (r == [[1, 3], [2, None]], repr(r), repr([[1, 3], [2, None]]))

    def c6():
        r = transpose_ragged([[1, 2, 3], [4, 5], [6]])
        exp = [[1, 4, 6], [2, 5, None], [3, None, None]]
        return (r == exp, repr(r), repr(exp))

    def c7():
        rows = [[1, 2], [3, 4, 5]]
        snapshot = copy.deepcopy(rows)
        transpose_ragged(rows)
        return (rows == snapshot, repr(rows), repr(snapshot))

    def c8():
        rows = [[1, 2, 3], [4], [5, 6, 7, 8]]
        snapshot = copy.deepcopy(rows)
        transpose_ragged(rows, fill=0)
        return (rows == snapshot, repr(rows), repr(snapshot))

    def c9():
        r = transpose_ragged([[1, 2], [3, 4]])
        is_list = all(type(c) is list for c in r)
        return (is_list, repr([type(c).__name__ for c in r]), repr("list"))

    def c10():
        r = transpose_ragged([[1, 2, 3], [4]], fill=0)
        exp = [[1, 4], [2, 0], [3, 0]]
        return (r == exp, repr(r), repr(exp))

    def c11():
        r = transpose_ragged([[1], [2, 3]], fill="x")
        exp = [[1, 2], ["x", 3]]
        return (r == exp, repr(r), repr(exp))

    def c12():
        r = transpose_ragged([[1, 2, 3, 4], [5]], fill=None)
        exp = [[1, 5], [2, None], [3, None], [4, None]]
        return (r == exp, repr(r), repr(exp))

    def c13():
        r = transpose_ragged([[1, 2], [3, 4], [5, 6]])
        exp = [[1, 3, 5], [2, 4, 6]]
        return (r == exp, repr(r), repr(exp))

    def c14():
        r = transpose_ragged([[1, 2, 3]], fill=None)
        exp = [[1], [2], [3]]
        return (r == exp, repr(r), repr(exp))

    def c15():
        r = transpose_ragged([[], [1]], fill=0)
        exp = [[0, 1]]
        return (r == exp, repr(r), repr(exp))

    add("empty_input", c1)
    add("single_empty_row", c2)
    add("multiple_empty_rows", c3)
    add("single_element", c4)
    add("ragged_basic", c5)
    add("ragged_multi", c6)
    add("no_modify_default_fill", c7)
    add("no_modify_custom_fill", c8)
    add("returns_list_not_tuple", c9)
    add("fill_zero", c10)
    add("fill_string", c11)
    add("long_short_rows", c12)
    add("rectangular", c13)
    add("single_row_multiple_cols", c14)
    add("empty_row_with_data_row", c15)

    discrepancies = []
    for name, func in cases:
        try:
            ok, obtained, expected = func()
            if not ok:
                discrepancies.append((name, expected, obtained))
        except Exception as e:
            discrepancies.append((name, "no exception", str(e)))

    if discrepancies:
        parts = [TASK_ID]
        for name, expected, obtained in discrepancies[:3]:
            parts.append(name + "|" + expected + "|" + obtained)
        line = "FAIL " + " ".join(parts)
        print(line[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
