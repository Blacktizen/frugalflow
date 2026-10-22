import unittest
from graph import edges, shortest

class TestShortest(unittest.TestCase):
    def test_path(self):
        adj = {}
        edges.add_edge(adj, "a", "b")
        edges.add_edge(adj, "b", "c")
        edges.add_edge(adj, "a", "c")
        edges.add_edge(adj, "c", "d")
        self.assertEqual(shortest.shortest(adj, "a", "d"), ["a", "c", "d"])
    def test_self(self):
        self.assertEqual(shortest.shortest({}, "a", "a"), ["a"])
    def test_none(self):
        self.assertIsNone(shortest.shortest({"a": ["b"], "b": ["a"]}, "a", "z"))

if __name__ == "__main__":
    unittest.main()
