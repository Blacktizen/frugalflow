import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def item1():
    from router import normalize
    assert normalize.normalize("/a//b/") == "/a/b"
    assert normalize.normalize("a/b") == "/a/b"
    assert normalize.normalize("") == "/"
    assert normalize.normalize("/") == "/"

def item2():
    from router import segments
    assert segments.segments("/a/b/") == ["a", "b"]
    assert segments.segments("/") == []
    assert segments.segments("a/b") == ["a", "b"]

def item3():
    from router import match
    assert match.match("/a/b", "/a/b") is True
    assert match.match("/a/*", "/a/b") is True
    assert match.match("/a/*", "/a/b/c") is False
    assert match.match("/", "/") is True
    assert match.match("*", "/x") is True
    assert match.match("/a", "/b") is False

def item4():
    from router import params
    assert params.extract("/users/:id", "/users/7") == {"id": "7"}
    assert params.extract("/a/:x/:y", "/a/1/2") == {"x": "1", "y": "2"}
    assert params.extract("/a/*", "/a/b") == {}
    assert params.extract("/a/b", "/a/c") is None
    assert params.extract("/a", "/a") == {}

def item5():
    from router import lookup
    routes = [("/users/:id", "show"), ("/ping", "ping")]
    assert lookup.lookup(routes, "/users/7") == ("show", {"id": "7"})
    assert lookup.lookup(routes, "/nope") is None

def item6():
    from router import url
    assert url.build("/users/{id}/posts/{pid}", {"id": "7", "pid": "3"}) == "/users/7/posts/3"
    assert url.build("/x/{a}", {"a": "1", "b": "2"}) == "/x/1"
    try:
        url.build("/x/{a}", {})
        raise AssertionError("missing param accepted")
    except ValueError:
        pass

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
