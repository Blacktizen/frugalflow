import sys

def run():
    failures = []
    try:
        from pct import pct_change
    except Exception as e:
        print("FAIL pct " + repr(e)[:580])
        sys.exit(1)

    def expect(label, args, want):
        try:
            got = pct_change(*args)
            if want is None:
                if got is not None:
                    failures.append((label, str(None), repr(got)))
            else:
                if type(got) is not float:
                    failures.append((label, "float", type(got).__name__))
                elif got != want:
                    failures.append((label, str(want), str(got)))
        except Exception as e:
            failures.append((label, str(want), "EXC:" + repr(e)[:50]))

    expect("1", (100, 110), 10.0)
    expect("2", (100, 90), -10.0)
    expect("3", (0, 5), None)
    expect("4", (0.0, 10), None)
    expect("5", (50, 50), 0.0)
    expect("6", (800, 801), 0.13)
    expect("7", (800, 799), -0.13)
    expect("8", (4000, 4001), 0.03)
    expect("9", (4000, 3999), -0.03)
    expect("10", (4000, 4013), 0.33)
    expect("11", (3, 7), 133.33)
    expect("12", (-100, -80), -20.0)
    expect("13", (0.1, 0.3), 200.0)
    expect("14", (1000, 0), -100.0)
    expect("15", (1000000, 1000125), 0.01)
    expect("16", (-50, 50), -200.0)

    if failures:
        first = failures[:3]
        parts = "; ".join("case %s expected %s obtained %s" % f for f in first)
        line = "FAIL pct " + parts
        print(line[:600])
        sys.exit(1)
    print("PASS")
    sys.exit(0)

run()
