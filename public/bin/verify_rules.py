#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""verify_rules.py - judges a delegation's check command before sending."""

import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import verify_extra

HELP_FLAGS = {"--help", "-h", "--usage", "--version", "-V"}
INERT = {"true", ":", "echo", "printf", "ls", "cat", "test", "[", "stat", "file", "wc", "head", "tail", "which", "pwd", "grep", "find", "md5sum", "sha256sum", "shasum", "date", "env", "ps", "sort", "uniq"}
SYNTAX = [("node", "--check"), ("bash", "-n"), ("sh", "-n"), ("zsh", "-n"), ("perl", "-c"), ("ruby", "-c"), ("tsc", "--noEmit")]
STATIC = {"ruff", "flake8", "pylint", "mypy", "pyright", "eslint", "shellcheck", "black", "isort", "pyflakes"}
VAR = "FRUGALFLOW_CANDIDATE"

OUT = "/w/tool.py"
GOOD = 'python3 "$FRUGALFLOW_CANDIDATE" --autotest'
PIPE = 'python3 "$FRUGALFLOW_CANDIDATE" | grep -q 42'
FIX = '  To fix: run the tool on "$FRUGALFLOW_CANDIDATE" and require its verdict, for example --autotest, or pass --verify-weak REASON.'


def split_segments(cmd):
    if cmd is None:
        cmd = ""
    segments = []
    current = ""
    in_single = False
    in_double = False
    i = 0
    while i < len(cmd):
        ch = cmd[i]
        if not in_single and not in_double:
            if ch == "'":
                in_single = True
                current += ch
            elif ch == '"':
                in_double = True
                current += ch
            elif ch == '&' and i + 1 < len(cmd) and cmd[i + 1] == '&':
                segments.append(current)
                current = ""
                i += 2
                continue
            elif ch == '|' and i + 1 < len(cmd) and cmd[i + 1] == '|':
                segments.append(current)
                current = ""
                i += 2
                continue
            elif ch == '|':
                segments.append(current)
                current = ""
            elif ch == ';':
                segments.append(current)
                current = ""
            elif ch == '\n':
                segments.append(current)
                current = ""
            else:
                current += ch
        else:
            if in_single and ch == "'":
                in_single = False
            elif in_double and ch == '"':
                in_double = False
            current += ch
        i += 1
    segments.append(current)
    return segments


def weak_segment(segment):
    a = segment.strip()
    if not a:
        return "empty segment"
    try:
        words = shlex.split(segment)
    except ValueError:
        words = segment.split()
    if not words:
        return "empty segment"
    if verify_extra.strong_test(segment):
        return None
    prog = os.path.basename(words[0])
    options =[w for w in words[1:] if w.startswith("-")]
    if options and all(o in HELP_FLAGS for o in options):
        return "help or version only"
    if prog in INERT:
        return "inert program " + prog
    if "py_compile" in words or "compileall" in words:
        return "compile only"
    if prog in ("python", "python3") and "-c" in words:
        idx = words.index("-c")
        if idx + 1 < len(words):
            code_str = words[idx + 1]
            instrs = [s.strip() for s in re.split(r"[;\n]", code_str) if s.strip()]
            if instrs and all(s.startswith("import ") or s.startswith("from ") for s in instrs):
                return "imports only"
    for (p, o) in SYNTAX:
        if prog == p and o in words[1:]:
            return "syntax check only " + p + " " + o
    if prog in ("python", "python3") and "-m" in words[:-1] and words[words.index("-m") + 1] in STATIC:
        return "static analysis only " + words[words.index("-m") + 1]
    if prog in STATIC and "pytest" not in words:
        return "static analysis only " + prog
    return None


def weak_reason(cmd):
    extra = verify_extra.weak_extra(cmd)
    for seg in split_segments(cmd):
        why = weak_segment(seg)
        if why is None:
            return extra
    for seg in split_segments(cmd):
        why = weak_segment(seg)
        if why is not None:
            return why
    return extra


