import os
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

TASK = "t19"
MODULE = "parsing"
MIN_TESTS = 3

FAULTY_A = """def parse_key_values(text):
    result = {}
    for line in text.splitlines():
        if not line or line[0] == "#":
            continue
        key, value = line.split("=", 1)
        result[key] = value
    return result


def to_csv_row(fields):
    return ",".join(fields)


def parse_numbers(text):
    return [int(t) for t in text.split() if t.lstrip("-").isdigit()]
"""

FAULTY_B = """def parse_key_values(text):
    result = {}
    for line in reversed(text.splitlines()):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        key, value = stripped.split("=", 1)
        result[key.strip()] = value.strip()
    return result


def to_csv_row(fields):
    return ",".join('"' + f.replace('"', '""') + '"' for f in fields)


def parse_numbers(text):
    return [float(t) for t in text.split()]
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
