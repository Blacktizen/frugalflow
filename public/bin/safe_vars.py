#!/usr/bin/env python3
"""Replaces each $NAME or ${NAME} use of a variable in a shell command by the
value of NAME, only when NAME is bound exactly once, at the top level, to a
plain unquoted literal; at the least doubt the command is returned unchanged."""

import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quote_mask
import shell_vars

NOTICE = (
    "NAME      safe_vars.py - replaces each $NAME or ${NAME} use of a variable in a shell command by its value only when the variable is bound exactly once, at the top level, to a plain unquoted literal; at the least doubt the command is returned unchanged.\n"
    "READS     nothing: pure module; it works on the command text it is given, with quote_mask.py and shell_quotes.py beside it.\n"
    "WRITES    nothing: resolve() returns the new command text; --resolve prints it.\n"
    "EXAMPLE   python3 safe_vars.py --resolve 'S=/tmp/x; cp /tmp/a $S/g'\n"
    "PITFALLS  2026-10-05 a resolver that ignored a second binding (read, for, $(...), +=) let a write into a protected folder pass; any second binding now leaves the name unresolved.\n"
    "          2026-10-10 a word or an assignment inside a here-document body was read as shell: a quoted body never blocks a name, and no body ever assigns one.\n"
    "          2026-10-10 false && R=x.md was read as a binding: an assignment after && or || is conditional and never resolved.\n"
)

USAGE = "usage: safe_vars.py --autotest | --notice\n"

# a name is resolved only if every occurrence of it in the raw text
# is either its single top-level assignment or an exact $NAME / ${NAME} use.
NAME_RE = r"[A-Za-z_][A-Za-z0-9_]*"
VALUE_RE = r"[A-Za-z0-9_.\/+,:@%\-]+"
ASSIGN_RE = re.compile(r"[ \t]*(" + NAME_RE + r")=(" + VALUE_RE + ")")
ALONE_RE = re.compile(r"[ \t]*(?:&&|\|\||;|\n|&|$)")
EVAL_SOURCE_RE = re.compile(r"(?<![A-Za-z0-9_])(?:eval|source)(?![A-Za-z0-9_])")
DOT_HEAD_RE = re.compile(r"(?:^|[;&|\n(])\s*\.(?:\s|[;&|\n]|$)")
KEYWORD_UP_RE = re.compile(r"(?<![A-Za-z0-9_])(?:then|do)(?![A-Za-z0-9_=])")
KEYWORD_DOWN_RE = re.compile(r"(?<![A-Za-z0-9_])(?:fi|done|esac)(?![A-Za-z0-9_])")


def _single_quote_spans(text):
    """Return the (start, end) spans of single-quoted regions in text.

    Double quotes, backslash escapes and heredoc delimiters are respected, so
    a ' inside double quotes never opens a single-quoted region.
    """
    spans = []
    i = 0
    n = len(text)
    start = None
    in_double = False
    while i < n:
        c = text[i]
        if in_double:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == '"':
                in_double = False
            i += 1
        else:
            if c == "\\" and i + 1 < n:
                i += 2
                continue
            if c == "'":
                if start is None:
                    start = i
                else:
                    spans.append((start, i + 1))
                    start = None
            elif c == '"':
                in_double = True
            i += 1
    if start is not None:
        spans.append((start, n))
    return spans


def _body_regions(text):
    """Return the (start, end) spans of the heredoc bodies in text."""
    regions = shell_vars.heredoc_regions(text)
    if regions is None:
        return []
    return [(a, b) for a, b, _q in regions]


def _conditional_starts(masked):
    """Return the command starts where an assignment is conditional in the mask:
    after a && or a || whose left side is a bare test word (false, true), and
    after such a conditional in the same list. A side that does the work (cd a
    folder) keeps the assignment that follows it resolved."""
    cond = set()
    n = len(masked)
    elements = []
    start = 0
    i = 0
    while i < n:
        two = masked[i:i + 2]
        if two == "&&" or two == "||":
            elements.append((start, i, two))
            start = i + 2
            i += 2
        elif masked[i] in ";&|\n":
            elements.append((start, i, masked[i]))
            start = i + 1
            i += 1
        else:
            i += 1
    elements.append((start, n, ""))
    guarded = False
    for k in range(1, len(elements)):
        prev_start, prev_end, prev_op = elements[k - 1]
        if prev_op not in ("&&", "||"):
            guarded = False
            continue
        left = masked[prev_start:prev_end].strip()
        guarded = re.fullmatch(NAME_RE, left) is not None or guarded
        if guarded:
            cond.add(elements[k][0])
    return cond


