import unittest
from backoff import budget

class TestBudget(unittest.TestCase):
    def test_prefix(self):
        self.assertEqual(budget.within_budget([5, 5, 5], 12), [5, 5])
    def test_empty(self):
        self.assertEqual(budget.within_budget([], 10), [])
    def test_all(self):
        self.assertEqual(budget.within_budget([3, 4, 2], 10), [3, 4, 2])
    def test_none(self):
        self.assertEqual(budget.within_budget([10, 1], 9), [])

if __name__ == "__main__":
    unittest.main()
