import unittest
from plan import overlap

class TestOverlap(unittest.TestCase):
    def test_overlap(self):
        self.assertTrue(overlap.overlap((0, 10), (5, 15)))
        self.assertTrue(overlap.overlap((5, 10), (0, 10)))
    def test_no_overlap(self):
        self.assertFalse(overlap.overlap((0, 10), (10, 20)))
        self.assertFalse(overlap.overlap((0, 10), (20, 30)))

if __name__ == "__main__":
    unittest.main()
