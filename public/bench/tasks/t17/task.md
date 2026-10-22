This folder contains `calc.py` with five functions: add(a, b), subtract(a, b), multiply(a, b), divide(a, b) and mean(values). Their behavior is:
- add returns a + b, subtract returns a - b, and multiply returns a * b.
- divide returns a / b, and raises ValueError when b is zero.
- mean returns the average of a non-empty list of numbers, and raises ValueError on an empty list.

Write a file named `test_calc.py` using the standard library `unittest` module. It must contain at least three test methods that exercise these functions, including the error cases described above. The checker imports your file, so do not run anything at import time: put unittest.main() inside an `if __name__ == "__main__":` block, or omit it.

Your tests must all pass when run against `calc.py` as given here. The checker also runs your tests against two faulty copies of `calc.py` and requires that at least one of your tests fails on each faulty copy.
