import unittest
from table import markdown

class TestMarkdown(unittest.TestCase):
    def test_table(self):
        self.assertEqual(markdown.table("a|b\n1|2"), "| a | b |\n| - | - |\n| 1 | 2 |\n")
    def test_empty(self):
        self.assertEqual(markdown.table(""), "")

if __name__ == "__main__":
    unittest.main()
