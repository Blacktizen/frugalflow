import sys


def main():
    import roman
    valid = {
        "I": 1, "IV": 4, "V": 5, "IX": 9, "X": 10, "XIV": 14, "XIX": 19,
        "XL": 40, "XLIX": 49, "L": 50, "XC": 90, "XCIX": 99, "CD": 400,
        "CDXLIV": 444, "CM": 900, "CMXCIX": 999, "M": 1000,
        "MCMXCIV": 1994, "MMXXIV": 2024, "MMMCMXCIX": 3999,
        "mcmxciv": 1994, "mmxxiv": 2024,
    }
    for s, want in valid.items():
        try:
            got = roman.from_roman(s)
        except Exception as e:
            print("FAIL: from_roman(%r) raised %r" % (s, e))
            return 1
        if got != want:
            print("FAIL: from_roman(%r) = %r, want %r" % (s, got, want))
            return 1
    invalid = ["", "IIII", "VX", "IC", "IIV", "XXXX", "LL", "DD", "IM",
               "XM", "IIX", "VIV", "CDC", "MIM", "ABC", "  ", "IVI",
               "IXI", "XLX", "VV", "0", "MMMM"]
    for s in invalid:
        try:
            roman.from_roman(s)
        except ValueError:
            continue
        except Exception as e:
            print("FAIL: from_roman(%r) raised %r, want ValueError" % (s, e))
            return 1
        print("FAIL: from_roman(%r) accepted, want ValueError" % s)
        return 1
    for n in range(1, 4000):
        if roman.from_roman(roman.to_roman(n)) != n:
            print("FAIL: round trip broken at %d" % n)
            return 1
    for bad in (0, -1, 4000, 4001):
        try:
            roman.to_roman(bad)
        except ValueError:
            continue
        print("FAIL: to_roman(%r) accepted" % bad)
        return 1
    assert roman.to_roman(3888) == "MMMDCCCLXXXVIII"
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
