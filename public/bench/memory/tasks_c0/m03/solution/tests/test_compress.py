import unittest
from plan import compress

class TestCompress(unittest.TestCase):
    def test_overlap(self):
        self.assertEqual(compress.merge([(0, 10), (5, 15)]), [(0, 15)])
    def test_touching(self):
        self.assertEqual(compress.merge([(0, 10), (10, 20)]), [(0, 20)])
    def test_empty(self):
        self.assertEqual(compress.merge([]), [])
    def test_disjoint(self):
        self.assertEqual(compress.merge([(3, 4), (0, 1)]), [(0, 1), (3, 4)])
    def test_chain(self):
        self.assertEqual(compress.merge([(0, 10), (10, 20), (20, 30)]), [(0, 30)])

if __name__ == "__main__":
    unittest.main()
