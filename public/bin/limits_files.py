"""limits_files.py - reads the two documents that set the ceilings of a delegation."""

import os
import json
import subprocess
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def read(cwd):
    """Read preferences.json in the FRUGALFLOW_HOME folder and .frugalflow.json in the working directory.

    preferences.json is never read beside a models.json a delegation points
    at: the ceilings come from the home folder (FRUGALFLOW_HOME, else
    ~/.frugalflow), whatever --models names.

    Returns a (prefs, project, error) tuple.
    """
    home = os.environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow")
    prefs_path = os.path.join(home, "preferences.json")
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
    "NAME      limits_files.py - reads the two documents that set the ceilings of a delegation: preferences.json in the FRUGALFLOW_HOME folder, and .frugalflow.json in the working directory.",
    "READS     preferences.json in FRUGALFLOW_HOME (else ~/.frugalflow), never beside a models.json a delegation points at; .frugalflow.json in the working directory it is given.",
    "WRITES    nothing: read() returns both documents (None when a file is absent), or an error starting with CEILING.",
    "EXAMPLE   python3 limits_files.py --autotest",
    "PITFALLS  2026-10-02 an absent file is not an error, an unreadable one is: a broken preferences.json must never be read as no preferences.",
    "          2026-11-06 a preferences.json lying beside a --models file set the ceilings from outside the home folder; preferences.json is now read only in the home folder.",
]


def autotest():
    """Run the five proof tests and return a process exit code."""
    PREFS_TEXT = '{"a": 1}'
    PROJECT_TEXT = '{"b": 2}'
    BROKEN_TEXT = '{"a": '

    all_passed = True
    saved_home = os.environ.get("FRUGALFLOW_HOME")

    for idx in range(1, 6):
        home = tempfile.mkdtemp()
        work = tempfile.mkdtemp()
        models_dir = None
        os.environ["FRUGALFLOW_HOME"] = home
        try:
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
                # A preferences.json beside another folder's models.json is not read.
                models_dir = tempfile.mkdtemp()
                with open(os.path.join(models_dir, "models.json"), "w", encoding="utf-8") as f:
                    f.write("{}")
                with open(os.path.join(models_dir, "preferences.json"), "w", encoding="utf-8") as f:
                    f.write(PREFS_TEXT)
                expected = (None, None, None)

            result = read(work)

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
            if saved_home is None:
                os.environ.pop("FRUGALFLOW_HOME", None)
            else:
                os.environ["FRUGALFLOW_HOME"] = saved_home
            shutil.rmtree(home)
            shutil.rmtree(work)
            if models_dir is not None:
                shutil.rmtree(models_dir)

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
