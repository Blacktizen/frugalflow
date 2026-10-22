import unittest
from graph import components

class TestComponents(unittest.TestCase):
    def test_connected(self):
        adj = {"a": ["b"], "b": ["a", "c"], "c": ["b", "d"], "d": ["c"]}
        self.assertEqual(components.components(adj), [{"a", "b", "c", "d"}])
    def test_isolated(self):
        self.assertEqual(components.components({"a": [], "b": []}), [{"a"}, {"b"}])

if __name__ == "__main__":
    unittest.main()
