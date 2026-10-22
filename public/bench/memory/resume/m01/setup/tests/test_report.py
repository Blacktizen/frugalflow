import unittest
from stock import report

class TestReport(unittest.TestCase):
    def test_sorted(self):
        self.assertEqual(report.render({"b": 1, "a": 2}), "a: 2\nb: 1\n")
    def test_empty(self):
        self.assertEqual(report.render({}), "")

if __name__ == "__main__":
    unittest.main()
