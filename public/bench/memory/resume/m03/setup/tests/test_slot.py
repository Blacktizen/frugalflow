import unittest
from plan import slot

class TestSlot(unittest.TestCase):
    def test_normal(self):
        self.assertEqual(slot.parse_time("09:05"), 545)
    def test_bounds(self):
        self.assertEqual(slot.parse_time("00:00"), 0)
        self.assertEqual(slot.parse_time("23:59"), 1439)
    def test_errors(self):
        for bad in ["24:00", "12:60", "9:05", "12:3", "abc", "12", "1:2:3"]:
            with self.assertRaises(ValueError):
                slot.parse_time(bad)

if __name__ == "__main__":
    unittest.main()
