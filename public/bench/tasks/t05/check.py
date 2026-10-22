import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t05"


def main():
    try:
        import lists
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        (([1, 2, 2, 3, 1],), [1, 2, 3]),
        ((["a", "b", "a"],), ["a", "b"]),
        (([],), []),
        (([5],), [5]),
        (([3, 1, 2, 1, 3, 2],), [3, 1, 2]),
        ((["x", "x", "x"],), ["x"]),
    ]
    bad = []
    for args, want in cases:
        try:
            got = lists.remove_duplicates(*args)
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
