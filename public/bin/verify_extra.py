#!/usr/bin/env python3
"""verify_extra.py - spots check commands that verify nothing."""

import shlex
import sys
import os
import subprocess

_NEQ = '-' + 'n' + 'e'

_PIPE_PROGRAMS = frozenset({
    'tail', 'head', 'cat', 'tee', 'wc', 'sort', 'uniq', 'less', 'more', 'nl',
})

_OPERATORS = frozenset({'|', '&', ';'})

_NOTICE = (
    "NAME      verify_extra.py - spots check commands that verify nothing: "
    "empty python code, parse-only python code, a masked exit status, "
    "a grep that matches anything; and tests that really compare a result.\n"
    "READS     nothing: pure functions on the command text it is given.\n"
    "WRITES    nothing: it prints a reason or OK.\n"
    "EXAMPLE   python3 verify_extra.py --weak 'python3 tool.py 2 3 || true'\n"
    "PITFALLS  2026-10-23 a check ending in || true or ; true could not fail "
    "and was accepted as a real verification.\n"
)

_USAGE = "usage: verify_extra.py --weak CMD | --strong-test SEGMENT | --notice | --autotest"


def _tokenize(cmd):
    """Tokenize a shell command string. Returns list or None on ValueError."""
    try:
        lexer = shlex.shlex(cmd, posix=True, punctuation_chars=True)
        lexer.whitespace_split = True
        raw = list(lexer)
    except ValueError:
        return None

    tokens = []
    for t in raw:
        if t == '||':
            tokens.append('|')
            tokens.append('|')
        elif t == '&&':
            tokens.append('&')
            tokens.append('&')
        else:
            tokens.append(t)
    return tokens


def _strip_imports(code):
    """Split code by ; and newline, remove instructions starting with import/from."""
    instructions = []
    current = ''
    for ch in code:
        if ch in (';', '\n'):
            instructions.append(current)
            current = ''
        else:
            current += ch
    instructions.append(current)
    remaining = []
    for inst in instructions:
        s = inst.strip()
        if s.startswith('import') or s.startswith('from'):
            continue
        remaining.append(s)
    return remaining


def _find_python_code(tokens):
    """Locate the -c code argument for python or python3. Returns the code string or None."""
    for i in range(len(tokens) - 2):
        if tokens[i] in ('python', 'python3') and tokens[i + 1] == '-c':
            return tokens[i + 2]
    return None


def _is_masked_value(tokens, start):
    """Check if tokens[start:] form a masked exit pattern: true, :, exit 0, or echo ..."""
    n = len(tokens)
    if start >= n:
        return False
    if start == n - 1 and tokens[start] == 'true':
        return True
    if start == n - 1 and tokens[start] == ':':
        return True
    if start + 1 == n - 1 and tokens[start] == 'exit' and tokens[start + 1] == '0':
        return True
    if tokens[start] == 'echo':
        for j in range(start + 1, n):
            if tokens[j] in _OPERATORS:
                return False
        return True
    return False


def _check_rule1_1b_2(tokens):
    """Apply rules 1, 1b, 2 for python -c code patterns."""
    code = _find_python_code(tokens)
    if code is None:
        return None

    remaining = _strip_imports(code)

    # Rule 1: empty, pass, or ...
    joined = ';'.join(remaining).strip()
    if joined == '' or joined == 'pass' or joined == '...':
        return "python code does nothing"

    # Rule 1b: all remaining start with print( or print (space)
    if remaining:
        non_empty = [r for r in remaining if r]
        if non_empty and all(
            r.startswith('print(') or r.startswith('print ')
            for r in non_empty
        ):
            return "python code only prints"

    # Rule 2: contains ast.parse or compile( but no assert/raise/exit
    if ('ast.parse' in code or 'compile(' in code):
        if 'assert' not in code and 'raise' not in code and 'exit' not in code:
            return "python code only parses"

    return None


def _check_rule3(tokens):
    """Apply rule 3: exit status masked by || true, ; true, ; echo, etc."""
    toks = tokens
    if toks and toks[0] == '(' and toks[-1] == ')':
        toks = toks[1:-1]
    if not toks:
        return False

    n = len(toks)

    # Exception: exit followed by a number != 0 anywhere means legit branching
    for i in range(n - 1):
        if toks[i] == 'exit':
            nxt = toks[i + 1]
            try:
                if int(nxt) != 0:
                    return False
            except ValueError:
                pass

    # Look for || (two adjacent |) or ; followed by a masked value at end
    for i in range(n - 2, -1, -1):
        if toks[i] == '|' and toks[i + 1] == '|':
            if _is_masked_value(toks, i + 2):
                return True
        if toks[i] == ';':
            if _is_masked_value(toks, i + 1):
                return True

    return False


