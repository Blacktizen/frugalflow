import os
import re
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quote_mask

KEYWORDS = "if|then|else|elif|fi|while|until|for|do|done|case|esac|function|select|read|export|declare|typeset|local|readonly|unset|eval|source|mapfile|readarray|getopts|let|alias|coproc|trap"
KEYWORDS_RE = re.compile(r"(?<![\w@./:%+~,-])(?<![\w]=)(" + KEYWORDS + r")(?![\w-])")
# zsh reads a word like ~local as a named directory, fails, and aborts the whole command;
# when such a word ends its segment the command is returned unchanged.
TILDE_KEYWORD_RE = re.compile(r"(?<![\w~])~(?:" + KEYWORDS + r")[\w-]*[ \t]*(?:[;&|\n)/<>{}\"']|$)")
PRINTF_V_RE = re.compile(r"(?<![\w-])printf\s+(?:-\S*\s+)*-v")
DOT_SOURCE_RE = re.compile(r"(?:^|[;&|\n(])\s*\.\s")
FUNCTION_RE = re.compile(r"[A-Za-z_][\w-]*\s*\(\s*\)")
ASSIGN_RE = re.compile(r"(?:^|(?<=[;\n]))[ \t]*([A-Za-z_][A-Za-z0-9_]*)=([A-Za-z0-9_./~$@%+,:=-]*)(?=[ \t]*(?:;|\n|&&|$))")
DELIM_NAME_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")


def heredoc_regions(text):
    """Return the (start, end, quoted) spans of the heredoc bodies in text
    (the delimiter line excluded, quoted True when the delimiter is written
    'DELIM', \"DELIM\" or \\DELIM), or None when a heredoc cannot be read:
    an unreadable delimiter, or a body whose delimiter line never comes."""
    if not isinstance(text, str):
        return []
    regions = []
    pending = []
    i = 0
    n = len(text)
    state = 0  # 0 outside, 1 single-quoted, 2 double-quoted
    while i < n:
        c = text[i]
        if state == 1:
            if c == "'":
                state = 0
            i += 1
        elif state == 2:
            if c == "\\" and i + 1 < n:
                i += 2
            elif c == '"':
                state = 0
                i += 1
            else:
                i += 1
        elif c == "\\" and i + 1 < n:
            i += 2
        elif c == "#" and (i == 0 or text[i - 1] in " \t\n;|&("):
            e = text.find("\n", i)
            i = n if e == -1 else e
        elif c == "'":
            state = 1
            i += 1
        elif c == '"':
            state = 2
            i += 1
        elif text[i:i + 2] == "<<" and text[i + 2:i + 3] != "<" and (i == 0 or text[i - 1] != "<"):
            q = i + 2
            dash = False
            if q < n and text[q] == "-":
                dash = True
                q += 1
            while q < n and text[q] in (" ", "\t"):
                q += 1
            quoted = False
            if q < n and text[q] in ("'", '"'):
                quoted = True
                m = DELIM_NAME_RE.match(text, q + 1)
                close = text.find(text[q], q + 1) if m is not None else -1
                if m is None or close == -1:
                    return None
                delim = m.group(0)
                end = close + 1
            elif q < n and text[q] == "\\":
                quoted = True
                m = DELIM_NAME_RE.match(text, q + 1)
                if m is None:
                    return None
                delim = m.group(0)
                end = q + 1 + len(delim)
            else:
                m = DELIM_NAME_RE.match(text, q)
                if m is None:
                    return None
                delim = m.group(0)
                end = q + len(delim)
            pending.append((delim, dash, quoted))
            i = end
        elif c == "\n" and pending:
            j = i + 1
            for delim, dash, quoted in pending:
                body_start = j
                closed = False
                while j < n:
                    e = text.find("\n", j)
                    e = n if e == -1 else e
                    line = text[j:e]
                    if (line.lstrip("\t") if dash else line) == delim:
                        regions.append((body_start, j, quoted))
                        j = e + 1
                        closed = True
                        break
                    j = e + 1
                if not closed:
                    return None
            pending = []
            i = j
        else:
            i += 1
    if pending:
        return None
    return regions


def blank_quoted_bodies(mask, regions):
    """Return mask with the characters of every quoted heredoc body replaced
    by spaces: a quoted body is data, never a sign of doubt."""
    chars = list(mask)
    for a, b, quoted in regions:
        if quoted:
            for k in range(a, b):
                chars[k] = " "
    return "".join(chars)


