#!/usr/bin/env python3
"""Lifts every command substitution out of a shell command so each is judged on its own."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quote_mask


def extract_subshells(text):
    """Extract all command substitutions from a shell command string.

    Returns a tuple (outer, inners) where outer is the command text with each
    substitution replaced by __SUB__, and inners is a list of the extracted
    commands in order of appearance.

    Raises:
        ValueError: if any substitution is not properly closed.
    """
    if not isinstance(text, str):
        return ("", [])

    out = []
    inners = []
    i = 0
    n = len(text)
    state = "out"

    while i < n:
        # 1. Inside single quotes: consume literally until the closing quote.
        if state == "single":
            out.append(text[i])
            if text[i] == "'":
                state = "out"
            i += 1
            continue

        # 2. Backslash escape (outside single quotes).
        if text[i] == "\\" and i + 1 < n:
            out.append(text[i:i + 2])
            i += 2
            continue

        # 3. Command / arithmetic / process substitution: $( ), $(( ), <( ), >( ).
        two = text[i:i + 2]
        if two == "$(" or (state == "out" and (two == "<(" or two == ">(")):
            e = quote_mask.region_end(text, i + 2, "paren")
            if e == -1:
                raise ValueError("unbalanced subshell")
            inners.append(text[i + 2:e - 1].strip())
            out.append("__SUB__")
            i = e
            continue

        # 4. Backtick substitution.
        if text[i] == "`":
            e = quote_mask.region_end(text, i + 1, "tick")
            if e == -1:
                raise ValueError("unbalanced subshell")
            inners.append(text[i + 1:e - 1].strip())
            out.append("__SUB__")
            i = e
            continue

        # 5. Opening single quote.
        if state == "out" and text[i] == "'":
            out.append(text[i])
            state = "single"
            i += 1
            continue

        # 6. Opening double quote.
        if state == "out" and text[i] == '"':
            out.append(text[i])
            state = "double"
            i += 1
            continue

        # 7. Closing double quote.
        if state == "double" and text[i] == '"':
            out.append(text[i])
            state = "out"
            i += 1
            continue

        # 8. Default: consume one character.
        out.append(text[i])
        i += 1

    return ("".join(out), inners)


def _print_notice():
    print("NAME      subshells.py - lifts every command substitution out of a shell command ($( ), $(( )), backticks, <( ), >( )) so that each is judged on its own.")
    print("READS     nothing: pure module; it works on the command text it is given, with quote_mask.py beside it.")
    print('WRITES    nothing: extract_subshells() returns the outer text and the inner commands, or raises ValueError("unbalanced subshell").')
    print('EXAMPLE   python3 subshells.py --split \'echo "$(grep -c x f)" ; ls\'')
    print("PITFALLS  2026-09-27 a command inside $(( )) was never judged, and a quote inside $( ) within double quotes cut the substitution short.")


def _print_usage():
    print("usage: subshells.py --split TEXT | --notice | --autotest")


def _autotest():
    F1 = 'echo "a $(echo "b $(echo \'c"\')")" x'
    S1 = ['|echo "a __SUB__" x|', '|echo "b $(echo \'c"\')"|']
    F2 = 'echo $((1 + $(tee a.py))) z'
    S2 = ['|echo __SUB__ z|', '|(1 + $(tee a.py))|']
    F3 = 'diff <(ls a) `cat b` c'
    S3 = ['|diff __SUB__ __SUB__ c|', '|ls a|', '|cat b|']
    F4 = "echo '$(no)' \"`x`\""
    S4 = ['|echo \'$(no)\' "__SUB__"|', '|x|']
    F5 = 'echo "$(a'
    S5 = ['UNBALANCED']

    tests = [
        (F1, S1, 0),
        (F2, S2, 0),
        (F3, S3, 0),
        (F4, S4, 0),
        (F5, S5, 1),
    ]

    all_pass = True
    for idx, (fixture, expected, expected_rc) in enumerate(tests, 1):
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--split", fixture],
            capture_output=True,
            text=True,
        )
        got_lines = result.stdout.splitlines()
        got_rc = result.returncode
        if got_lines == expected and got_rc == expected_rc:
            print("PASS test {}: expected {} rc={} got {} rc={}".format(
                idx, expected, expected_rc, got_lines, got_rc))
        else:
            all_pass = False
            print("FAIL test {}: expected {} rc={} got {} rc={}".format(
                idx, expected, expected_rc, got_lines, got_rc))

    sys.exit(0 if all_pass else 1)


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--split":
        try:
            outer, inners = extract_subshells(args[1])
        except ValueError:
            print("UNBALANCED")
            sys.exit(1)
        print("|" + outer + "|")
        for inner in inners:
            print("|" + inner + "|")
        sys.exit(0)
    elif len(args) == 1 and args[0] == "--notice":
        _print_notice()
        sys.exit(0)
    elif len(args) == 1 and args[0] == "--autotest":
        _autotest()
    else:
        _print_usage()
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "subshells", sys.argv[1:])
