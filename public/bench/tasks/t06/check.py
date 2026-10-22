import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t06"


def main():
    try:
        import csvtools
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        ((["a", "b", "c"],), "a,b,c"),
        ((["a,b", "c"],), '"a,b",c'),
        ((['say "hi"', "x"],), '"say ""hi""",x'),
        ((["a\nb", "c"],), '"a\nb",c'),
        (([],), ""),
        ((["plain", ""],), "plain,"),
    ]
    bad = []
    for args, want in cases:
        try:
            got = csvtools.to_csv_row(*args)
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
