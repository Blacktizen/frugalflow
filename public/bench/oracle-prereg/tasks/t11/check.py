import sys

TASK_ID = "roman_to_int"

def run():
    try:
        from roman import roman_to_int
    except Exception as e:
        print("FAIL " + TASK_ID + " import error: " + str(e)[:200])
        sys.exit(1)

    cases = [
        ("I", 1),
        ("III", 3),
        ("IV", 4),
        ("IX", 9),
        ("XL", 40),
        ("XC", 90),
        ("CD", 400),
        ("CM", 900),
        ("MCMXCIV", 1994),
        ("MMMCMXCIX", 3999),
        ("IIII", ValueError),
        ("VX", ValueError),
        ("IC", ValueError),
        ("XM", ValueError),
        ("IIV", ValueError),
        ("VV", ValueError),
        ("LL", ValueError),
        ("DD", ValueError),
        ("CCCC", ValueError),
        ("XXXX", ValueError),
        ("MMMM", ValueError),
        ("", ValueError),
        ("iv", ValueError),
    ]

    discrepancies = []
    for case_input, expected in cases:
        try:
            result = roman_to_int(case_input)
            if isinstance(expected, type) and issubclass(expected, ValueError):
                discrepancies.append((case_input, "ValueError", repr(result)))
                break
            elif result != expected:
                discrepancies.append((case_input, expected, result))
                break
        except ValueError:
            if not (isinstance(expected, type) and issubclass(expected, ValueError)):
                discrepancies.append((case_input, expected, "ValueError"))
                break
        except Exception as e:
            discrepancies.append((case_input, expected, str(e)))
            break

    if discrepancies:
        parts = []
        for d in discrepancies[:3]:
            parts.append(str(d[0]) + " expected=" + str(d[1]) + " got=" + str(d[2]))
        msg = "FAIL " + TASK_ID + " | " + " | ".join(parts)
        print(msg[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run()
