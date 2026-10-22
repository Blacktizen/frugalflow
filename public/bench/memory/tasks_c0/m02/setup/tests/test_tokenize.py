import unittest
from tok import tokenize

class TestTokenize(unittest.TestCase):
    def test_simple(self):
        self.assertEqual(tokenize.words("Hello, world!"), ["hello", "world"])
    def test_empty(self):
        self.assertEqual(tokenize.words(""), [])
    def test_punctuation_only(self):
        self.assertEqual(tokenize.words("..."), [])
    def test_unicode(self):
        self.assertEqual(tokenize.words("Straße 42"), ["straße", "42"])
    def test_surrounding_spaces(self):
        self.assertEqual(tokenize.words("  a  "), ["a"])
    def test_non_string(self):
        with self.assertRaises(ValueError):
            tokenize.words(5)

if __name__ == "__main__":
    unittest.main()
