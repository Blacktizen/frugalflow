import unittest
from cfg import types

class TestTypes(unittest.TestCase):
    def test_is_int(self):
        self.assertTrue(types.is_int("12"))
        self.assertTrue(types.is_int("-3"))
        self.assertFalse(types.is_int("12.0"))
        self.assertFalse(types.is_int(""))
        self.assertFalse(types.is_int(12))
    def test_is_float(self):
        self.assertTrue(types.is_float("1.5"))
        self.assertTrue(types.is_float("1e3"))
        self.assertFalse(types.is_float("abc"))
    def test_is_bool(self):
        self.assertTrue(types.is_bool("TRUE"))
        self.assertTrue(types.is_bool(" yes "))
        self.assertFalse(types.is_bool("on"))
        self.assertFalse(types.is_bool(1))

if __name__ == "__main__":
    unittest.main()
