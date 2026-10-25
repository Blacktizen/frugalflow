import sys

TASK = "semver_compare"

def run_checks():
    try:
        import semver
        compare = semver.compare
    except Exception as e:
        print("FAIL " + TASK + " | import: " + str(e)[:200])
        sys.exit(1)

    cases = [
        ("1.0.0", "1.0.1", -1),
        ("1.0.0", "1.0.0", 0),
        ("2.1.0", "1.9.9", 1),
        ("1.0.0+build1", "1.0.0+build2", 0),
        ("1.0.0-alpha", "1.0.0", -1),
        ("1.0.0", "1.0.0-alpha", 1),
        ("1.0.0-alpha", "1.0.0-beta", -1),
        ("1.0.0-9", "1.0.0-10", -1),
        ("1.0.0-10", "1.0.0-9", 1),
        ("1.0.0-9", "1.0.0-alpha", -1),
        ("1.0.0-Alpha", "1.0.0-alpha", -1),
        ("1.0.0-1", "1.0.0-1.2", -1),
        ("1.0.0-1.2", "1.0.0-1", 1),
        ("1.0.0-1.alpha", "1.0.0-1.beta", -1),
        ("1.0.0-1.2", "1.0.0-1.alpha", -1),
    ]

    errors = []

    for i, (a, b, expected) in enumerate(cases):
        try:
            got = compare(a, b)
        except Exception as e:
            errors.append((i, a, b, expected, "EXC:" + str(e)[:80]))
            continue
        if got != expected:
            errors.append((i, a, b, expected, str(got)))
        if len(errors) >= 3:
            break

    # test invalid input raises ValueError
    try:
        compare("1.0", "1.0.0")
        errors.append((len(cases), "1.0", "1.0.0", "ValueError", "no exception"))
    except ValueError:
        pass
    except Exception as e:
        errors.append((len(cases), "1.0", "1.0.0", "ValueError", str(e)[:80]))

    if errors:
        parts = []
        for e in errors[:3]:
            idx, a, b, exp, got = e
            parts.append("case%d a=%s b=%s expected=%s obtained=%s" % (idx, a, b, str(exp), got))
        line = "FAIL " + TASK + " | " + " | ".join(parts)
        print(line[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run_checks()
