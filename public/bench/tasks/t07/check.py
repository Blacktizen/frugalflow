import os
import sys

sys.dont_write_bytecode = True
sys.path.insert(0, os.getcwd())

TASK = "t07"


def main():
    try:
        import kv
    except Exception as exc:
        print("FAIL %s import error: %s" % (TASK, exc))
        sys.exit(1)
    cases = [
        (("a=1\nb=2",), {"a": "1", "b": "2"}),
        (("  name = alice  \n",), {"name": "alice"}),
        (("# comment\nk = v\n",), {"k": "v"}),
        (("x=1\nx=2\n",), {"x": "2"}),
        (("",), {}),
        (("   \n\ttab=3\n",), {"tab": "3"}),
    ]
    bad = []
    for args, want in cases:
        try:
            got = kv.parse_key_values(*args)
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
