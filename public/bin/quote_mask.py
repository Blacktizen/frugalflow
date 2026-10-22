#!/usr/bin/env python3
"""Masks the quoted text of a shell command the way the shell reads it."""

import os
import subprocess
import sys


def region_end(text, i, kind, level=0):
    """Return the index just after the character that closes the region.

    Returns -1 if the region is not closed before the end of text,
    or if the nesting level exceeds 50.
    """
    if level > 50:
        return -1
    n = len(text)
    k = i
    depth = 1
    while k < n:
        if kind == "tick":
            if text[k] == "\\" and k + 1 < n:
                k += 2
            elif text[k] == "`":
                return k + 1
            else:
                k += 1
        elif kind == "dquote":
            if text[k] == "\\" and k + 1 < n:
                k += 2
            elif text[k] == '"':
                return k + 1
            elif text[k:k + 2] == "$(":
                e = region_end(text, k + 2, "paren", level + 1)
                if e == -1:
                    return -1
                k = e
            elif text[k:k + 2] == "${":
                e = region_end(text, k + 2, "brace", level + 1)
                if e == -1:
                    return -1
                k = e
            elif text[k] == "`":
                e = region_end(text, k + 1, "tick", level + 1)
                if e == -1:
                    return -1
                k = e
            else:
                k += 1
        elif kind in ("paren", "brace"):
            if text[k] == "\\" and k + 1 < n:
                k += 2
            elif text[k] == "'":
                j = text.find("'", k + 1)
                if j == -1:
                    return -1
                k = j + 1
            elif text[k] == '"':
                e = region_end(text, k + 1, "dquote", level + 1)
                if e == -1:
                    return -1
                k = e
            elif text[k] == "`":
                e = region_end(text, k + 1, "tick", level + 1)
                if e == -1:
                    return -1
                k = e
            elif text[k:k + 2] == "$(":
                e = region_end(text, k + 2, "paren", level + 1)
                if e == -1:
                    return -1
                k = e
            elif text[k:k + 2] == "${":
                e = region_end(text, k + 2, "brace", level + 1)
                if e == -1:
                    return -1
                k = e
            elif kind == "paren" and text[k] == "#" and (
                k == i or text[k - 1] in " \t\n;|&("
            ):
                j = text.find("\n", k)
                if j == -1:
                    return -1
                k = j
            elif kind == "paren" and text[k] == "(":
                depth += 1
                k += 1
            elif kind == "paren" and text[k] == ")":
                depth -= 1
                if depth == 0:
                    return k + 1
                k += 1
            elif kind == "brace" and text[k] == "}":
                return k + 1
            else:
                k += 1
    return -1


def scan(text):
    """Return (mask, closed) where mask is the same length as text.

    Each character in mask is either the original character (when it is
    outside quoted regions) or a space (when it is inside a quoted region).
    closed is True only if all quotes are properly terminated.
    """
    if not isinstance(text, str):
        return ("", False)
    n = len(text)
    i = 0
    state = "out"
    mask = []
    while i < n:
        if state == "out":
            if text[i] == "'":
                mask.append(text[i])
                state = "single"
                i += 1
            elif text[i] == '"':
                mask.append(text[i])
                state = "double"
                i += 1
            elif text[i] == "\\" and i + 1 < n:
                mask.append(text[i])
                mask.append(text[i + 1])
                i += 2
            else:
                mask.append(text[i])
                i += 1
        elif state == "single":
            if text[i] == "'":
                mask.append(text[i])
                state = "out"
            else:
                mask.append(" ")
            i += 1
        elif state == "double":
            if text[i] == "\\" and i + 1 < n:
                mask.append(" ")
                mask.append(" ")
                i += 2
            elif text[i] == '"':
                mask.append(text[i])
                state = "out"
                i += 1
            elif text[i:i + 2] == "$(":
                e = region_end(text, i + 2, "paren")
                if e == -1:
                    mask.append(" " * (n - i))
                    return ("".join(mask), False)
                mask.append(" " * (e - i))
                i = e
            elif text[i:i + 2] == "${":
                e = region_end(text, i + 2, "brace")
                if e == -1:
                    mask.append(" " * (n - i))
                    return ("".join(mask), False)
                mask.append(" " * (e - i))
                i = e
            elif text[i] == "`":
                e = region_end(text, i + 1, "tick")
                if e == -1:
                    mask.append(" " * (n - i))
                    return ("".join(mask), False)
                mask.append(" " * (e - i))
                i = e
            else:
                mask.append(" ")
                i += 1
    closed = state == "out"
    return ("".join(mask), closed)