def resolve(text):
    """Replace $NAME and ${NAME} by the value of NAME when NAME is set earlier
    in the same command by a plain, certain assignment; at the least doubt the
    command is returned unchanged."""
    try:
        if not isinstance(text, str):
            return text
        # a heredoc body is data; a quoted body is never a sign of doubt.
        regions = heredoc_regions(text)
        if regions is None:
            return text
        masked = blank_quoted_bodies(quote_mask.mask_quotes(text), regions)
        if (KEYWORDS_RE.search(masked)
                or TILDE_KEYWORD_RE.search(masked)
                or PRINTF_V_RE.search(masked)
                or DOT_SOURCE_RE.search(masked)
                or FUNCTION_RE.search(masked)):
            return text
        braces = re.sub(r"\$\{[^{}]*\}", "", masked)
        if "{" in braces or "}" in braces:
            return text
        found = []
        for match in ASSIGN_RE.finditer(masked):
            name = match.group(1)
            start = match.start(1)
            end = match.end(2)
            value = text[match.start(2):end]
            if any(a <= start < b for a, b, _q in regions):
                continue  # an assignment written in a heredoc body is never one
            if (masked[:start].count("(") == masked[:start].count(")")
                    and len(re.findall(r"(?<![\w$])" + re.escape(name) + r"\+?=", text)) == 1
                    and re.search(r"\$\{" + re.escape(name) + r":?[=?+-]", text) is None
                    and "(" not in value and ")" not in value):
                found.append((name, value, end))
        found.sort(key=lambda x: x[2], reverse=True)
        live = [list(r) for r in regions]
        for name, value, end in found:
            # zsh turns $R:s/md/py/, $R:r, $R[2,-1] or $R(:r) into another name: never resolved.
            pattern = re.compile(r"(?<!\\)\$(?:\{" + re.escape(name) + r"\}|" + re.escape(name) + r"(?![A-Za-z0-9_]))(?![:\[(])")
            edits = []
            for m in pattern.finditer(text, end):
                if any(a <= m.start() < b for a, b, q in live if q):
                    continue  # a quoted body is data: the shell never expands it
                edits.append((m.start(), m.end()))
            for a, b in reversed(edits):
                delta = len(value) - (b - a)
                text = text[:a] + value + text[b:]
                for r in live:
                    if r[0] >= b:
                        r[0] += delta
                        r[1] += delta
                    elif r[1] > a:
                        r[1] += delta
        return text
    except Exception:
        return text


def _notice():
    lines = [
        "NAME      shell_vars.py - replaces $NAME in a shell command by its value when NAME is set earlier in the same command by a plain, certain assignment; at the least doubt the command is returned unchanged.",
        "READS     nothing: pure module; it works on the command text it is given, with quote_mask.py beside it.",
        "WRITES    nothing: resolve() returns the new command text; --resolve prints it.",
        "EXAMPLE   python3 shell_vars.py --resolve 'R=$PWD/notes.md; echo a >> $R'",
        "PITFALLS  2026-09-27 R=$PWD/x.md; printf x >> $R was refused as an unreadable target; a conditional, repeated or exported assignment is never resolved.",
        "          2026-10-09 git -c user.email=n@local commit && ln -sfn d $S/me was refused: local inside a word is not a command; after a space or a backslash it still is.",
        "          2026-10-10 a word or an assignment inside a here-document body was read as shell: a quoted body never blocks a name, and no body ever assigns one.",
    ]
    for line in lines:
        print(line)
    sys.exit(0)


