import sys
import copy

try:
    from dedupe import keep_last
except Exception as e:
    print("FAIL dedupe import: " + str(e)[:600])
    sys.exit(1)

discrepancies = []

def run(case_id, fn):
    try:
        fn()
    except Exception as e:
        expected = getattr(e, "expected", "exception raised")
        obtained = getattr(e, "obtained", str(e))
        discrepancies.append((case_id, expected, obtained))
        return False
    return True

def assert_eq(case_id, expected, obtained):
    if expected != obtained:
        exc = AssertionError("case " + case_id)
        exc.expected = repr(expected)
        exc.obtained = repr(obtained)
        raise exc

# Case 1: empty list
def case1():
    assert_eq("C1", [], keep_last([], "k"))
run("C1", case1)

# Case 2: all rows lack the key -> all kept in order
def case2():
    rows = [{"a": 1}, {"b": 2}, {"c": 3}]
    assert_eq("C2", [{"a": 1}, {"b": 2}, {"c": 3}], keep_last(rows, "k"))
run("C2", case2)

# Case 3: two rows same key value -> only last kept
def case3():
    rows = [{"k": "x", "v": 1}, {"k": "x", "v": 2}]
    assert_eq("C3", [{"k": "x", "v": 2}], keep_last(rows, "k"))
run("C3", case3)

# Case 4: three rows same key value -> only last kept
def case4():
    rows = [{"k": 1, "v": 10}, {"k": 1, "v": 20}, {"k": 1, "v": 30}]
    assert_eq("C4", [{"k": 1, "v": 30}], keep_last(rows, "k"))
run("C4", case4)

# Case 5: row without key kept in place among key rows
def case5():
    rows = [{"k": "a", "v": 1}, {"nokey": 9}, {"k": "a", "v": 2}]
    assert_eq("C5", [{"nokey": 9}, {"k": "a", "v": 2}], keep_last(rows, "k"))
run("C5", case5)

# Case 6: multiple rows without key all kept in relative order
def case6():
    rows = [{"m": 1}, {"m": 2}, {"m": 3}]
    assert_eq("C6", [{"m": 1}, {"m": 2}, {"m": 3}], keep_last(rows, "k"))
run("C6", case6)

# Case 7: order of last occurrences follows input order
def case7():
    rows = [{"k": "b", "v": 1}, {"k": "a", "v": 2}, {"k": "b", "v": 3}, {"k": "a", "v": 4}]
    assert_eq("C7", [{"k": "b", "v": 3}, {"k": "a", "v": 4}], keep_last(rows, "k"))
run("C7", case7)

# Case 8: returns a new list (not the same object)
def case8():
    rows = [{"k": 1}]
    result = keep_last(rows, "k")
    if result is rows:
        exc = AssertionError("case C8")
        exc.expected = "new list object"
        exc.obtained = "same list object"
        raise exc
run("C8", case8)

# Case 9: original dicts not modified
def case9():
    rows = [{"k": "x", "v": 1}, {"k": "x", "v": 2}]
    before = copy.deepcopy(rows)
    keep_last(rows, "k")
    assert_eq("C9", before, rows)
run("C9", case9)

# Case 10: key value appears once -> kept
def case10():
    rows = [{"k": "solo", "v": 42}]
    assert_eq("C10", [{"k": "solo", "v": 42}], keep_last(rows, "k"))
run("C10", case10)

# Case 11: interspersed no-key rows maintain position
def case11():
    rows = [{"n": 1}, {"k": "a", "v": 1}, {"n": 2}, {"k": "a", "v": 2}, {"n": 3}]
    assert_eq("C11", [{"n": 1}, {"n": 2}, {"k": "a", "v": 2}, {"n": 3}], keep_last(rows, "k"))
run("C11", case11)

# Case 12: key value 0 (falsy) handled correctly
def case12():
    rows = [{"k": 0, "v": "first"}, {"k": 0, "v": "second"}]
    assert_eq("C12", [{"k": 0, "v": "second"}], keep_last(rows, "k"))
run("C12", case12)

# Case 13: key value empty string handled correctly
def case13():
    rows = [{"k": "", "v": 1}, {"k": "", "v": 2}]
    assert_eq("C13", [{"k": "", "v": 2}], keep_last(rows, "k"))
run("C13", case13)

# Case 14: all same key value with no-key rows interspersed
def case14():
    rows = [{"z": 1}, {"k": 7, "v": "a"}, {"z": 2}, {"k": 7, "v": "b"}, {"z": 3}]
    assert_eq("C14", [{"z": 1}, {"z": 2}, {"k": 7, "v": "b"}, {"z": 3}], keep_last(rows, "k"))
run("C14", case14)

# Case 15: two distinct key values each appearing twice
def case15():
    rows = [{"k": "p", "v": 1}, {"k": "q", "v": 2}, {"k": "p", "v": 3}, {"k": "q", "v": 4}]
    assert_eq("C15", [{"k": "p", "v": 3}, {"k": "q", "v": 4}], keep_last(rows, "k"))
run("C15", case15)

# Case 16: key value None handled correctly
def case16():
    rows = [{"k": None, "v": 1}, {"k": None, "v": 2}, {"k": None, "v": 3}]
    assert_eq("C16", [{"k": None, "v": 3}], keep_last(rows, "k"))
run("C16", case16)

if discrepancies:
    parts = []
    for d in discrepancies[:3]:
        parts.append("case=" + d[0] + " expected=" + str(d[1]) + " obtained=" + str(d[2]))
    msg = " ".join(parts)
    print("FAIL dedupe: " + msg[:600])
    sys.exit(1)
else:
    print("PASS")
    sys.exit(0)