def mask_quotes(text):
    """Return the mask for the given command text."""
    return scan(text)[0]


def quotes_closed(text):
    """Return True if all quotes in the given text are closed."""
    if not isinstance(text, str):
        return False
    return scan(text)[1]


NOTICE = (
    "NAME      quote_mask.py - masks the quoted text of a shell command the way the shell reads it: a $( ), ${ } or backtick opened inside double quotes has its own quotes.\n"
    "READS     nothing: pure module; it works on the command text it is given.\n"
    "WRITES    nothing: scan() returns the mask and whether every quote is closed; --scan prints them.\n"
    "EXAMPLE   python3 quote_mask.py --scan 'echo \"$(grep -c x f)\"'\n"
    "PITFALLS  2026-09-27 echo \"$(grep -c '\"x' f)\" was read as an unterminated quote and refused: the quote inside $( ) does not close the outer one.\n"
)


def _autotest():
    """Run the five built-in test cases and report results."""
    F1 = 'echo "a $(b \')\' c) d" x'
    M1 = 'echo "' + ' ' * 14 + '" x'
    F2 = 'echo "$(grep -c \'"x\' f)" ; ls'
    M2 = 'echo "' + ' ' * 17 + '" ; ls'
    F3 = 'echo "$(tee a.py'
    M3 = 'echo "' + ' ' * 10
    F4 = 'echo \'a"b\' "c\\"d"'
    M4 = 'echo \'   \' "    "'
    F5 = 'echo "${X:-"a b"}" ; ls'
    M5 = 'echo "' + ' ' * 11 + '" ; ls'

    cases = [
        (F1, M1, "CLOSED", 0),
        (F2, M2, "CLOSED", 0),
        (F3, M3, "OPEN", 1),
        (F4, M4, "CLOSED", 0),
        (F5, M5, "CLOSED", 0),
    ]

    all_pass = True
    for idx, (fixture, expected_mask, expected_status, expected_code) in enumerate(cases, 1):
        expected_line1 = "|" + expected_mask + "|"
        proc = subprocess.run(
            [sys.executable, __file__, "--scan", fixture],
            capture_output=True,
            text=True,
        )
        lines = proc.stdout.splitlines()
        got_line1 = lines[0] if len(lines) > 0 else ""
        got_line2 = lines[1] if len(lines) > 1 else ""
        got_code = proc.returncode

        ok = (got_line1 == expected_line1 and got_line2 == expected_status and got_code == expected_code)
        if ok:
            print("PASS test {}: expected [{}] [{}] [{}], got [{}] [{}] [{}]".format(
                idx, expected_line1, expected_status, expected_code,
                got_line1, got_line2, got_code
            ))
        else:
            print("FAIL test {}: expected [{}] [{}] [{}], got [{}] [{}] [{}]".format(
                idx, expected_line1, expected_status, expected_code,
                got_line1, got_line2, got_code
            ))
            all_pass = False

    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]
    if len(args) == 1 and args[0] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(args) == 2 and args[0] == "--scan":
        text = args[1]
        mask, closed = scan(text)
        print("|" + mask + "|")
        if closed:
            print("CLOSED")
            sys.exit(0)
        else:
            print("OPEN")
            sys.exit(1)
    elif len(args) == 1 and args[0] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: quote_mask.py --scan TEXT | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "quote_mask", sys.argv[1:])
