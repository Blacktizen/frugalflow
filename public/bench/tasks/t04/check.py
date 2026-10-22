import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t04"


def main():
    try:
        import validate
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        (("x",), True),
        (("_x",), True),
        (("x1",), True),
        (("foo_bar",), True),
        (("",), False),
        (("1x",), False),
        (("foo-bar",), False),
        (("foo bar",), False),
        (("foo.bar",), False),
    ]
    bad = []
    for args, want in cases:
        try:
            got = validate.is_valid_identifier(*args)
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
