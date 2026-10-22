import unittest
from tok import ngram

class TestNgram(unittest.TestCase):
    def test_bigrams(self):
        self.assertEqual(ngram.bigrams(["a", "b", "c"]), [("a", "b"), ("b", "c")])
    def test_short(self):
        self.assertEqual(ngram.bigrams(["a"]), [])
        self.assertEqual(ngram.bigrams([]), [])

if __name__ == "__main__":
    unittest.main()
