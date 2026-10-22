import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t03"


def main():
    try:
        import timefmt
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        ((0,), "0:00:00"),
        ((59,), "0:00:59"),
        ((60,), "0:01:00"),
        ((3661,), "1:01:01"),
        ((86399,), "23:59:59"),
        ((90061,), "25:01:01"),
    ]
    bad = []
    for args, want in cases:
        try:
            got = timefmt.format_duration(*args)
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
