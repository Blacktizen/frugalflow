import sys

TASK = "topwords_top_n"

def run():
    try:
        from topwords import top_n
    except ImportError:
        print("FAIL {} cannot import topwords: ImportError".format(TASK))
        sys.exit(1)

    discrepancies = []

    def check(label, got, expected):
        if got != expected:
            discrepancies.append((label, repr(expected)[:200], repr(got)[:200]))

    def expect_error(label, exc_type, fn):
        try:
            fn()
            discrepancies.append((label, "expected {}".format(exc_type.__name__), "no exception"))
        except exc_type:
            pass

    # 1 - basic frequency
    try:
        check("basic_freq", top_n(["apple", "banana", "apple", "cherry"], 2), [("apple", 2), ("banana", 1)])
    except Exception as e:
        discrepancies.append(("basic_freq", "no exception", repr(e)))

    # 2 - case insensitive, lowercase output
    try:
        check("case_insensitive", top_n(["Apple", "apple", "BANANA"], 2), [("apple", 2), ("banana", 1)])
    except Exception as e:
        discrepancies.append(("case_insensitive", "no exception", repr(e)))

    # 3 - alphabetical tie-break
    try:
        check("alpha_tiebreak", top_n(["zebra", "alpha", "beta", "alpha", "beta"], 3), [("alpha", 2), ("beta", 2), ("zebra", 1)])
    except Exception as e:
        discrepancies.append(("alpha_tiebreak", "no exception", repr(e)))

    # 4 - n <= 0 returns []
    try:
        check("n_zero", top_n(["a", "b"], 0), [])
    except Exception as e:
        discrepancies.append(("n_zero", "no exception", repr(e)))

    # 5 - n negative returns []
    try:
        check("n_negative", top_n(["a", "b", "a"], -3), [])
    except Exception as e:
        discrepancies.append(("n_negative", "no exception", repr(e)))

    # 6 - n exceeds distinct words: return all
    try:
        check("n_exceeds", top_n(["cat", "dog", "cat"], 10), [("cat", 2), ("dog", 1)])
    except Exception as e:
        discrepancies.append(("n_exceeds", "no exception", repr(e)))

    # 7 - empty strings ignored
    try:
        check("empty_string_ignored", top_n(["", "hello", "hello", ""], 2), [("hello", 2)])
    except Exception as e:
        discrepancies.append(("empty_string_ignored", "no exception", repr(e)))

    # 8 - space-only strings ignored
    try:
        check("space_only_ignored", top_n(["   ", "world", "world"], 2), [("world", 2)])
    except Exception as e:
        discrepancies.append(("space_only_ignored", "no exception", repr(e)))

    # 9 - words are stripped before lowercasing
    try:
        check("strip_words", top_n(["  apple  ", "apple", "  APPLE  "], 1), [("apple", 3)])
    except Exception as e:
        discrepancies.append(("strip_words", "no exception", repr(e)))

    # 10 - all words stripped to empty yields empty list
    try:
        check("all_ignored", top_n(["", "  ", "\t"], 5), [])
    except Exception as e:
        discrepancies.append(("all_ignored", "no exception", repr(e)))

    # 11 - n equals number of distinct words: return all
    try:
        check("n_equals_distinct", top_n(["x", "y", "x", "z"], 3), [("x", 2), ("y", 1), ("z", 1)])
    except Exception as e:
        discrepancies.append(("n_equals_distinct", "no exception", repr(e)))

    # 12 - multiple ties alphabetical full order
    try:
        check("multi_tie", top_n(["b", "c", "a", "b", "c", "a"], 3), [("a", 2), ("b", 2), ("c", 2)])
    except Exception as e:
        discrepancies.append(("multi_tie", "no exception", repr(e)))

    # 13 - n=1 returns only first
    try:
        check("n_one", top_n(["mango", "mango", "apple"], 1), [("mango", 2)])
    except Exception as e:
        discrepancies.append(("n_one", "no exception", repr(e)))

    # 14 - empty words list with n>0
    try:
        check("empty_words", top_n([], 5), [])
    except Exception as e:
        discrepancies.append(("empty_words", "no exception", repr(e)))

    if discrepancies:
        msg = "FAIL {} ".format(TASK)
        for d in discrepancies[:3]:
            msg += "[case={}, expected={}, obtained={}] ".format(d[0], d[1], d[2])
        print(msg[:600])
        sys.exit(1)
    else:
        print("PASS")
        sys.exit(0)

run()
