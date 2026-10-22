import sys


def main():
    import wrap
    cases = [
        ("hello world\nfoo bar", 5, ["hello", "world", "foo", "bar"]),
        ("a\nb", 10, ["a", "b"]),
        ("a\n\nb", 10, ["a", "", "b"]),
        ("a\tb", 5, ["a", "b"]),
        ("ab\tcd", 6, ["ab", "cd"]),
        ("ab\tcd", 5, ["ab", "cd"]),
        ("abcdefgh", 3, ["abc", "def", "gh"]),
        ("ab", 1, ["a", "b"]),
        ("hello world ", 11, ["hello world"]),
        ("foo\t", 10, ["foo"]),
        ("the quick brown fox", 10, ["the quick", "brown fox"]),
        ("one\ntwo three\nfour", 6, ["one", "two", "three", "four"]),
    ]
    for text, width, want in cases:
        try:
            got = wrap.wrap(text, width)
        except Exception as e:
            print("FAIL: wrap(%r, %r) raised %r" % (text, width, e))
            return 1
        if got != want:
            print("FAIL: wrap(%r, %r) = %r, want %r" % (text, width, got, want))
            return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
