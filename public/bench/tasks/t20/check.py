import os
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

TASK = "t20"
MODULE = "stats"
MIN_TESTS = 3

FAULTY_A = """def median(values):
    ordered = sorted(values)
    return ordered[len(ordered) // 2]


def range_of(values):
    return max(values) - min(values)


def running_total(values):
    out = []
    product = 1
    for value in values:
        product *= value
        out.append(product)
    return out
"""

FAULTY_B = """def median(values):
    ordered = sorted(values)
    mid = len(ordered) // 2
    if len(ordered) % 2 == 1:
        return ordered[mid - 1]
    return (ordered[mid - 1] + ordered[mid]) / 2


def range_of(values):
    if not values:
        raise ValueError("empty list")
    return min(values) - max(values)


def running_total(values):
    total = 0
    out = []
    for value in values:
        total += value
        if total < 0:
            total = 0
        out.append(total)
    return out
"""


def run_tests(directory):
    sys.path.insert(0, directory)
    for name in list(sys.modules):
        if name == MODULE or name.startswith("test_"):
            del sys.modules[name]
    result = unittest.TestResult()
    try:
        loader = unittest.TestLoader()
        suite = loader.discover(directory, pattern="test_*.py", top_level_dir=directory)
        suite.run(result)
    except SystemExit:
        result.failures.append((None, "test module exited during import or run"))
    except Exception as exc:
        result.failures.append((None, "test run error: %s" % exc))
    return result


def copy_work(tmp_root):
    dst = os.path.join(tmp_root, "work")
    shutil.copytree(os.getcwd(), dst)
    return dst


def main():
    with tempfile.TemporaryDirectory() as tmp:
        correct = run_tests(copy_work(tmp))
    if correct.testsRun < MIN_TESTS or correct.failures or correct.errors:
        print("FAIL %s tests do not pass on the correct code (testsRun=%d failures=%d errors=%d)" % (
            TASK, correct.testsRun, len(correct.failures), len(correct.errors)))
        sys.exit(1)
    for label, source in (("A", FAULTY_A), ("B", FAULTY_B)):
        with tempfile.TemporaryDirectory() as tmp:
            work = copy_work(tmp)
            with open(os.path.join(work, MODULE + ".py"), "w") as handle:
                handle.write(source)
            result = run_tests(work)
        if result.testsRun < 1 or (not result.failures and not result.errors):
            print("FAIL %s tests do not catch faulty variant %s (testsRun=%d)" % (TASK, label, result.testsRun))
            sys.exit(1)
    print("PASS %s" % TASK)
    sys.exit(0)


if __name__ == "__main__":
    main()
