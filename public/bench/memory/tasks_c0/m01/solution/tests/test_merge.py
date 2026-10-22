import unittest
from stock import merge

class TestMerge(unittest.TestCase):
    def test_merge(self):
        left = {"a": 1, "b": 2}
        right = {"b": 3, "c": 4}
        self.assertEqual(merge.merge(left, right), {"a": 1, "b": 5, "c": 4})
        self.assertEqual(left, {"a": 1, "b": 2})
        self.assertEqual(right, {"b": 3, "c": 4})
    def test_empty(self):
        self.assertEqual(merge.merge({}, {}), {})

if __name__ == "__main__":
    unittest.main()
