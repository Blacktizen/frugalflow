import unittest
from conv import length

class TestLength(unittest.TestCase):
    def test_km(self):
        self.assertEqual(length.convert(1, "km", "m"), 1000.0)
    def test_cm(self):
        self.assertEqual(length.convert(100, "cm", "m"), 1.0)
    def test_zero(self):
        self.assertEqual(length.convert(0, "m", "km"), 0.0)
    def test_mi(self):
        self.assertAlmostEqual(length.convert(1, "mi", "km"), 1.609344, places=9)
    def test_unknown(self):
        with self.assertRaises(ValueError):
            length.convert(1, "m", "inch")

if __name__ == "__main__":
    unittest.main()
