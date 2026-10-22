import unittest
from cfg import defaults

class TestDefaults(unittest.TestCase):
    def test_defaults(self):
        self.assertEqual(defaults.with_defaults({"a": 1}, {"a": 9, "b": 2}), {"a": 1, "b": 2})
    def test_none(self):
        self.assertEqual(defaults.with_defaults({"a": None}, {"a": 9}), {"a": 9})
    def test_missing(self):
        self.assertEqual(defaults.with_defaults({}, {"b": 2}), {"b": 2})

if __name__ == "__main__":
    unittest.main()
