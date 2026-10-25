import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

TASK_ID = "luhn_valid_2025"

def run_tests():
    try:
        from luhn import luhn_valid
    except Exception as e:
        print("FAIL " + TASK_ID + " :: import error :: " + str(e)[:600])
        sys.exit(1)

    cases = []

    # Case 1: valid 16-digit no separators
    cases.append(("4532015112830366", True))

    # Case 2: valid 12-digit no separators
    cases.append(("123456789015", True))

    # Case 3: valid 12-digit with spaces
    cases.append(("1234 5678 9015", True))

    # Case 4: valid 12-digit with dashes
    cases.append(("1234-5678-9015", True))

    # Case 5: valid 16-digit with mixed spaces and dashes
    cases.append(("4532 0151-1283 0366", True))

    # Case 6: 16-digit but invalid Luhn checksum
    cases.append(("4532015112830367", False))

    # Case 7: contains a letter (non-digit, non-separator)
    cases.append(("453201511283036a", False))

    # Case 8: contains a dot (non-digit, non-separator)
    cases.append(("4532.0151.1283.0366", False))

    # Case 9: contains underscore
    cases.append(("1234_5678_9015", False))

    # Case 10: fewer than 12 digits (10 digits, valid Luhn)
    cases.append(("1234567897", False))

    # Case 11: more than 19 digits (20 digits)
    cases.append(("12345678901234567890", False))

    # Case 12: empty string
    cases.append(("", False))

    # Case 13: only separators, no digits
    cases.append(("   ---  ", False))

    # Case 14: exactly 12 digits, valid Luhn
    cases.append(("123456789015", True))

    # Case 15: exactly 19 digits, valid Luhn
    cases.append(("1234567890123456789", False))

    # Case 16: exactly 19 digits valid Luhn (constructed)
    # 18 digits + check: "123456789012345678" + check digit
    # From right of "123456789012345678X":
    # Let's use: 1234567890123456785 (19 digits)
    cases.append(("1234567890123456785", True))

    # Case 17: contains plus sign
    cases.append(("+123456789015", False))

    # Case 18: contains newline character
    cases.append(("12345678901\n5", False))

    # Case 19: single digit
    cases.append(("5", False))

    failures = []
    for idx, (inp, expected) in enumerate(cases):
        try:
            result = luhn_valid(inp)
        except Exception as e:
            failures.append((idx, expected, "EXCEPTION:" + str(e)[:80]))
            continue
        if result != expected:
            failures.append((idx, expected, str(result)[:80]))

    if failures:
        parts = []
        for f in failures[:3]:
            parts.append("case%d exp=%s got=%s" % (f[0], str(f[1])[:60], f[2][:60]))
        msg = "FAIL " + TASK_ID + " :: " + " || ".join(parts)
        print(msg[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run_tests()
