import sys
try:
    import joiner
    from joiner import human_join
except Exception as e:
    print("FAIL joiner: import error: " + str(e)[:600])
    sys.exit(1)

cases = [
    ("empty list", lambda: human_join([]), ""),
    ("single string", lambda: human_join(["alpha"]), "alpha"),
    ("two strings", lambda: human_join(["alpha", "beta"]), "alpha and beta"),
    ("three strings oxford", lambda: human_join(["a", "b", "c"]), "a, b, and c"),
    ("four strings oxford", lambda: human_join(["a", "b", "c", "d"]), "a, b, c, and d"),
    ("none ignored", lambda: human_join(["x", None, "y"]), "x and y"),
    ("empty string ignored", lambda: human_join(["x", "", "y"]), "x and y"),
    ("blank string ignored", lambda: human_join(["x", "   ", "y"]), "x and y"),
    ("all none gives empty", lambda: human_join([None, None, None]), ""),
    ("integers converted", lambda: human_join([1, 2, 3]), "1, 2, and 3"),
    ("whitespace stripped", lambda: human_join([" hello ", "  world"]), "hello and world"),
    ("custom conj", lambda: human_join(["a", "b", "c"], conj="or"), "a, b, or c"),
    ("no deduplication", lambda: human_join(["a", "a"]), "a and a"),
    ("boolean converted", lambda: human_join([True, False, True]), "True, False, and True"),
    ("mixed none and items", lambda: human_join([None, 1, None, 2, None]), "1 and 2"),
    ("blank only gives empty", lambda: human_join(["", " ", "  ", "\t"]), ""),
]

discrepancies = []
for i, (desc, func, expected) in enumerate(cases, 1):
    try:
        result = func()
        if result != expected:
            discrepancies.append((i, desc, repr(expected), repr(result)))
    except Exception as e:
        discrepancies.append((i, desc, repr(expected), "EXCEPTION: " + repr(e)))
    if discrepancies:
        break

if discrepancies:
    msg = "FAIL joiner:"
    for d in discrepancies[:3]:
        msg += " [case %d: %s] expected=%s obtained=%s" % (d[0], d[1], d[2], d[3])
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
