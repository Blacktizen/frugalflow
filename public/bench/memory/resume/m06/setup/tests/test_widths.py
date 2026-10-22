import unittest
from table import widths

class TestWidths(unittest.TestCase):
    def test_widths(self):
        self.assertEqual(widths.widths([["a", "bb"], ["ccc", "d"]]), [3, 2])
    def test_empty(self):
        self.assertEqual(widths.widths([]), [])
    def test_ragged(self):
        self.assertEqual(widths.widths([["a"], ["bb", "cc"]]), [2, 2])

if __name__ == "__main__":
    unittest.main()
