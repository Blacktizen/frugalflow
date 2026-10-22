import unittest
from plan import total

class TestTotal(unittest.TestCase):
    def test_touching(self):
        self.assertEqual(total.total([(0, 10), (10, 20)]), 20)
    def test_empty(self):
        self.assertEqual(total.total([]), 0)
    def test_disjoint(self):
        self.assertEqual(total.total([(0, 10), (30, 40)]), 20)

if __name__ == "__main__":
    unittest.main()
