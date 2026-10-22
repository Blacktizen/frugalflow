import unittest
from cfg import intval

class TestIntval(unittest.TestCase):
    def test_to_int(self):
        self.assertEqual(intval.to_int(None, 5, 0, 10), 5)
        self.assertEqual(intval.to_int("7", 0, 0, 10), 7)
        self.assertEqual(intval.to_int(7, 0, 0, 10), 7)
    def test_errors(self):
        for bad in ["11", "abc", True]:
            with self.assertRaises(ValueError):
                intval.to_int(bad, 0, 0, 10)

if __name__ == "__main__":
    unittest.main()
