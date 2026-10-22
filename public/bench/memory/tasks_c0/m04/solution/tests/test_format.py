import unittest
from conv import format

class TestFormat(unittest.TestCase):
    def test_values(self):
        self.assertEqual(format.fmt(0, "m"), "0 m")
        self.assertEqual(format.fmt(1000, "m"), "1000 m")
        self.assertEqual(format.fmt(1.5, "kg"), "1.5 kg")
        self.assertEqual(format.fmt(2.0, "s"), "2 s")

if __name__ == "__main__":
    unittest.main()
