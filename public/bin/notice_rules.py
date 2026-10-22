import sys
import os
import re
import subprocess

SECTIONS = ["NAME", "READS", "WRITES", "EXAMPLE", "PITFALLS"]

NOTICE = (
    "NAME      notice_rules.py - says whether a tool notice follows the five-section contract.\n"
    "READS     nothing: pure module, it only reads the text it is given.\n"
    "WRITES    nothing: check() returns the list of defects, empty when the notice conforms.\n"
    "EXAMPLE   python3 notice_rules.py --notice\n"
    "PITFALLS  2026-09-22 a notice was counted as present because the word NOTICE: appeared once.\n"
    "          Presence proves nothing; each section is now checked.\n"
)

GOOD = (
    "NAME      demo.py - counts the lines of a file.\n"
    "READS     nothing from config; the file named on the command line.\n"
    "WRITES    nothing; prints one number.\n"
    "EXAMPLE   python3 demo.py notes.txt\n"
    "PITFALLS  2026-09-23 an empty file printed nothing instead of 0.\n"
)

NO_PITFALLS = (
    "NAME      demo.py - counts the lines of a file.\n"
    "READS     nothing from config; the file named on the command line.\n"
    "WRITES    nothing; prints one number.\n"
    "EXAMPLE   python3 demo.py notes.txt\n"
)

BAD_EXAMPLE = (
    "NAME      demo.py - counts the lines of a file.\n"
    "READS     nothing from config; the file named on the command line.\n"
    "WRITES    nothing; prints one number.\n"
    "EXAMPLE   python3 other.py notes.txt\n"
    "PITFALLS  an empty file printed nothing.\n"
)


def check(text, tool_name):
    if not text.strip():
        return ["empty notice"]

    defects = []
    sections = {}
    order = []
    current = None
    strays = []
    duplicates = []

    for line in text.split('\n'):
        if line.strip() == '':
            continue
        if line[0] in (' ', '\t'):
            if current is not None:
                sections[current] += '\n' + line.strip()
        else:
            parts = line.split()
            if not parts:
                continue
            first = parts[0]
            if first in SECTIONS:
                if first in sections:
                    duplicates.append(first)
                else:
                    body = line[len(first):].strip()
                    sections[first] = body
                    order.append(first)
                    current = first
            else:
                strays.append(line.strip())

    for s in strays:
        defects.append("stray line: " + s)

    for d in duplicates:
        defects.append("duplicate section " + d)

    for s in SECTIONS:
        if s not in sections:
            defects.append("missing section " + s)

    present_indices = [SECTIONS.index(s) for s in order]
    if present_indices != sorted(present_indices):
        defects.append("sections out of order")

    for s in SECTIONS:
        if s in sections and sections[s] == '':
            defects.append("empty section " + s)

    if 'NAME' in sections and '\n' in sections['NAME']:
        defects.append("NAME must fit on one line")

    if 'EXAMPLE' in sections and sections['EXAMPLE'] != '' and tool_name not in sections['EXAMPLE']:
        defects.append("EXAMPLE does not invoke " + tool_name)

    if 'PITFALLS' in sections and sections['PITFALLS'] != '':
        if not re.search(r"\d{4}-\d{2}-\d{2}", sections['PITFALLS']):
            defects.append("PITFALLS carries no date")

    return defects


def _autotest():
    failures = 0

    # Test 1
    expected = []
    got = check(GOOD, "demo.py")
    if got == expected:
        print("PASS 1: expected={} got={}".format(expected, got))
    else:
        print("FAIL 1: expected={} got={}".format(expected, got))
        failures += 1

    # Test 2
    expected = ["missing section PITFALLS"]
    got = check(NO_PITFALLS, "demo.py")
    if got == expected:
        print("PASS 2: expected={} got={}".format(expected, got))
    else:
        print("FAIL 2: expected={} got={}".format(expected, got))
        failures += 1

    # Test 3
    expected = ["EXAMPLE does not invoke demo.py", "PITFALLS carries no date"]
    got = check(BAD_EXAMPLE, "demo.py")
    if got == expected:
        print("PASS 3: expected={} got={}".format(expected, got))
    else:
        print("FAIL 3: expected={} got={}".format(expected, got))
        failures += 1

    # Test 4
    expected = ["empty notice"]
    got = check("", "demo.py")
    if got == expected:
        print("PASS 4: expected={} got={}".format(expected, got))
    else:
        print("FAIL 4: expected={} got={}".format(expected, got))
        failures += 1

    # Test 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    expected = []
    if proc.returncode == 0:
        got = check(proc.stdout, "notice_rules.py")
    else:
        got = None
    if proc.returncode == 0 and got is not None and got == expected:
        print("PASS 5: expected={} got={}".format(expected, got))
    else:
        print("FAIL 5: expected={} got={}".format(expected, got))
        failures += 1

    return 1 if failures else 0


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: notice_rules.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "notice_rules", sys.argv[1:])
