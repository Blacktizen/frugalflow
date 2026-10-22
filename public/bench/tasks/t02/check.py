import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t02"


def main():
    try:
        import text
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        (("hello world",), "Hello World"),
        (("PYTHON is GREAT",), "Python Is Great"),
        (("  spaced  out ",), "  Spaced  Out "),
        (("",), ""),
        (("a",), "A"),
        (("don't stop",), "Don't Stop"),
    ]
    bad = []
    for args, want in cases:
        try:
            got = text.title_case(*args)
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
