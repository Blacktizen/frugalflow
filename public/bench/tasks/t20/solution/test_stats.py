import unittest
import stats


class TestStats(unittest.TestCase):
    def test_median_odd(self):
        self.assertEqual(stats.median([1, 2, 3]), 2)

    def test_median_even(self):
        self.assertEqual(stats.median([1, 2, 3, 4]), 2.5)

    def test_range_of(self):
        self.assertEqual(stats.range_of([3, 9, 1]), 8)

    def test_range_of_empty(self):
        with self.assertRaises(ValueError):
            stats.range_of([])

    def test_running_total(self):
        self.assertEqual(stats.running_total([1, 2, 3]), [1, 3, 6])

    def test_running_total_negative(self):
        self.assertEqual(stats.running_total([5, -2, 4]), [5, 3, 7])


if __name__ == "__main__":
    unittest.main()
