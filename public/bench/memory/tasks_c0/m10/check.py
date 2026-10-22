import sys

FAILED = []

def check(n, fn):
    try:
        fn()
    except Exception:
        FAILED.append(n)

def build():
    from graph import edges
    adj = {}
    edges.add_edge(adj, "a", "b")
    edges.add_edge(adj, "b", "c")
    edges.add_edge(adj, "a", "c")
    edges.add_edge(adj, "c", "d")
    return adj

def item1():
    from graph import edges
    assert edges.add_edge({}, "a", "b") == {"a": ["b"], "b": ["a"]}
    adj = build()
    assert edges.neighbors(adj, "b") == ["a", "c"]
    assert edges.neighbors(adj, "z") == []

def item2():
    from graph import degree
    adj = build()
    assert degree.degree(adj, "c") == 3
    assert degree.degree(adj, "z") == 0

def item3():
    from graph import components
    adj = build()
    assert components.components(adj) == [{"a", "b", "c", "d"}]
    assert components.components({"a": [], "b": []}) == [{"a"}, {"b"}]

def item4():
    from graph import reach
    adj = build()
    assert reach.reachable(adj, "a") == {"a", "b", "c", "d"}
    assert reach.reachable({"x": []}, "x") == {"x"}

def item5():
    from graph import shortest
    adj = build()
    assert shortest.shortest(adj, "a", "d") == ["a", "c", "d"]
    assert shortest.shortest(adj, "a", "a") == ["a"]
    assert shortest.shortest({"a": ["b"], "b": ["a"]}, "a", "z") is None

def item6():
    from graph import count
    adj = build()
    assert count.edge_count(adj) == 4
    assert count.edge_count({"a": ["b"], "b": ["a"]}) == 1
    assert count.edge_count({}) == 0

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