def correct(cmd, out):
    if not cmd or not out or VAR in cmd:
        return (cmd, False)
    refs = []
    for ref in [out, os.path.basename(out)]:
        if ref and ref not in refs:
            refs.append(ref)
    new_cmd = cmd
    for ref in refs:
        pattern = re.compile(r"(?<![\w./-])(['\"]?)" + re.escape(ref) + r"\1(?![\w./-])")
        new_cmd = pattern.sub(lambda m: '"$' + VAR + '"', new_cmd)
    change = new_cmd != cmd
    return (new_cmd, change)


def judge(cmd, out, waiver=None):
    if not cmd:
        return (0, cmd, [])
    cmd2, change = correct(cmd, out)
    lines = []
    if change:
        lines.append("VERIFY CORRECTED: the check named the target, which does not exist yet; it now runs on the candidate: " + cmd2)
    why = weak_reason(cmd2)
    if why is None:
        return (0, cmd2, lines)
    if waiver is not None and waiver.strip():
        lines.append("VERIFY WEAK ACCEPTED: " + why + " - waiver: " + waiver.strip())
        return (0, cmd2, lines)
    lines.append("VERIFY WEAK: " + why)
    lines.append(FIX)
    return (3, cmd2, lines)


NOTICE = (
    "NAME      verify_rules.py - judges a delegation's check command before sending: it must run something, and a check that names the target is rewritten to run on the candidate.\n"
    "READS     nothing: pure module; it works on the command and the target path it is given.\n"
    "WRITES    nothing: judge() returns the code (0 go, 3 weak check refused), the command to run and the lines to print.\n"
    "EXAMPLE   python3 verify_rules.py --notice\n"
    "PITFALLS  2026-09-25 a check that named the final target stopped the delegation; it is now corrected to the candidate, not refused.\n"
)

USAGE = "usage: verify_rules.py --notice | --autotest\n"


