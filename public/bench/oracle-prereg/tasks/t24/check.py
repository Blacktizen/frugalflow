import sys

def run():
    try:
        from sortedins import insert_sorted
    except ImportError:
        print("FAIL sortedins: import error")
        sys.exit(1)

    failures = []

    # 1 - basic insertion in middle
    try:
        r = insert_sorted([1, 3, 5], 4)
        assert r == [1, 3, 4, 5], "1"
    except Exception as e:
        failures.append((1, [1,3,4,5], repr(e)))

    # 2 - insert at beginning
    try:
        r = insert_sorted([2, 4, 6], 1)
        assert r == [1, 2, 4, 6], "2"
    except Exception as e:
        failures.append((2, [1,2,4,6], repr(e)))

    # 3 - insert at end
    try:
        r = insert_sorted([1, 3, 5], 7)
        assert r == [1, 3, 5, 7], "3"
    except Exception as e:
        failures.append((3, [1,3,5,7], repr(e)))

    # 4 - empty list
    try:
        r = insert_sorted([], 5)
        assert r == [5], "4"
    except Exception as e:
        failures.append((4, [5], repr(e)))

    # 5 - stability with tuples: x after equal-key elements
    try:
        xs = [(2, 'a'), (2, 'b')]
        r = insert_sorted(xs, (2, 'c'), key=lambda t: t[0])
        assert r == [(2, 'a'), (2, 'b'), (2, 'c')], "5"
    except Exception as e:
        failures.append((5, [(2,'a'),(2,'b'),(2,'c')], repr(e)))

    # 6 - stability single equal-key element
    try:
        xs = [(5, 'a')]
        r = insert_sorted(xs, (5, 'b'), key=lambda t: t[0])
        assert r == [(5, 'a'), (5, 'b')], "6"
    except Exception as e:
        failures.append((6, [(5,'a'),(5,'b')], repr(e)))

    # 7 - xs must not be mutated
    try:
        xs = [1, 3, 5]
        r = insert_sorted(xs, 4)
        assert xs == [1, 3, 5], "7-mutation"
    except Exception as e:
        failures.append((7, "xs==[1,3,5]", repr(e)))

    # 8 - result is a new list (not the same object)
    try:
        xs = [1, 3, 5]
        r = insert_sorted(xs, 4)
        assert r is not xs, "8-identity"
    except Exception as e:
        failures.append((8, "r is not xs", repr(e)))

    # 9 - key=None explicit
    try:
        r = insert_sorted([1, 2, 3], 3, key=None)
        assert r == [1, 2, 3, 3], "9"
    except Exception as e:
        failures.append((9, [1,2,3,3], repr(e)))

    # 10 - key applies to x and elements with tuple extraction
    try:
        xs = [(1, 'a'), (3, 'b'), (5, 'c')]
        r = insert_sorted(xs, (2, 'x'), key=lambda t: t[0])
        assert r == [(1, 'a'), (2, 'x'), (3, 'b'), (5, 'c')], "10"
    except Exception as e:
        failures.append((10, [(1,'a'),(2,'x'),(3,'b'),(5,'c')], repr(e)))

    # 11 - all elements share same key, x goes after all
    try:
        xs = [(1, 'a'), (1, 'b'), (1, 'c')]
        r = insert_sorted(xs, (1, 'z'), key=lambda t: t[0])
        assert r == [(1, 'a'), (1, 'b'), (1, 'c'), (1, 'z')], "11"
    except Exception as e:
        failures.append((11, [(1,'a'),(1,'b'),(1,'c'),(1,'z')], repr(e)))

    # 12 - key function produces shared keys among xs and x
    try:
        xs = [10, 20, 30]
        r = insert_sorted(xs, 15, key=lambda v: v // 10)
        assert r == [10, 15, 20, 30], "12"
    except Exception as e:
        failures.append((12, [10,15,20,30], repr(e)))

    # 13 - negative numbers
    try:
        r = insert_sorted([-3, -1, 2], -2)
        assert r == [-3, -2, -1, 2], "13"
    except Exception as e:
        failures.append((13, [-3,-2,-1,2], repr(e)))

    # 14 - integer stability: x after equal ints in xs
    try:
        r = insert_sorted([1, 2, 2, 3], 2)
        assert r == [1, 2, 2, 2, 3], "14"
    except Exception as e:
        failures.append((14, [1,2,2,2,3], repr(e)))

    # 15 - insert before all (x smaller than every element)
    try:
        xs = [(4, 'd'), (6, 'f')]
        r = insert_sorted(xs, (1, 'a'), key=lambda t: t[0])
        assert r == [(1, 'a'), (4, 'd'), (6, 'f')], "15"
    except Exception as e:
        failures.append((15, [(1,'a'),(4,'d'),(6,'f')], repr(e)))

    # 16 - key=lambda returns negative, xs sorted by key
    try:
        xs = [-5, -3, -1]
        r = insert_sorted(xs, -4, key=lambda v: v)
        assert r == [-5, -4, -3, -1], "16"
    except Exception as e:
        failures.append((16, [-5,-4,-3,-1], repr(e)))

    if failures:
        parts = []
        for f in failures[:3]:
            parts.append("case={case} expected={exp} obtained={got}".format(
                case=f[0], exp=str(f[1])[:60], got=str(f[2])[:60]))
        msg = "FAIL sortedins: " + " | ".join(parts)
        print(msg[:600])
        sys.exit(1)

    print("PASS")
    sys.exit(0)

run()
