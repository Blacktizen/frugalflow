import unittest
from cfg import get

class TestGet(unittest.TestCase):
    def test_get(self):
        self.assertEqual(get.get({"a": 1}, "a", 9), 1)
        self.assertEqual(get.get({"a": 1}, "b", 9), 9)
        self.assertEqual(get.get({"a": None}, "a", 9), 9)
        self.assertIsNone(get.get({}, "x"))

if __name__ == "__main__":
    unittest.main()
