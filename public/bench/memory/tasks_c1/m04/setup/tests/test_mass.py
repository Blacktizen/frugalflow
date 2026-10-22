import unittest
from conv import mass

class TestMass(unittest.TestCase):
    def test_kg(self):
        self.assertEqual(mass.convert(1, "kg", "g"), 1000.0)
    def test_lb(self):
        self.assertAlmostEqual(mass.convert(1, "lb", "kg"), 0.45359237, places=9)
    def test_unknown(self):
        with self.assertRaises(ValueError):
            mass.convert(1, "kg", "stone")

if __name__ == "__main__":
    unittest.main()
