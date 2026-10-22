import sys
import copy


def main():
    import intervals
    cases = [
        ([], []),
        ([[1, 3], [2, 6], [8, 10], [15, 18]], [[1, 6], [8, 10], [15, 18]]),
        ([[1, 2], [2, 3]], [[1, 3]]),
        ([[1, 4], [2, 3]], [[1, 4]]),
        ([[5, 2]], [[2, 5]]),
        ([[5, 2], [1, 1], [3, 4]], [[1, 1], [2, 5]]),
        ([[10, 11], [2, 3], [6, 7], [3, 4], [5, 6]], [[2, 4], [5, 7], [10, 11]]),
        ([[1, 1], [1, 2], [2, 2]], [[1, 2]]),
    ]
    for inp, want in cases:
        try:
            got = intervals.merge(inp)
        except Exception as e:
            print("FAIL: merge(%r) raised %r" % (inp, e))
            return 1
        if got != want:
            print("FAIL: merge(%r) = %r, want %r" % (inp, got, want))
            return 1
    orig = [[3, 1], [2, 5]]
    before = copy.deepcopy(orig)
    res = intervals.merge(orig)
    if res != [[1, 5]]:
        print("FAIL: merge(%r) = %r, want [[1, 5]]" % (orig, res))
        return 1
    if orig != before:
        print("FAIL: input was mutated: %r -> %r" % (before, orig))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
