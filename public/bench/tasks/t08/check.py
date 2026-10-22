import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t08"


def main():
    try:
        import pricing
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        ((1000, 10), 900),
        ((1000, 0), 1000),
        ((999, 33), 669),
        ((50, 200), 0),
        ((1000, 100), 0),
        ((1, 1), 1),
    ]
    bad = []
    for args, want in cases:
        try:
            got = pricing.apply_discount(*args)
        except Exception as exc:
            bad.append((args, want, "raised %s" % exc))
            continue
        if got != want:
            bad.append((args, want, got))
    if bad:
        print("FAIL %s expected/got: %r" % (TASK, bad))
        sys.exit(1)
    print("PASS %s" % TASK)
    sys.exit(0)


if __name__ == "__main__":
    main()
