import unittest
from stock import parse

class TestParse(unittest.TestCase):
    def test_full(self):
        self.assertEqual(parse.parse_line("widget,12,kg"), ("widget", 12, "kg"))
    def test_default_unit(self):
        self.assertEqual(parse.parse_line("bolt,3"), ("bolt", 3, "pcs"))
    def test_spaces(self):
        self.assertEqual(parse.parse_line(" nut , 7 , "), ("nut", 7, "pcs"))
    def test_zero(self):
        self.assertEqual(parse.parse_line("a,0"), ("a", 0, "pcs"))
    def test_negative(self):
        with self.assertRaises(ValueError):
            parse.parse_line("x,-1,kg")
    def test_bad_qty(self):
        with self.assertRaises(ValueError):
            parse.parse_line("x,abc")
    def test_empty_name(self):
        with self.assertRaises(ValueError):
            parse.parse_line(",5")
    def test_empty_line(self):
        with self.assertRaises(ValueError):
            parse.parse_line("")
    def test_too_many(self):
        with self.assertRaises(ValueError):
            parse.parse_line("a,1,kg,extra")

if __name__ == "__main__":
    unittest.main()
