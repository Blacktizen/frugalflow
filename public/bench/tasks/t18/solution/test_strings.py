import unittest
import strings


class TestStrings(unittest.TestCase):
    def test_capitalize_words(self):
        self.assertEqual(strings.capitalize_words("hello world"), "Hello World")
        self.assertEqual(strings.capitalize_words("PYTHON is GREAT"), "Python Is Great")

    def test_capitalize_words_spaces(self):
        self.assertEqual(strings.capitalize_words("  a  b "), "  A  B ")

    def test_chunk(self):
        self.assertEqual(strings.chunk("abcdef", 2), ["ab", "cd", "ef"])
        self.assertEqual(strings.chunk("abcde", 2), ["ab", "cd", "e"])

    def test_chunk_bad_size(self):
        with self.assertRaises(ValueError):
            strings.chunk("abc", 0)

    def test_count_vowels(self):
        self.assertEqual(strings.count_vowels("Hello"), 2)
        self.assertEqual(strings.count_vowels("AEIOU"), 5)
        self.assertEqual(strings.count_vowels("xyz"), 0)


if __name__ == "__main__":
    unittest.main()
