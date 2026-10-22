import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t01"


def main():
    try:
        import stats
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        (([5],), 5),
        (([1, 2, 3],), 2),
        (([1, 2, 3, 4],), 2.5),
        (([7, 3, 1, 5, 9],), 5),
        (([10, 20],), 15.0),
        (([-5, 5],), 0.0),
    ]
    bad = []
    for args, want in cases:
        try:
            got = stats.median(*args)
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
