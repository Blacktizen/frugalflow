import os
import re
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import quote_mask
import shell_vars

ASSIGN_RE = re.compile(r"&&[ \t]*([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./~@%+,:-]+)(?=[ \t]*&&)")

def scope_end(masked, start):
    """Return the first position at or after start where a separator begins."""
    n = len(masked)
    i = start
    while i < n:
        c = masked[i]
        if c in ";\n()":
            return i
        if c == '|' and i + 1 < n and masked[i + 1] == '|':
            return i
        if c == '&':
            prev_amp_gt = (i > 0 and masked[i - 1] in '&>')
            next_amp_gt = (i + 1 < n and masked[i + 1] in '&>')
            if not prev_amp_gt and not next_amp_gt:
                return i
        i += 1
    return n

def resolve_chained(text):
    """Replace $NAME after a plain NAME=value between two && in the same chain."""
    if not isinstance(text, str):
        return text
    try:
        # a heredoc body is data; a quoted body is never a sign of doubt.
        regions = shell_vars.heredoc_regions(text)
        if regions is None:
            return text
        masked = shell_vars.blank_quoted_bodies(quote_mask.mask_quotes(text), regions)

        if (shell_vars.KEYWORDS_RE.search(masked) or
            shell_vars.PRINTF_V_RE.search(masked) or
            shell_vars.DOT_SOURCE_RE.search(masked) or
            shell_vars.FUNCTION_RE.search(masked) or
            any(seq in masked for seq in ("{", "}", "`", "$("))):
            return text

        edits = []
        for m in ASSIGN_RE.finditer(masked):
            name = m.group(1)
            value = m.group(2)

            if any(a <= m.start(1) < b for a, b, _q in regions):
                continue  # an assignment written in a heredoc body is never one
            if any(re.search(r"(?<![A-Za-z0-9_$])" + re.escape(name) + r"\+?=", text[a:b])
                   for a, b, _q in regions):
                continue  # a name assigned in a body is never resolved anywhere

            assignment_count_pattern = r"(?<![A-Za-z0-9_$])" + re.escape(name) + r"\+?="
            if len(re.findall(assignment_count_pattern, masked)) != 1:
                continue

            start = m.end()
            end = scope_end(masked, start)

            use_pattern = r"\$" + re.escape(name) + r"(?![A-Za-z0-9_])"
            for u in re.finditer(use_pattern, masked[start:end]):
                edits.append((start + u.start(), start + u.end(), value))

        if not edits:
            return text

        edits.sort(key=lambda x: x[0], reverse=True)
        result = text
        for a, b, val in edits:
            result = result[:a] + val + result[b:]
        return result
    except Exception:
        return text

CHANGED = [
    ('cd /x && f=a.md && sed -i "" -e "s/a/b/" $f && grep -c a $f', 'cd /x && f=a.md && sed -i "" -e "s/a/b/" a.md && grep -c a a.md'),
    ('cd /x && f=a.md && sed -i y $f; sed -i y $f', 'cd /x && f=a.md && sed -i y a.md; sed -i y $f'),
    ('true && f=a.md && cat $f 2>&1 && wc $f | head', 'true && f=a.md && cat a.md 2>&1 && wc a.md | head'),
    # a keyword inside a quoted here-document body is data, not shell.
    ("true && f=a.md && cat <<'EOF' && sed -i y $f\nfor x in y\nEOF",
     "true && f=a.md && cat <<'EOF' && sed -i y a.md\nfor x in y\nEOF"),
]

UNCHANGED = [
    'cd /nope && f=a.md; sed -i y $f',
    'f=a.md && f=b.py && sed -i y $f',
    'true && f=a.md || true && sed -i y $f',
    'f=a.md && echo | f=b.py && sed -i y $f',
    'true && f=a.md && { sed -i y $f; }',
    'true && f=a.md && sed -i y "$f"',
    'true && f=a.md && sed -i y $fx',
    'true && f=a.md && for x in 1; do sed -i y $f; done',
    'true && f=a.md && sleep 1 & sed -i y $f',
    'true && f=a.md && sed -i y $(echo $f)',
    # no here-document body ever assigns a name; an unquoted body keeps its doubt.
    "true && f=a.md && cat <<'EOF' && sed -i y $f\nf=b.py\nEOF",
    "true && f=a.md && cat <<EOF && sed -i y $f\nfor x in y\nEOF",
]

