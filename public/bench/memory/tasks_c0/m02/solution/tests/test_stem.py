import unittest
from tok import stem

class TestStem(unittest.TestCase):
    def test_ing(self):
        self.assertEqual(stem.stem("running"), "runn")
    def test_ed(self):
        self.assertEqual(stem.stem("ended"), "end")
    def test_s(self):
        self.assertEqual(stem.stem("cats"), "cat")
    def test_short(self):
        self.assertEqual(stem.stem("a"), "a")
        self.assertEqual(stem.stem("ss"), "ss")
    def test_ing_before_s(self):
        self.assertEqual(stem.stem("sings"), "sing")

if __name__ == "__main__":
    unittest.main()
