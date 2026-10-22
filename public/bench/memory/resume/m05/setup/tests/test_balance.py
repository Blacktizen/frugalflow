import unittest
from ledger import balance

class TestBalance(unittest.TestCase):
    def test_balance(self):
        self.assertEqual(balance.balance([("a", "x", 1.0), ("a", "y", -0.5)]), 0.5)
    def test_empty(self):
        self.assertEqual(balance.balance([]), 0.0)

if __name__ == "__main__":
    unittest.main()
