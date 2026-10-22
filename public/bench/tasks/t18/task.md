This folder contains `strings.py` with three functions: capitalize_words(text), chunk(text, size) and count_vowels(text). Their behavior is:
- capitalize_words returns a new string where the first character of every space-separated word is upper case and every other character is lower case, with spaces preserved.
- chunk returns a list of substrings of length `size`; the last item may be shorter. A size of zero or less raises ValueError.
- count_vowels returns the number of vowels (a, e, i, o, u) in the text, ignoring case.

Write a file named `test_strings.py` using the standard library `unittest` module. It must contain at least three test methods that exercise these functions, including the error case described above. The checker imports your file, so do not run anything at import time: put unittest.main() inside an `if __name__ == "__main__":` block, or omit it.

Your tests must all pass when run against `strings.py` as given here. The checker also runs your tests against two faulty copies of `strings.py` and requires that at least one of your tests fails on each faulty copy.
