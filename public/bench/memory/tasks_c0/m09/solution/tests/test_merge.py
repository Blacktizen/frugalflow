import unittest
from cfg import merge

class TestMerge(unittest.TestCase):
    def test_merge(self):
        self.assertEqual(merge.merge({"a": 1, "b": 2}, {"b": 3, "c": 4}), {"a": 1, "b": 3, "c": 4})
    def test_none_ignored(self):
        self.assertEqual(merge.merge({"a": 1}, {"a": None}), {"a": 1})
    def test_base_unchanged(self):
        base = {"a": 1}
        merge.merge(base, {"b": 2})
        self.assertEqual(base, {"a": 1})

if __name__ == "__main__":
    unittest.main()
