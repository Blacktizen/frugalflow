import unittest
from cfg import schema

class TestSchema(unittest.TestCase):
    def test_missing_reported(self):
        self.assertEqual(schema.check({"a": 5}, {"a": lambda v: v > 0, "b": lambda v: v > 0}), ["b"])
    def test_false_predicate(self):
        self.assertEqual(schema.check({"a": -1}, {"a": lambda v: v > 0}), ["a"])
    def test_order(self):
        self.assertEqual(schema.check({}, {"a": lambda v: True, "b": lambda v: True}), ["a", "b"])
    def test_all_ok(self):
        self.assertEqual(schema.check({"a": 1}, {"a": lambda v: v > 0}), [])

if __name__ == "__main__":
    unittest.main()
