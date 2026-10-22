import unittest
from backoff import steps

class TestSteps(unittest.TestCase):
    def test_steps(self):
        self.assertEqual(steps.delay_at(2, 3, 0), 2)
        self.assertEqual(steps.delay_at(2, 3, 2), 18)
        self.assertEqual(steps.delay_at(2, 3, 3), 54)
    def test_error(self):
        with self.assertRaises(ValueError):
            steps.delay_at(2, 3, -1)

if __name__ == "__main__":
    unittest.main()
