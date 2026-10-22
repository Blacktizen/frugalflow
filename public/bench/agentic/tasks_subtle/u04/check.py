import sys


def main():
    import semver
    cases = [
        ("1.2.3", "1.10.0", -1),
        ("1.10.0", "1.2.3", 1),
        ("1.2.3", "1.2.3", 0),
        ("1.0.0-alpha", "1.0.0", -1),
        ("1.0.0", "1.0.0-alpha", 1),
        ("1.0.0-alpha", "1.0.0-alpha.1", -1),
        ("1.0.0-alpha.1", "1.0.0-alpha", 1),
        ("1.0.0-2", "1.0.0-10", -1),
        ("1.0.0-alpha", "1.0.0-1", 1),
        ("1.0.0-1", "1.0.0-alpha", -1),
        ("1.0.0-a", "1.0.0-b", -1),
        ("1.0", "1.0.0", -1),
        ("1.0.0", "1.0", 1),
        ("1.0.0+build", "1.0.0", 0),
        ("1.0.0", "1.0.0+other", 0),
        ("1.0.0-alpha+meta", "1.0.0-alpha", 0),
    ]
    for a, b, want in cases:
        try:
            got = semver.compare(a, b)
        except Exception as e:
            print("FAIL: compare(%r, %r) raised %r" % (a, b, e))
            return 1
        if got != want:
            print("FAIL: compare(%r, %r) = %r, want %r" % (a, b, got, want))
            return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