def _depth_after(masked):
    """Return depth_after, where depth_after[i] is the structure depth after
    the character i of the mask: subshells, braces, backticks, then and do add
    one; fi, done, esac and closers remove one."""
    n = len(masked)
    up = set(m.start() for m in KEYWORD_UP_RE.finditer(masked))
    down = set(m.start() for m in KEYWORD_DOWN_RE.finditer(masked))
    depth = [0] * n
    d = 0
    for i in range(n):
        if i in up:
            d += 1
        elif i in down:
            d -= 1
        elif masked[i] in "({`":
            d += 1
        elif masked[i] in ")}":
            d -= 1
        depth[i] = d
    return depth


def _command_starts(masked):
    """Return the indexes that start a simple command in the mask: 0 and the
    index just after each top-level ; && || newline | or &."""
    starts = [0]
    i = 0
    n = len(masked)
    while i < n:
        two = masked[i:i + 2]
        if two == "&&" or two == "||":
            starts.append(i + 2)
            i += 2
        elif masked[i] in ";&|\n":
            starts.append(i + 1)
            i += 1
        else:
            i += 1
    return starts


def _resolve(text):
    masked, closed = quote_mask.scan(text)
    if not closed:
        return text
    # a heredoc body is data; an unreadable one is the least doubt.
    regions_q = shell_vars.heredoc_regions(text)
    if regions_q is None:
        return text
    masked = shell_vars.blank_quoted_bodies(masked, regions_q)
    text_q = shell_vars.blank_quoted_bodies(text, regions_q)
    # a command that may re-read its own text: nothing is resolved at all
    if EVAL_SOURCE_RE.search(text_q) is not None:
        return text
    if DOT_HEAD_RE.search(masked) is not None:
        return text

    regions = [(a, b) for a, b, _q in regions_q]
    quotes = _single_quote_spans(text)

    def in_body(i):
        for a, b in regions:
            if a <= i < b:
                return True
        return False

    def in_single(i):
        for a, b in quotes:
            if a <= i < b:
                return True
        return False

    depth = _depth_after(masked)
    conditional = _conditional_starts(masked)

    # the plain top-level assignments, alone on their simple command
    candidates = []
    for s in _command_starts(masked):
        m = ASSIGN_RE.match(masked, s)
        if m is None:
            continue
        if s > 0 and depth[s - 1] != 0:
            continue
        if ALONE_RE.match(masked, m.end()) is None:
            continue
        if in_body(m.start(1)):
            continue  # an assignment written in a heredoc body is never one
        if s in conditional:
            continue  # after && or || the assignment may never run
        candidates.append((m.group(1), m.group(2), m.start(1), m.end(2)))

    by_name = {}
    for name, value, a, e in candidates:
        by_name.setdefault(name, []).append((value, a, e))

    replacements = []
    for name, entries in by_name.items():
        if len(entries) != 1:
            continue
        value, a_start, a_end = entries[0]
        token = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(name) + r"(?![A-Za-z0-9_])")
        usages = []
        blocked = False
        for m in token.finditer(text):
            p = m.start()
            if a_start <= p < a_end:
                continue  # the binding itself, value included
            if in_body(p):
                # data of a heredoc body, not a command; but a name assigned
                # in a body is never resolved anywhere in the command
                tail = text[m.end():m.end() + 2]
                if tail.startswith("=") or tail.startswith("+="):
                    blocked = True
                    break
                continue
            if in_single(p):
                blocked = True
                break
            before = text[p - 1] if p > 0 else ""
            if before == "$":
                span = (p - 1, m.end())
            elif text[p - 2:p] == "${" and text[m.end():m.end() + 1] == "}":
                span = (p - 2, m.end() + 1)
            else:
                span = None
            if span is not None:
                if p < a_end:
                    blocked = True  # a use before the binding
                    break
                usages.append(span)
            else:
                blocked = True  # any other occurrence of the name
                break
        if blocked:
            continue
        for start_u, end_u in usages:
            replacements.append((start_u, end_u, value))

    replacements.sort(key=lambda r: r[0], reverse=True)
    for start_u, end_u, value in replacements:
        text = text[:start_u] + value + text[end_u:]
    return text


def resolve(text):
    """Replace $NAME and ${NAME} by the value of NAME when every condition of
    the module holds for NAME; at the least doubt, or on any internal error,
    the command is returned unchanged."""
    try:
        if not isinstance(text, str):
            return text
        return _resolve(text)
    except Exception:
        return text