def _autotest():
    F1 = 'R=$PWD/x.md; echo a >> $R; cat f >> "${R}"'
    O1 = 'R=$PWD/x.md; echo a >> $PWD/x.md; cat f >> "$PWD/x.md"'
    F2 = 'echo a >> $R; R=x.md'
    O2 = F2
    F3 = 'false && R=x.md; echo a > $R'
    O3 = F3
    F4 = 'R=x.md; R=y.py; echo a > $R'
    O4 = F4
    F5 = 'A=/tmp; B=$A/x.md; echo a > $B'
    O5 = 'A=/tmp; B=/tmp/x.md; echo a > /tmp/x.md'
    F6 = 'S=/tmp/q; git -c user.email=n@local commit -qam x && ln -sfn /a $S/v/me'
    O6 = 'S=/tmp/q; git -c user.email=n@local commit -qam x && ln -sfn /a /tmp/q/v/me'
    F7 = 'S=/tmp/q; ls /usr/local/bin > $S/x.txt'
    O7 = 'S=/tmp/q; ls /usr/local/bin > /tmp/q/x.txt'
    F7B = 'S=/tmp/q; true ~local a=local x:local; echo a > $S/x'
    O7B = 'S=/tmp/q; true ~local a=local x:local; echo a > /tmp/q/x'
    F8 = 'S=/tmp/q; local S=/etc; echo a > $S/x'
    O8 = F8
    F9 = 'S=/tmp/q; \\export S=/etc; echo a > $S/x'
    O9 = F9
    F10 = 'S=/tmp/q; true a@b;export S=/etc; echo a > $S/x'
    O10 = F10
    # a heredoc body is data; a quoted body never blocks a name.
    H1 = "S=/tmp/q; cat > o.txt <<'EOF'\nfor x in y:\n    if x: print(x)\nEOF\nrm -rf $S/b"
    O11 = "S=/tmp/q; cat > o.txt <<'EOF'\nfor x in y:\n    if x: print(x)\nEOF\nrm -rf /tmp/q/b"
    H2 = 'S=/tmp/q; cat > o.txt <<"EOF"\nwhile read l; do :; done\nEOF\nrm -rf $S/b'
    O12 = 'S=/tmp/q; cat > o.txt <<"EOF"\nwhile read l; do :; done\nEOF\nrm -rf /tmp/q/b'
    H3 = "S=/tmp/q; cat > o.txt <<\\EOF\nexport A=1\nEOF\nrm -rf $S/b"
    O13 = "S=/tmp/q; cat > o.txt <<\\EOF\nexport A=1\nEOF\nrm -rf /tmp/q/b"
    H4 = "S=/tmp/q; cat > o.txt <<'EOF'\n$S\nEOF\necho x > $S/c.txt"
    O14 = "S=/tmp/q; cat > o.txt <<'EOF'\n$S\nEOF\necho x > /tmp/q/c.txt"
    T1 = "cat > /dev/null <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R"
    T2 = "cat > /dev/null <<EOF\nR=/tmp/safe.md\nEOF\necho x > $R"
    T3 = "bash <<'EOF'\nR=/tmp/safe.md\nEOF\necho x > $R"
    T4 = "python3 - <<EOF\nR=1\nEOF\necho x > $R"
    T5 = "S=/tmp/q; cat > o.txt <<EOF\nfor x in y\nEOF\nrm -rf $S/b"
    T6 = "S=/tmp/q; source /dev/stdin <<'EOF'\nS=lib\nEOF\nrm -rf $S/b"
    T7 = "false && R=/tmp/safe.md; echo x > $R"
    T8 = "true || R=/tmp/safe.md\necho x > $R"

    tests = [
        (F1, O1, 0),
        (F2, O2, 1),
        (F3, O3, 1),
        (F4, O4, 1),
        (F5, O5, 0),
        (F6, O6, 0),
        (F7, O7, 0),
        (F7B, O7B, 0),
        (F8, O8, 1),
        (F9, O9, 1),
        (F10, O10, 1),
        (H1, O11, 0),
        (H2, O12, 0),
        (H3, O13, 0),
        (H4, O14, 0),
        (T1, T1, 1),
        (T2, T2, 1),
        (T3, T3, 1),
        (T4, T4, 1),
        (T5, T5, 1),
        (T6, T6, 1),
        (T7, T7, 1),
        (T8, T8, 1),
    ]

    all_pass = True
    for i, (fixture, expected, expected_code) in enumerate(tests, 1):
        proc = subprocess.run(
            [sys.executable, __file__, "--resolve", fixture],
            capture_output=True, text=True
        )
        stdout = proc.stdout.rstrip("\n")
        got_code = proc.returncode
        if stdout == expected and got_code == expected_code:
            print(f"PASS test {i}: expected={expected!r} code={expected_code} got={stdout!r} code={got_code}")
        else:
            print(f"FAIL test {i}: expected={expected!r} code={expected_code} got={stdout!r} code={got_code}")
            all_pass = False
    sys.exit(0 if all_pass else 1)


def _cli():
    if len(sys.argv) < 2:
        print("usage: shell_vars.py --resolve TEXT | --notice | --autotest")
        sys.exit(2)
    cmd = sys.argv[1]
    if cmd == "--resolve":
        if len(sys.argv) < 3:
            print("usage: shell_vars.py --resolve TEXT | --notice | --autotest")
            sys.exit(2)
        new = resolve(sys.argv[2])
        print(new)
        sys.exit(0 if new != sys.argv[2] else 1)
    elif cmd == "--notice":
        _notice()
    elif cmd == "--autotest":
        _autotest()
    else:
        print("usage: shell_vars.py --resolve TEXT | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "shell_vars", sys.argv[1:])
