import unittest
import calc


class TestCalc(unittest.TestCase):
    def test_add(self):
        self.assertEqual(calc.add(2, 3), 5)
        self.assertEqual(calc.add(-1, 1), 0)

    def test_subtract(self):
        self.assertEqual(calc.subtract(10, 4), 6)

    def test_multiply(self):
        self.assertEqual(calc.multiply(3, 4), 12)

    def test_divide(self):
        self.assertEqual(calc.divide(10, 2), 5)

    def test_divide_by_zero(self):
        with self.assertRaises(ValueError):
            calc.divide(1, 0)

    def test_mean(self):
        self.assertEqual(calc.mean([1, 2, 3]), 2)

    def test_mean_empty(self):
        with self.assertRaises(ValueError):
            calc.mean([])


if __name__ == "__main__":
    unittest.main()
