"""limits_files.py - reads the two documents that set the ceilings of a delegation."""

import os
import json
import subprocess
import sys
import tempfile
import shutil


def read(models_path, cwd):
    """Read preferences.json beside models.json and .frugalflow.json in the working directory.

    Returns a (prefs, project, error) tuple.
    """
    prefs_path = os.path.join(os.path.dirname(os.path.abspath(models_path)), "preferences.json")
    project_path = os.path.join(cwd, ".frugalflow.json")

    prefs = None
    project = None

    if os.path.exists(prefs_path):
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
        except (OSError, ValueError):
            return (None, None, "CEILING: " + prefs_path + " unreadable or invalid JSON")

    if os.path.exists(project_path):
        try:
            with open(project_path, "r", encoding="utf-8") as f:
                project = json.load(f)
        except (OSError, ValueError):
            return (None, None, "CEILING: " + project_path + " unreadable or invalid JSON")

    return (prefs, project, None)


NOTICE_LINES = [
    "NAME      limits_files.py - reads the two documents that set the ceilings of a delegation: preferences.json beside models.json, and .frugalflow.json in the working directory.",
    "READS     preferences.json beside the models.json path it is given; .frugalflow.json in the working directory it is given.",
    "WRITES    nothing: read() returns both documents (None when a file is absent), or an error starting with CEILING.",
    "EXAMPLE   python3 limits_files.py --autotest",
    "PITFALLS  2026-10-02 an absent file is not an error, an unreadable one is: a broken preferences.json must never be read as no preferences.",
]


def autotest():
    """Run the five proof tests and return a process exit code."""
    PREFS_TEXT = '{"a": 1}'
    PROJECT_TEXT = '{"b": 2}'
    BROKEN_TEXT = '{"a": '

    all_passed = True

    for idx in range(1, 6):
        home = tempfile.mkdtemp()
        work = tempfile.mkdtemp()
        try:
            with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
                f.write("{}")

            if idx == 1:
                expected = (None, None, None)
            elif idx == 2:
                with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
                    f.write(PREFS_TEXT)
                with open(os.path.join(work, ".frugalflow.json"), "w", encoding="utf-8") as f:
                    f.write(PROJECT_TEXT)
                expected = ({"a": 1}, {"b": 2}, None)
            elif idx == 3:
                with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
                    f.write(BROKEN_TEXT)
                expected = (None, None, "CEILING: " + os.path.join(home, "preferences.json") + " unreadable or invalid JSON")
            elif idx == 4:
                with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
                    f.write(PREFS_TEXT)
                with open(os.path.join(work, ".frugalflow.json"), "w", encoding="utf-8") as f:
                    f.write(BROKEN_TEXT)
                expected = (None, None, "CEILING: " + os.path.join(work, ".frugalflow.json") + " unreadable or invalid JSON")
            else:
                with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
                    f.write(PREFS_TEXT)
                expected = ({"a": 1}, None, None)

            if idx == 5:
                original_cwd = os.getcwd()
                os.chdir(home)
                try:
                    result = read("models.json", work)
                finally:
                    os.chdir(original_cwd)
            else:
                result = read(os.path.join(home, "models.json"), work)

            if idx == 5:
                proc = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True)
                passed = (result == expected) and (proc.returncode == 0) and proc.stdout.startswith("NAME      limits_files.py")
            else:
                passed = (result == expected)

            if not passed:
                all_passed = False

            status = "PASS" if passed else "FAIL"
            print(status + " " + str(idx) + " expected=" + repr(expected) + " got=" + repr(result))

        finally:
            shutil.rmtree(home)
            shutil.rmtree(work)

    return 0 if all_passed else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        for line in NOTICE_LINES:
            print(line)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(autotest())
    else:
        print("usage: limits_files.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "limits_files", sys.argv[1:])
