import unittest
from tok import stop

class TestStop(unittest.TestCase):
    def test_removes(self):
        self.assertEqual(stop.remove_stopwords(["a", "the", "b"], {"the"}), ["a", "b"])
    def test_order_preserved(self):
        self.assertEqual(stop.remove_stopwords(["x", "y", "z"], set()), ["x", "y", "z"])

if __name__ == "__main__":
    unittest.main()
