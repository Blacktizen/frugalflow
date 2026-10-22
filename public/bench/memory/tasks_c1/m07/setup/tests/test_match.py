import unittest
from router import match

class TestMatch(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(match.match("/a/b", "/a/b"))
    def test_wildcard(self):
        self.assertTrue(match.match("/a/*", "/a/b"))
        self.assertFalse(match.match("/a/*", "/a/b/c"))
    def test_root(self):
        self.assertTrue(match.match("/", "/"))
        self.assertTrue(match.match("*", "/x"))
    def test_no(self):
        self.assertFalse(match.match("/a", "/b"))

if __name__ == "__main__":
    unittest.main()
