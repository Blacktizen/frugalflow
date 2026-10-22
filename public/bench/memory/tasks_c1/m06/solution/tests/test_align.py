import unittest
from table import align

class TestAlign(unittest.TestCase):
    def test_left(self):
        self.assertEqual(align.pad("a", 4, "left"), "a   ")
    def test_right(self):
        self.assertEqual(align.pad("a", 4, "right"), "   a")
    def test_center(self):
        self.assertEqual(align.pad("a", 4, "center"), " a  ")
        self.assertEqual(align.pad("ab", 5, "center"), " ab  ")
    def test_unknown(self):
        with self.assertRaises(ValueError):
            align.pad("a", 4, "x")

if __name__ == "__main__":
    unittest.main()