script_name = os.path.basename(__file__)
NOTICE = f"""NAME      {script_name} - resolves $NAME after a plain NAME=value placed between two && in a shell command, inside that same && chain only; at the least doubt the command is returned unchanged.
READS     the command text it is given; nothing on disk.
WRITES    nothing: resolve_chained() returns the command with the certain uses of the variable replaced.
EXAMPLE   python3 {script_name} --autotest
PITFALLS  2026-10-03 an assignment after && runs only when the chain gets there: a use after ; or || may see an inherited value, so it is never replaced.
          2026-10-10 a word or an assignment inside a here-document body was read as shell: a quoted body never blocks a name, and no body ever assigns one."""

USAGE = "usage: chain_vars.py --notice | --autotest"

def run_autotest():
    tests = []

    def test_changed():
        for idx, (inp, exp) in enumerate(CHANGED, 1):
            try:
                out = resolve_chained(inp)
            except Exception as e:
                out = f"EXCEPTION: {e}"
            if out != exp:
                return False, f"case {idx}: input={inp!r}, expected={exp!r}, got={out!r}"
        return True, f"all {len(CHANGED)} changed cases passed"

    def test_unchanged_first5():
        for idx, inp in enumerate(UNCHANGED[:5], 1):
            try:
                out = resolve_chained(inp)
            except Exception as e:
                out = f"EXCEPTION: {e}"
            if out != inp:
                return False, f"case {idx}: input={inp!r}, expected unchanged, got={out!r}"
        return True, f"all {len(UNCHANGED[:5])} first unchanged cases passed"

    def test_unchanged_last5():
        for idx, inp in enumerate(UNCHANGED[5:], 6):
            try:
                out = resolve_chained(inp)
            except Exception as e:
                out = f"EXCEPTION: {e}"
            if out != inp:
                return False, f"case {idx}: input={inp!r}, expected unchanged, got={out!r}"
        return True, f"all {len(UNCHANGED[5:])} last unchanged cases passed"

    def test_types_scope():
        if resolve_chained(None) is not None:
            return False, f"resolve_chained(None) expected None, got {resolve_chained(None)!r}"
        if resolve_chained(5) != 5:
            return False, f"resolve_chained(5) expected 5, got {resolve_chained(5)!r}"
        s1 = scope_end("a; b", 0)
        if s1 != 1:
            return False, f"scope_end('a; b', 0) expected 1, got {s1}"
        s2 = scope_end("a 2>&1 b", 0)
        if s2 != 8:
            return False, f"scope_end('a 2>&1 b', 0) expected 8, got {s2}"
        return True, "all type and scope_end checks passed"

    def test_notice_subprocess():
        try:
            proc = subprocess.run([sys.executable, __file__, "--notice"],
                                  capture_output=True, text=True)
            out = proc.stdout
            if proc.returncode != 0:
                return False, f"returncode={proc.returncode}, expected 0, stderr={proc.stderr!r}"
            expected_prefix = "NAME      " + script_name
            if not out.startswith(expected_prefix):
                return False, f"output does not start with {expected_prefix!r}, got {out[:50]!r}"
            return True, f"returncode=0 and output starts with {expected_prefix!r}"
        except Exception as e:
            return False, f"subprocess failed: {e}"

    tests.append(("CHANGED", test_changed))
    tests.append(("UNCHANGED first 5", test_unchanged_first5))
    tests.append(("UNCHANGED last 5", test_unchanged_last5))
    tests.append(("types and scope_end", test_types_scope))
    tests.append(("notice subprocess", test_notice_subprocess))

    all_pass = True
    for name, test_func in tests:
        passed, detail = test_func()
        status = "PASS" if passed else "FAIL"
        print(f"{status} {name}: {detail}")
        if not passed:
            all_pass = False
    return 0 if all_pass else 1

def main(argv=None):
    if argv is None:
        argv = sys.argv
    if len(argv) == 2 and argv[1] == "--notice":
        print(NOTICE)
        return 0
    elif len(argv) == 2 and argv[1] == "--autotest":
        return run_autotest()
    else:
        print(USAGE)
        return 2

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "chain_vars", sys.argv[1:])
