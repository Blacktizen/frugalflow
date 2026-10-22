import unittest
from router import lookup

class TestLookup(unittest.TestCase):
    def test_lookup(self):
        routes = [("/users/:id", "show"), ("/ping", "ping")]
        self.assertEqual(lookup.lookup(routes, "/users/7"), ("show", {"id": "7"}))
    def test_missing(self):
        self.assertIsNone(lookup.lookup([("/users/:id", "show")], "/nope"))

if __name__ == "__main__":
    unittest.main()
