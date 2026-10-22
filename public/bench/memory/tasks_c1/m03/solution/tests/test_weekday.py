import unittest
from plan import weekday

class TestWeekday(unittest.TestCase):
    def test_names(self):
        self.assertEqual(weekday.day_index("Mon"), 0)
        self.assertEqual(weekday.day_index("sun"), 6)
    def test_errors(self):
        with self.assertRaises(ValueError):
            weekday.day_index("")
        with self.assertRaises(ValueError):
            weekday.day_index("funday")

if __name__ == "__main__":
    unittest.main()
