import unittest
from plan import fit

class TestFit(unittest.TestCase):
    def test_empty_day(self):
        self.assertEqual(fit.find_slot([], 30, 0, 120), 0)
    def test_after_busy(self):
        self.assertEqual(fit.find_slot([(0, 30)], 30, 0, 120), 30)
        self.assertEqual(fit.find_slot([(0, 30), (60, 90)], 30, 0, 120), 30)
    def test_gap(self):
        self.assertEqual(fit.find_slot([(10, 20)], 30, 0, 60), 20)
    def test_no_room(self):
        self.assertIsNone(fit.find_slot([(0, 120)], 30, 0, 120))
    def test_errors(self):
        with self.assertRaises(ValueError):
            fit.find_slot([], 0, 0, 120)
        with self.assertRaises(ValueError):
            fit.find_slot([], 30, 60, 60)

if __name__ == "__main__":
    unittest.main()
