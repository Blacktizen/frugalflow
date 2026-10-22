import unittest
from conv import time

class TestTime(unittest.TestCase):
    def test_seconds(self):
        self.assertEqual(time.to_hours(3600, "s"), 1.0)
    def test_minutes(self):
        self.assertEqual(time.to_hours(30, "min"), 0.5)
    def test_day(self):
        self.assertEqual(time.to_hours(1, "day"), 24.0)
    def test_unknown(self):
        with self.assertRaises(ValueError):
            time.to_hours(1, "week")

if __name__ == "__main__":
    unittest.main()
