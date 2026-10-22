import unittest
from router import segments

class TestSegments(unittest.TestCase):
    def test_segments(self):
        self.assertEqual(segments.segments("/a/b/"), ["a", "b"])
        self.assertEqual(segments.segments("/"), [])
        self.assertEqual(segments.segments("a/b"), ["a", "b"])

if __name__ == "__main__":
    unittest.main()
