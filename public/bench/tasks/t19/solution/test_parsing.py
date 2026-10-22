import unittest
import parsing


class TestParsing(unittest.TestCase):
    def test_parse_key_values(self):
        self.assertEqual(parsing.parse_key_values("a=1\nb=2"), {"a": "1", "b": "2"})
        self.assertEqual(parsing.parse_key_values("  name = alice  \n"), {"name": "alice"})

    def test_parse_key_values_last_wins(self):
        self.assertEqual(parsing.parse_key_values("x=1\nx=2"), {"x": "2"})

    def test_to_csv_row(self):
        self.assertEqual(parsing.to_csv_row(["a", "b", "c"]), "a,b,c")
        self.assertEqual(parsing.to_csv_row(["a,b", "c"]), '"a,b",c')

    def test_parse_numbers(self):
        self.assertEqual(parsing.parse_numbers("1 2 3"), [1, 2, 3])
        self.assertEqual(parsing.parse_numbers(""), [])

    def test_parse_numbers_invalid(self):
        with self.assertRaises(ValueError):
            parsing.parse_numbers("1 x 3")


if __name__ == "__main__":
    unittest.main()