def _autotest():
    fixtures = [
        ("S=/tmp/x; cp /tmp/a $S/g", "S=/tmp/x; cp /tmp/a /tmp/x/g"),
        ("S=/tmp/x && cp /tmp/a ${S}/g", "S=/tmp/x && cp /tmp/a /tmp/x/g"),
        ("S=/tmp/x; T=/tmp/y; cp $S/a $T/b", "S=/tmp/x; T=/tmp/y; cp /tmp/x/a /tmp/y/b"),
        ("echo $S; S=/tmp/x", "echo $S; S=/tmp/x"),
        ("S=/tmp/x; S=$(echo /y); cp /tmp/a $S/g", "S=/tmp/x; S=$(echo /y); cp /tmp/a $S/g"),
        ("S=/tmp/x; read S < f; cp /tmp/a $S/g", "S=/tmp/x; read S < f; cp /tmp/a $S/g"),
        ("S=/tmp/x; for S in /y; do cp /tmp/a $S/g; done", "S=/tmp/x; for S in /y; do cp /tmp/a $S/g; done"),
        ("S=/tmp/x; S+=/u; cp /tmp/a $S/g", "S=/tmp/x; S+=/u; cp /tmp/a $S/g"),
        ("S=/tmp/x; cp /tmp/a ${S:-/y}/g", "S=/tmp/x; cp /tmp/a ${S:-/y}/g"),
        ("S=/tmp/x; (S=/y; cp /tmp/a $S/g)", "S=/tmp/x; (S=/y; cp /tmp/a $S/g)"),
        ("S=/tmp/x; eval \"S=/y\"; cp /tmp/a $S/g", "S=/tmp/x; eval \"S=/y\"; cp /tmp/a $S/g"),
        ("S=/tmp/x; cp /tmp/a '$S/g'", "S=/tmp/x; cp /tmp/a '$S/g'"),
        # a heredoc body is data; a quoted body never blocks a name.
        ("S=/tmp/q; cat > o.txt <<'EOF'\nfor x in y:\n    if x: print(x)\nEOF\nrm -rf $S/b",
         "S=/tmp/q; cat > o.txt <<'EOF'\nfor x in y:\n    if x: print(x)\nEOF\nrm -rf /tmp/q/b"),
        ("S=/tmp/q; cat > o.txt <<'EOF'\n$S\nEOF\necho x > $S/c.txt",
         "S=/tmp/q; cat > o.txt <<'EOF'\n$S\nEOF\necho x > /tmp/q/c.txt"),
        ("cat > /dev/null <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R",
         "cat > /dev/null <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R"),
        ("cat > /dev/null <<EOF\nR=/tmp/safe.md\nEOF\necho x > $R",
         "cat > /dev/null <<EOF\nR=/tmp/safe.md\nEOF\necho x > $R"),
        ("bash <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R",
         "bash <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R"),
        ("python3 - <<EOF\nR=1\nEOF\necho x > $R",
         "python3 - <<EOF\nR=1\nEOF\necho x > $R"),
        ("S=/tmp/q; source /dev/stdin <<'EOF'\nS=lib\nEOF\nrm -rf $S/b",
         "S=/tmp/q; source /dev/stdin <<'EOF'\nS=lib\nEOF\nrm -rf $S/b"),
        ("false && R=/tmp/safe.md; echo x > $R", "false && R=/tmp/safe.md; echo x > $R"),
        ("true || R=/tmp/safe.md\necho x > $R", "true || R=/tmp/safe.md\necho x > $R"),
    ]
    all_pass = True
    for idx, (fixture, expected) in enumerate(fixtures, 1):
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--resolve", fixture],
            capture_output=True,
            text=True,
        )
        got = proc.stdout.rstrip("\n")
        if proc.returncode == 0 and got == expected:
            print("PASS fixture {}: expected={} got={}".format(idx, repr(expected), repr(got)))
        else:
            print("FAIL fixture {}: expected={} got={} code={}".format(
                idx, repr(expected), repr(got), proc.returncode))
            all_pass = False
    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]
    if len(args) == 1 and args[0] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(args) == 1 and args[0] == "--autotest":
        sys.exit(_autotest())
    elif len(args) == 2 and args[0] == "--resolve":
        sys.stdout.write(resolve(args[1]) + "\n")
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "safe_vars", sys.argv[1:])
