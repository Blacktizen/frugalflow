import unittest
from graph import edges

class TestEdges(unittest.TestCase):
    def test_add_edge(self):
        self.assertEqual(edges.add_edge({}, "a", "b"), {"a": ["b"], "b": ["a"]})
    def test_neighbors(self):
        adj = {}
        edges.add_edge(adj, "a", "b")
        edges.add_edge(adj, "b", "c")
        self.assertEqual(edges.neighbors(adj, "b"), ["a", "c"])
        self.assertEqual(edges.neighbors(adj, "z"), [])

if __name__ == "__main__":
    unittest.main()