def _autotest():
    failures = 0

    # --- Test 1: split_segments ---
    exp1a = ["a ", " b ", " c ", " d", " e"]
    got1a = split_segments("a && b || c | d; e")
    exp1b = ["echo 'a;b' ", " x"]
    got1b = split_segments("echo 'a;b' && x")
    exp1c = [""]
    got1c = split_segments("")
    ok1 = got1a == exp1a and got1b == exp1b and got1c == exp1c
    if ok1:
        print("PASS 1: split_segments expected=" + repr(exp1a) + " got=" + repr(got1a))
    else:
        print("FAIL 1: split_segments expected=" + repr(exp1a) + " got=" + repr(got1a) + " | expected=" + repr(exp1b) + " got=" + repr(got1b) + " | expected=" + repr(exp1c) + " got=" + repr(got1c))
        failures += 1

    # --- Test 2: weak_reason ---
    checks = [
        (GOOD, None),
        (PIPE, None),
        ("python3 x.py --help", "help or version only"),
        ("ls -l && echo ok", "inert program ls"),
        ("python3 -m py_compile x.py", "compile only"),
        ("python3 -c 'import os; import sys'", "imports only"),
        ("bash -n run.sh", "syntax check only bash -n"),
        ("ruff check .", "static analysis only ruff"),
        ("  ", "empty segment"),
        ('python3 "$FRUGALFLOW_CANDIDATE" 2 3 || true', "exit status masked"),
        ("python3 -c pass", "python code does nothing"),
        ('test "$(python3 "$FRUGALFLOW_CANDIDATE" 2 3)" = 5', None),
    ]
    ok2 = True
    detail2 = ""
    for cmd_v, exp in checks:
        got = weak_reason(cmd_v)
        if got != exp:
            ok2 = False
            detail2 = "cmd=" + repr(cmd_v) + " expected=" + repr(exp) + " got=" + repr(got)
            break
    if ok2:
        print("PASS 2: weak_reason expected=None/None/help-or-version/inert/compile/imports/syntax/static/empty got=all-match")
    else:
        print("FAIL 2: weak_reason " + detail2)
        failures += 1

    # --- Test 3: correct ---
    exp3a = ('python3 "$FRUGALFLOW_CANDIDATE" --autotest', True)
    got3a = correct("python3 /w/tool.py --autotest", OUT)
    exp3b = ('python3 "$FRUGALFLOW_CANDIDATE" --autotest', True)
    got3b = correct("python3 'tool.py' --autotest", OUT)
    exp3c = ("python3 mytool.py --autotest", False)
    got3c = correct("python3 mytool.py --autotest", OUT)
    exp3d = (GOOD + " /w/tool.py", False)
    got3d = correct(GOOD + " /w/tool.py", OUT)
    exp3e = ("python3 x.py", False)
    got3e = correct("python3 x.py", "")
    ok3 = got3a == exp3a and got3b == exp3b and got3c == exp3c and got3d == exp3d and got3e == exp3e
    if ok3:
        print("PASS 3: correct expected=all-5-tuples-match got=all-5-tuples-match")
    else:
        parts = []
        if got3a != exp3a:
            parts.append("a exp=" + repr(exp3a) + " got=" + repr(got3a))
        if got3b != exp3b:
            parts.append("b exp=" + repr(exp3b) + " got=" + repr(got3b))
        if got3c != exp3c:
            parts.append("c exp=" + repr(exp3c) + " got=" + repr(got3c))
        if got3d != exp3d:
            parts.append("d exp=" + repr(exp3d) + " got=" + repr(got3d))
        if got3e != exp3e:
            parts.append("e exp=" + repr(exp3e) + " got=" + repr(got3e))
        print("FAIL 3: correct " + " | ".join(parts))
        failures += 1

    # --- Test 4: judge ---
    exp4a = (0, GOOD, [])
    got4a = judge(GOOD, OUT)
    exp4b = (0, GOOD, ["VERIFY CORRECTED: the check named the target, which does not exist yet; it now runs on the candidate: " + GOOD])
    got4b = judge("python3 /w/tool.py --autotest", OUT)
    exp4c = (3, "python3 -m py_compile x.py", ["VERIFY WEAK: compile only", FIX])
    got4c = judge("python3 -m py_compile x.py", OUT)
    exp4d = (0, "python3 -m py_compile x.py", ["VERIFY WEAK ACCEPTED: compile only - waiver: no test yet"])
    got4d = judge("python3 -m py_compile x.py", OUT, "no test yet")
    exp4e = 3
    got4e = judge("python3 -m py_compile x.py", OUT, "  ")[0]
    exp4f = (0, None, [])
    got4f = judge(None, OUT)
    ok4 = got4a == exp4a and got4b == exp4b and got4c == exp4c and got4d == exp4d and got4e == exp4e and got4f == exp4f
    if ok4:
        print("PASS 4: judge expected=6-tuples-match got=6-tuples-match")
    else:
        parts = []
        if got4a != exp4a:
            parts.append("a exp=" + repr(exp4a) + " got=" + repr(got4a))
        if got4b != exp4b:
            parts.append("b exp=" + repr(exp4b) + " got=" + repr(got4b))
        if got4c != exp4c:
            parts.append("c exp=" + repr(exp4c) + " got=" + repr(got4c))
        if got4d != exp4d:
            parts.append("d exp=" + repr(exp4d) + " got=" + repr(got4d))
        if got4e != exp4e:
            parts.append("e exp=" + repr(exp4e) + " got=" + repr(got4e))
        if got4f != exp4f:
            parts.append("f exp=" + repr(exp4f) + " got=" + repr(got4f))
        print("FAIL 4: judge " + " | ".join(parts))
        failures += 1

    # --- Test 5: subprocess ---
    r1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    ok5a = r1.returncode == 0 and r1.stdout.startswith("NAME      verify_rules.py")
    r2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True
    )
    ok5b = r2.returncode == 2 and r2.stdout == USAGE
    ok5 = ok5a and ok5b
    if ok5:
        print("PASS 5: subprocess expected=code0+NAME-prefix / code2+usage got=match")
    else:
        parts = []
        if not ok5a:
            parts.append("notice code=" + str(r1.returncode) + " stdout[:40]=" + repr(r1.stdout[:40]))
        if not ok5b:
            parts.append("noarg code=" + str(r2.returncode) + " stdout=" + repr(r2.stdout))
        print("FAIL 5: subprocess " + " | ".join(parts))
        failures += 1

    return 1 if failures else 0


def main():
    args = sys.argv[1:]
    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if args == ["--autotest"]:
        sys.exit(_autotest())
    sys.stdout.write(USAGE)
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "verify_rules", sys.argv[1:])
