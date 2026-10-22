import unittest
from router import url

class TestUrl(unittest.TestCase):
    def test_build(self):
        self.assertEqual(url.build("/users/{id}/posts/{pid}", {"id": "7", "pid": "3"}), "/users/7/posts/3")
    def test_extra_ignored(self):
        self.assertEqual(url.build("/x/{a}", {"a": "1", "b": "2"}), "/x/1")
    def test_missing(self):
        with self.assertRaises(ValueError):
            url.build("/x/{a}", {})

if __name__ == "__main__":
    unittest.main()
