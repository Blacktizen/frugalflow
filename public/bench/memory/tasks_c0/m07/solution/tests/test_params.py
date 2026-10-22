import unittest
from router import params

class TestParams(unittest.TestCase):
    def test_params(self):
        self.assertEqual(params.extract("/users/:id", "/users/7"), {"id": "7"})
        self.assertEqual(params.extract("/a/:x/:y", "/a/1/2"), {"x": "1", "y": "2"})
    def test_wildcard(self):
        self.assertEqual(params.extract("/a/*", "/a/b"), {})
    def test_nomatch(self):
        self.assertIsNone(params.extract("/a/b", "/a/c"))
    def test_root(self):
        self.assertEqual(params.extract("/a", "/a"), {})

if __name__ == "__main__":
    unittest.main()
