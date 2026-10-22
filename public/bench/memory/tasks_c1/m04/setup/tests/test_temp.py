import unittest
from conv import temp

class TestTemp(unittest.TestCase):
    def test_c_to_f(self):
        self.assertEqual(temp.c_to_f(0), 32.0)
        self.assertEqual(temp.c_to_f(100), 212.0)
    def test_f_to_c(self):
        self.assertEqual(temp.f_to_c(32), 0.0)
        self.assertEqual(temp.f_to_c(212), 100.0)
    def test_c_to_k(self):
        self.assertEqual(temp.c_to_k(0), 273.15)

if __name__ == "__main__":
    unittest.main()
