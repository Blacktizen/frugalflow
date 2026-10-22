This folder contains `stats.py` with three functions: median(values), range_of(values) and running_total(values). Their behavior is:
- median returns the middle value of a non-empty list of numbers when the length is odd, and the average of the two middle values when the length is even.
- range_of returns the largest value minus the smallest value, and raises ValueError on an empty list.
- running_total returns a list where each element is the sum of all values up to that position, so running_total([1, 2, 3]) is [1, 3, 6].

Write a file named `test_stats.py` using the standard library `unittest` module. It must contain at least three test methods that exercise these functions, including the error case described above. The checker imports your file, so do not run anything at import time: put unittest.main() inside an `if __name__ == "__main__":` block, or omit it.

Your tests must all pass when run against `stats.py` as given here. The checker also runs your tests against two faulty copies of `stats.py` and requires that at least one of your tests fails on each faulty copy.
