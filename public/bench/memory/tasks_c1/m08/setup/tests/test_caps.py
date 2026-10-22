import unittest
from backoff import caps

class TestCaps(unittest.TestCase):
    def test_cap(self):
        self.assertEqual(caps.cap(5, 10), 5)
        self.assertEqual(caps.cap(15, 10), 10)
        self.assertEqual(caps.cap(0, 0), 0)
    def test_error(self):
        with self.assertRaises(ValueError):
            caps.cap(5, -1)

if __name__ == "__main__":
    unittest.main()
