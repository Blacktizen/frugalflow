import unittest
from stock import adjust

class TestAdjust(unittest.TestCase):
    def test_add_existing(self):
        totals = {"a": 5}
        out = adjust.apply(totals, "a", 3)
        self.assertEqual(out, {"a": 8})
        self.assertIs(out, totals)
    def test_new_name(self):
        self.assertEqual(adjust.apply({"a": 5}, "b", 2), {"a": 5, "b": 2})
    def test_zero(self):
        self.assertEqual(adjust.apply({}, "a", 0), {"a": 0})
    def test_negative_result(self):
        with self.assertRaises(ValueError):
            adjust.apply({"a": 2}, "a", -5)

if __name__ == "__main__":
    unittest.main()
