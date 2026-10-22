import sys


def main():
    import slug
    cases = [
        ("Café au Lait", 50, "cafe-au-lait"),
        ("Crème brûlée", 50, "creme-brulee"),
        ("Über München", 50, "uber-munchen"),
        ("Hello,   World!!!", 50, "hello-world"),
        ("__init__.py", 50, "init-py"),
        ("ab-cdefghij", 8, "ab"),
        ("the-quick-brown-fox", 10, "the-quick"),
        ("thisisalongslugwithnohyphen", 10, "thisisalon"),
        ("abc-def-ghi", 6, "abc"),
        ("Café---au--Lait", 50, "cafe-au-lait"),
        ("", 50, ""),
        ("---", 50, ""),
        ("Hello World", 5, "hello"),
    ]
    for text, max_len, want in cases:
        try:
            got = slug.slugify(text, max_len)
        except Exception as e:
            print("FAIL: slugify(%r, %r) raised %r" % (text, max_len, e))
            return 1
        if got != want:
            print("FAIL: slugify(%r, %r) = %r, want %r" % (text, max_len, got, want))
            return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
