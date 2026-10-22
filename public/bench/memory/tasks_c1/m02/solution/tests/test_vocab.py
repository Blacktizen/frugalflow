import unittest
from tok import vocab

class TestVocab(unittest.TestCase):
    def test_unique(self):
        self.assertEqual(vocab.unique_sorted(["b", "a", "b"]), ["a", "b"])
    def test_empty(self):
        self.assertEqual(vocab.unique_sorted([]), [])

if __name__ == "__main__":
    unittest.main()
