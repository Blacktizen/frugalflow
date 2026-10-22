import unittest
from graph import edges, reach

class TestReach(unittest.TestCase):
    def test_reachable(self):
        adj = {}
        edges.add_edge(adj, "a", "b")
        edges.add_edge(adj, "b", "c")
        self.assertEqual(reach.reachable(adj, "a"), {"a", "b", "c"})
    def test_singleton(self):
        self.assertEqual(reach.reachable({"x": []}, "x"), {"x"})

if __name__ == "__main__":
    unittest.main()
