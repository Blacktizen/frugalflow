import sys
sys.path.insert(0, ".")

TASK = "rangelist-parse_ranges"
discrepancies = []

def expect_valueerror(case, s):
    try:
        from rangelist import parse_ranges as f
        f(s)
        discrepancies.append((case, "ValueError", "no exception"))
    except ValueError:
        pass
    except Exception as e:
        discrepancies.append((case, "ValueError", repr(e)))

def expect_result(case, s, expected):
    try:
        from rangelist import parse_ranges as f
        got = f(s)
        if got != expected:
            discrepancies.append((case, str(expected), str(got)))
    except Exception as e:
        discrepancies.append((case, str(expected), repr(e)))

cases_done = 0
try:
    import rangelist
except Exception as e:
    print("FAIL " + TASK + " | import | " + repr(e))
    sys.exit(1)

cases = [
    ("basic_ranges", lambda: expect_result("basic_ranges", "1-3,5,7-9", [1,2,3,5,7,8,9])),
    ("empty_string", lambda: expect_result("empty_string", "", [])),
    ("blank_string", lambda: expect_result("blank_string", "   ", [])),
    ("spaces_around", lambda: expect_result("spaces_around", " 1-3 , 5 , 7-9 ", [1,2,3,5,7,8,9])),
    ("single_number", lambda: expect_result("single_number", "5", [5])),
    ("range_only", lambda: expect_result("range_only", "1-3", [1,2,3])),
    ("singles", lambda: expect_result("singles", "1,2,3", [1,2,3])),
    ("empty_element_mid", lambda: expect_valueerror("empty_element_mid", "1,,2")),
    ("empty_element_lead", lambda: expect_valueerror("empty_element_lead", ",1,2")),
    ("empty_element_tail", lambda: expect_valueerror("empty_element_tail", "1,2,")),
    ("inverse_range", lambda: expect_valueerror("inverse_range", "5-3")),
    ("negative_sign", lambda: expect_valueerror("negative_sign", "-1")),
    ("non_numeric", lambda: expect_valueerror("non_numeric", "1-3,abc")),
    ("duplicates", lambda: expect_result("duplicates", "1-3,1-3", [1,2,3])),
    ("overlapping", lambda: expect_result("overlapping", "1-2,2-3", [1,2,3])),
    ("range_spaces_inside", lambda: expect_valueerror("range_spaces_inside", "1 - 3")),
]

for name, fn in cases:
    cases_done += 1
    fn()

if discrepancies:
    msg = "FAIL " + TASK + " "
    for d in discrepancies[:3]:
        msg += "| " + str(d) + " "
    print(msg[:600])
    sys.exit(1)

print("PASS")
sys.exit(0)
