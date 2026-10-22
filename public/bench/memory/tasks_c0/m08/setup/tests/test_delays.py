import unittest
from backoff import delays

class TestDelays(unittest.TestCase):
    def test_sequence(self):
        self.assertEqual(delays.exponential(2, 3, 3), [2, 6, 18])
    def test_zero(self):
        self.assertEqual(delays.exponential(2, 3, 0), [])
    def test_float(self):
        self.assertEqual(delays.exponential(1.5, 2, 3), [1.5, 3.0, 6.0])
    def test_errors(self):
        with self.assertRaises(ValueError):
            delays.exponential(2, 3, -1)
        with self.assertRaises(ValueError):
            delays.exponential(2, 3, 2.5)

if __name__ == "__main__":
    unittest.main()
