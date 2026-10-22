import sys


def main():
    import invoice
    cases = [
        ([("10.00", 1, 0)], 1000),
        ([("1.50", 2, 0)], 300),
        ([("0.10", 1, 5)], 11),
        ([("-0.10", 1, 5)], -11),
        ([("0.10", 1, 5), ("0.10", 1, 5)], 22),
        ([("2.675", 1, 0)], 268),
        ([("0.07", 3, 0)], 21),
        ([("0.33", 1, 8)], 36),
        ([("1234.56", 2, 19)], 293825),
        ([], 0),
    ]
    for lines, want in cases:
        try:
            got = invoice.total(lines)
        except Exception as e:
            print("FAIL: total(%r) raised %r" % (lines, e))
            return 1
        if got != want:
            print("FAIL: total(%r) = %r, want %r" % (lines, got, want))
            return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