def _check_rule3b(tokens):
    """Apply rule 3b: last pipe feeds a benign filter without pipefail."""
    # Find single | tokens (not part of ||)
    pipe_positions = []
    for i, t in enumerate(tokens):
        if t == '|':
            prev_pipe = (i > 0 and tokens[i - 1] == '|')
            next_pipe = (i < len(tokens) - 1 and tokens[i + 1] == '|')
            if not prev_pipe and not next_pipe:
                pipe_positions.append(i)

    if not pipe_positions:
        return False

    last_pipe = pipe_positions[-1]
    idx = last_pipe + 1
    if idx >= len(tokens):
        return False

    prog = os.path.basename(tokens[idx])
    if prog not in _PIPE_PROGRAMS:
        return False

    # No operator after the program
    for j in range(idx + 1, len(tokens)):
        if tokens[j] in _OPERATORS:
            return False

    # No token contains pipefail
    if any('pipefail' in t for t in tokens):
        return False

    return True


def _check_rule4(tokens):
    """Apply rule 4: match-anything grep at the end of a pipe."""
    n = len(tokens)
    if n < 3:
        return False

    pattern = tokens[-1]
    if pattern not in ('.', '.*', '^', ''):
        return False

    idx = n - 2
    while idx >= 0 and tokens[idx].startswith('-'):
        idx -= 1

    if idx < 0 or tokens[idx] != 'grep':
        return False

    idx -= 1
    if idx < 0 or tokens[idx] != '|':
        return False

    # Must be a single pipe, not part of ||
    if idx > 0 and tokens[idx - 1] == '|':
        return False

    return True


def weak_extra(cmd):
    """Analyze a shell command. Returns a reason string or None."""
    if not cmd or not cmd.strip():
        return None

    tokens = _tokenize(cmd)
    if tokens is None:
        return None
    if not tokens:
        return None

    # Rules 1, 1b, 2
    reason = _check_rule1_1b_2(tokens)
    if reason is not None:
        return reason

    # Rule 3
    if _check_rule3(tokens):
        return "exit status masked"

    # Rule 3b
    if _check_rule3b(tokens):
        return "pipe masks the exit status"

    # Rule 4
    if _check_rule4(tokens):
        return "match-anything grep"

    return None


def strong_test(segment):
    """Check if a test segment genuinely compares a result."""
    try:
        tokens = shlex.split(segment)
    except ValueError:
        return False

    if not tokens:
        return False

    first = tokens[0]
    if first not in ('test', '[', '[['):
        return False

    if '$(' not in segment:
        return False

    comparison_tokens = frozenset({'=', '==', '!=', '-eq', _NEQ})
    if any(tok in comparison_tokens for tok in tokens):
        return True

    return False


def _run_subprocess(args):
    """Run verify_extra.py in a subprocess, return (returncode, stdout)."""
    result = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout


