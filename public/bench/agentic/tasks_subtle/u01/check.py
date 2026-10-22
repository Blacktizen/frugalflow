import sys


def main():
    import money
    cases = [
        ("$1,234.50", 123450),
        ("1.234,50 EUR", 123450),
        ("(12.00)", -1200),
        ("-12.00", -1200),
        ("12", 1200),
        ("$1,000", 100000),
        ("1.000,25", 100025),
        ("7.5", 750),
        ("1,5", 150),
        ("€45", 4500),
        ("(1,234.56)", -123456),
        ("0", 0),
        ("  $42  ", 4200),
        ("1,234,567.89", 123456789),
        ("1.234", 123400),
        ("+3.25", 325),
    ]
    for text, want in cases:
        try:
            got = money.parse_amount(text)
        except Exception as e:
            print("FAIL: parse_amount(%r) raised %r" % (text, e))
            return 1
        if got != want:
            print("FAIL: parse_amount(%r) = %r, want %r" % (text, got, want))
            return 1
    invalid = ["", "abc", "1,2,3", "1.2.3", "$", "(12", "12)",
               "-", "--5", "()", "12,", "   "]
    for text in invalid:
        try:
            money.parse_amount(text)
        except ValueError:
            continue
        except Exception as e:
            print("FAIL: parse_amount(%r) raised %r, want ValueError" % (text, e))
            return 1
        print("FAIL: parse_amount(%r) accepted, want ValueError" % text)
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
