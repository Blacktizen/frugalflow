import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from tok import tokenize
    assert tokenize.words("Hello, world!") == ["hello", "world"]
    assert tokenize.words("") == []
    assert tokenize.words("...") == []
    assert tokenize.words("Straße 42") == ["straße", "42"]
    assert tokenize.words("  a  ") == ["a"]
    try:
        tokenize.words(5)
        raise AssertionError("non-string accepted")
    except ValueError:
        pass

def item2():
    from tok import count
    assert count.frequencies(["a", "b", "a"]) == {"a": 2, "b": 1}
    assert count.frequencies([]) == {}

def item3():
    from tok import stop
    assert stop.remove_stopwords(["a", "the", "b"], {"the"}) == ["a", "b"]
    assert stop.remove_stopwords(["x", "y", "z"], set()) == ["x", "y", "z"]

def item4():
    from tok import stem
    assert stem.stem("running") == "runn"
    assert stem.stem("ended") == "end"
    assert stem.stem("cats") == "cat"
    assert stem.stem("a") == "a"
    assert stem.stem("ss") == "ss"
    assert stem.stem("sings") == "sing"

def item5():
    from tok import ngram
    assert ngram.bigrams(["a", "b", "c"]) == [("a", "b"), ("b", "c")]
    assert ngram.bigrams(["a"]) == []
    assert ngram.bigrams([]) == []

def item6():
    from tok import vocab
    assert vocab.unique_sorted(["b", "a", "b"]) == ["a", "b"]
    assert vocab.unique_sorted([]) == []

check(1, item1)
check(2, item2)
check(3, item3)
check(4, item4)
check(5, item5)
check(6, item6)

if FAILED:
    print("FAIL " + " ".join(str(n) for n in FAILED))
    sys.exit(1)
print("PASS")
sys.exit(0)
