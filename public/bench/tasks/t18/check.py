import os
import shutil
import sys
import tempfile
import unittest

sys.dont_write_bytecode = True

TASK = "t18"
MODULE = "strings"
MIN_TESTS = 3

FAULTY_A = """def capitalize_words(text):
    return text.capitalize()


def chunk(text, size):
    return [text[i:i + size] for i in range(0, len(text) - size + 1, size)]


def count_vowels(text):
    return sum(1 for ch in text if ch in "aeiou")
"""

FAULTY_B = """def capitalize_words(text):
    return text.upper()


def chunk(text, size):
    return [text[i:i + size] for i in range(0, len(text), size)][::-1]


def count_vowels(text):
    return sum(1 for ch in text.lower() if ch in "aeiouy")
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
