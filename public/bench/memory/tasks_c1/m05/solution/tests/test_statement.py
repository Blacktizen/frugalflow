import unittest
from ledger import statement

class TestStatement(unittest.TestCase):
    def test_render(self):
        entries = [("2026-10-22", "coffee", 1.0), ("2026-10-21", "tea", 2.5)]
        self.assertEqual(statement.render(entries), "2026-10-21 tea 2.5\n2026-10-22 coffee 1.0\n")
    def test_empty(self):
        self.assertEqual(statement.render([]), "")

if __name__ == "__main__":
    unittest.main()
