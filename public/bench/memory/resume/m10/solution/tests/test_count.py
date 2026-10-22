import unittest
from graph import count

class TestCount(unittest.TestCase):
    def test_count(self):
        self.assertEqual(count.edge_count({"a": ["b"], "b": ["a"]}), 1)
        self.assertEqual(count.edge_count({"a": ["b", "c"], "b": ["a"], "c": ["a"]}), 2)
        self.assertEqual(count.edge_count({}), 0)

if __name__ == "__main__":
    unittest.main()
