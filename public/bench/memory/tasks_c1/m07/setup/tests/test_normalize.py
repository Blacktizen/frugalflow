import unittest
from router import normalize

class TestNormalize(unittest.TestCase):
    def test_normalize(self):
        self.assertEqual(normalize.normalize("/a//b/"), "/a/b")
        self.assertEqual(normalize.normalize("a/b"), "/a/b")
        self.assertEqual(normalize.normalize(""), "/")
        self.assertEqual(normalize.normalize("/"), "/")
    def test_non_string(self):
        with self.assertRaises(ValueError):
            normalize.normalize(3)

if __name__ == "__main__":
    unittest.main()