def _autotest():
    """Run the 5 built-in tests. Print one PASS/FAIL line per test. Exit 0 or 1."""
    all_ok = True

    def check(desc, args, expected_code, expected_out):
        nonlocal all_ok
        code, out = _run_subprocess(args)
        got = out.strip() if out else ''
        exp = expected_out.strip() if expected_out else ''
        if code == expected_code and got == exp:
            print("PASS %s: expected code %d, expected %r; got code %d, got %r"
                  % (desc, expected_code, exp, code, got))
        else:
            all_ok = False
            print("FAIL %s: expected code %d, expected %r; got code %d, got %r"
                  % (desc, expected_code, exp, code, got))

    # Test 1: python code rules (1, 1b, 2)
    check(
        "T1a --weak python3 -c print(1)",
        ['--weak', 'python3 -c "print(1)"'],
        3, "python code only prints",
    )
    check(
        "T1b --weak python3 -c import sys;print",
        ['--weak', "python3 -c 'import sys; print(sys.version)'"],
        3, "python code only prints",
    )
    check(
        "T1c --weak python3 -c pass",
        ['--weak', "python3 -c pass"],
        3, "python code does nothing",
    )
    check(
        "T1d --weak python3 -c import os",
        ['--weak', "python3 -c 'import os'"],
        3, "python code does nothing",
    )
    check(
        "T1e --weak python3 -c ast.parse",
        ['--weak', "python3 -c 'import ast,sys;ast.parse(open(sys.argv[1]).read())' f.py"],
        3, "python code only parses",
    )

    # Test 2: exit status masked
    check(
        "T2a --weak || true",
        ['--weak', "python3 t.py 2 3 || true"],
        3, "exit status masked",
    )
    check(
        "T2b --weak ; true",
        ['--weak', "python3 t.py 2 3; true"],
        3, "exit status masked",
    )
    check(
        "T2c --weak ; echo $?",
        ['--weak', "python3 t.py 2 3; echo $?"],
        3, "exit status masked",
    )

    # Test 3: grep match-anything and pipe masks
    check(
        "T3a --weak grep -q .",
        ['--weak', "python3 t.py 2 3 | grep -q ."],
        3, "match-anything grep",
    )
    check(
        "T3b --weak | tail -3",
        ['--weak', "python3 t.py --autotest 2>&1 | tail -3"],
        3, "pipe masks the exit status",
    )
    check(
        "T3c --weak (|| true)",
        ['--weak', "(python3 t.py --autotest || true)"],
        3, "exit status masked",
    )

    # Test 4: non-weak commands and strong tests
    check(
        "T4a --weak python3 t.py --autotest",
        ['--weak', "python3 t.py --autotest"],
        0, "OK",
    )
    check(
        "T4b --weak && echo ok",
        ['--weak', "python3 t.py 2 3 && echo ok"],
        0, "OK",
    )
    check(
        "T4c --weak grep -q '^5$'",
        ['--weak', "python3 t.py 2 3 | grep -q '^5$'"],
        0, "OK",
    )
    check(
        "T4d --weak echo 'a; true'",
        ['--weak', "echo 'a; true'"],
        0, "OK",
    )
    check(
        "T4e --weak runpy assert",
        ['--weak', 'python3 -c \'import runpy;m=runpy.run_path("f.py");assert m["f"](2,3)==5\''],
        0, "OK",
    )
    check(
        "T4f --weak exit 1 || exit 0",
        ['--weak', "python3 t.py --autotest | grep -q FAIL && exit 1 || exit 0"],
        0, "OK",
    )
    check(
        "T4g --weak grep -c PASS",
        ['--weak', "python3 t.py --autotest 2>&1 | grep -c PASS"],
        0, "OK",
    )
    check(
        "T4h --weak pipefail tail",
        ['--weak', "set -o pipefail; python3 t.py --autotest | tail -3"],
        0, "OK",
    )
    check(
        "T4i --strong-test test $() = 5",
        ['--strong-test', 'test "$(python3 t.py 2 3)" = 5'],
        0, "STRONG",
    )
    check(
        "T4j --strong-test [ $() = 5 ]",
        ['--strong-test', '[ "$(python3 t.py 2 3)" = 5 ]'],
        0, "STRONG",
    )
    check(
        "T4k --strong-test test -f",
        ['--strong-test', 'test -f t.py'],
        1, "NOT STRONG",
    )
    check(
        "T4l --strong-test ls",
        ['--strong-test', 'ls'],
        1, "NOT STRONG",
    )

    # Test 5: usage, notice, exit codes 0/1/2/3 each exercised
    code, out = _run_subprocess([])
    got = out.strip()
    if code == 2 and got == _USAGE:
        print("PASS T5a usage: expected code 2; got code 2")
    else:
        all_ok = False
        print("FAIL T5a usage: expected code 2, %r; got code %d, %r"
              % (_USAGE, code, got.strip()))

    code, out = _run_subprocess(['--notice'])
    expected_notice = _NOTICE.rstrip('\n')
    got_notice = out.rstrip('\n')
    if code == 0 and got_notice == expected_notice:
        print("PASS T5b notice: expected code 0 and 5 notice lines; got code 0")
    else:
        all_ok = False
        print("FAIL T5b notice: expected code 0; got code %d" % code)

    # Verify exit codes 0, 1, 2, 3 are each exercised
    if all_ok:
        print("PASS T5c exit codes: codes 0,1,2,3 each exercised in prior tests")
    else:
        print("FAIL T5c exit codes: some prior test failed")

    sys.exit(0 if all_ok else 1)


def main():
    args = sys.argv[1:]

    if not args:
        print(_USAGE)
        sys.exit(2)

    opt = args[0]

    if opt == '--weak':
        if len(args) < 2:
            print(_USAGE)
            sys.exit(2)
        cmd = args[1]
        reason = weak_extra(cmd)
        if reason is not None:
            print(reason)
            sys.exit(3)
        else:
            print("OK")
            sys.exit(0)

    elif opt == '--strong-test':
        if len(args) < 2:
            print(_USAGE)
            sys.exit(2)
        segment = args[1]
        if strong_test(segment):
            print("STRONG")
            sys.exit(0)
        else:
            print("NOT STRONG")
            sys.exit(1)

    elif opt == '--notice':
        sys.stdout.write(_NOTICE)
        sys.exit(0)

    elif opt == '--autotest':
        _autotest()

    else:
        print(_USAGE)
        sys.exit(2)


if __name__ == '__main__':
    main()
