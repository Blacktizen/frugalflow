import sys

TASK_ID = "rle_decode"

def get_module():
    try:
        from rle import rle_decode
        return rle_decode
    except Exception:
        return None

def main():
    fn = get_module()
    if fn is None:
        print("FAIL " + TASK_ID + " | module import error")
        sys.exit(1)

    cases = [
        ("3a2b1c", "aaabbc", None),
        ("12x", "xxxxxxxxxxxx", None),
        ("", "", None),
        ("0a", "", None),
        ("0a0b0c", "", None),
        ("1a", "a", None),
        ("10b", "bbbbbbbbbb", None),
        ("a3", None, ValueError),
        (" 3a", None, ValueError),
        ("3a2", None, ValueError),
        ("3a21", None, ValueError),
        ("3ab", None, ValueError),
        ("2a 3b", None, ValueError),
        ("2 1a", "  a", None),
        ("1 a", None, ValueError),
        ("3a1 ", "aaa ", None),
        ("3a0b1c", "aaac", None),
        ("5x", "xxxxx", None),
        ("1 ", " ", None),
        ("44z", "z" * 44, None),
    ]

    discrepancies = []
    for case in cases:
        inp, expected, exc = case
        try:
            if exc is not None:
                try:
                    result = fn(inp)
                    discrepancies.append((inp, "raises " + exc.__name__, repr(result)))
                except exc:
                    pass
            else:
                try:
                    result = fn(inp)
                    if result != expected:
                        discrepancies.append((inp, repr(expected), repr(result)))
                except Exception as e:
                    discrepancies.append((inp, repr(expected), repr(e)))
        except Exception as e:
            discrepancies.append((inp, repr(expected), repr(e)))

    if discrepancies:
        first_three = discrepancies[:3]
        msg = "FAIL " + TASK_ID + " | "
        for (inp, exp, got) in first_three:
            msg += "[case=" + repr(inp) + " expected=" + str(exp) + " obtained=" + str(got) + "] "
        msg = msg[:600]
        print(msg)
        sys.exit(1)
    print("PASS")
    sys.exit(0)

if __name__ == "__main__":
    main()
