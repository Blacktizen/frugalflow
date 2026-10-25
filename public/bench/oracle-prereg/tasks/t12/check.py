import sys
TASK_ID = "basen_to_base"
try:
    from basen import to_base
except Exception as e:
    print(f"FAIL {TASK_ID} import: {str(e)[:600]}")
    sys.exit(1)

results = []
def check(case, fn, expected, expected_type="value"):
    try:
        got = fn()
    except Exception as e:
        got = e
    if expected_type == "value":
        if isinstance(got, Exception):
            return (case, expected, repr(got))
        if got != expected:
            return (case, expected, repr(got))
    elif expected_type == "ValueError":
        if not isinstance(got, ValueError):
            return (case, "ValueError", repr(got))
    return None

tests = [
    ("to_base(0,2)", lambda: to_base(0, 2), "0", "value"),
    ("to_base(0,36)", lambda: to_base(0, 36), "0", "value"),
    ("to_base(10,2)", lambda: to_base(10, 2), "1010", "value"),
    ("to_base(255,16)", lambda: to_base(255, 16), "ff", "value"),
    ("to_base(-42,8)", lambda: to_base(-42, 8), "-52", "value"),
    ("to_base(35,36)", lambda: to_base(35, 36), "z", "value"),
    ("to_base(10,10)", lambda: to_base(10, 10), "10", "value"),
    ("to_base(2,2)", lambda: to_base(2, 2), "10", "value"),
    ("to_base(10,36)", lambda: to_base(10, 36), "a", "value"),
    ("to_base(-1,2)", lambda: to_base(-1, 2), "-1", "value"),
    ("to_base(True,2)", lambda: to_base(True, 2), None, "ValueError"),
    ("to_base(False,2)", lambda: to_base(False, 2), None, "ValueError"),
    ("to_base(3.0,2)", lambda: to_base(3.0, 2), None, "ValueError"),
    ("to_base('10',2)", lambda: to_base("10", 2), None, "ValueError"),
    ("to_base(10,1)", lambda: to_base(10, 1), None, "ValueError"),
    ("to_base(10,37)", lambda: to_base(10, 37), None, "ValueError"),
    ("to_base(10,0)", lambda: to_base(10, 0), None, "ValueError"),
    ("to_base(10,-1)", lambda: to_base(10, -1), None, "ValueError"),
]

discrepancies = []
for case, fn, expected, etype in tests:
    d = check(case, fn, expected, etype)
    if d:
        discrepancies.append(d)

if discrepancies:
    parts = []
    for (c, e, g) in discrepancies[:3]:
        parts.append(f"[{c}] expected={e} obtained={g}")
    msg = " ".join(parts)[:600]
    print(f"FAIL {TASK_ID} {msg}")
    sys.exit(1)

print("PASS")
sys.exit(0)
