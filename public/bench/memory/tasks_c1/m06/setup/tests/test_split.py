import unittest
from table import split

class TestSplit(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(split.split("a|b\n1|2"), [["a", "b"], ["1", "2"]])
    def test_pipes(self):
        self.assertEqual(split.split("|a|b|\n|c|d|"), [["a", "b"], ["c", "d"]])
    def test_empty(self):
        self.assertEqual(split.split(""), [])
    def test_empty_cell(self):
        self.assertEqual(split.split("a||b"), [["a", "", "b"]])
    def test_blank_lines(self):
        self.assertEqual(split.split("  a | b  \n\n c|d"), [["a", "b"], ["c", "d"]])

if __name__ == "__main__":
    unittest.main()
