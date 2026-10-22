import unittest
from graph import edges, degree

class TestDegree(unittest.TestCase):
    def test_degree(self):
        adj = {}
        edges.add_edge(adj, "a", "b")
        edges.add_edge(adj, "b", "c")
        self.assertEqual(degree.degree(adj, "b"), 2)
        self.assertEqual(degree.degree(adj, "z"), 0)

if __name__ == "__main__":
    unittest.main()
