import unittest
from conv import square

class TestSquare(unittest.TestCase):
    def test_area(self):
        self.assertEqual(square.area(3, "m"), (9, "m2"))
    def test_zero(self):
        self.assertEqual(square.area(0, "km"), (0, "km2"))

if __name__ == "__main__":
    unittest.main()
