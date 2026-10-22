import unittest
from table import escape

class TestEscape(unittest.TestCase):
    def test_escape(self):
        self.assertEqual(escape.escape("a|b"), "a\\|b")
    def test_plain(self):
        self.assertEqual(escape.escape("abc"), "abc")
    def test_empty(self):
        self.assertEqual(escape.escape(""), "")

if __name__ == "__main__":
    unittest.main()
