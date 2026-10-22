import re
import os
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import quote_mask

# Fixtures
H1 = "python3 - <<'EOF'\nprint('<path>')\nEOF\nls"
H2 = "cat <<-END > out.py\n\tx = 1\n\tEND\necho done"
H3 = "cat <<A <<B\na1\nA\nb1\nb2\nB"
H4 = 'grep x <<< "a" ; echo "<<EOF"'
H5 = "cat <<EOF\nno end"
M1 = "echo 'a\nb' <<EOF\nbody\nEOF"
M2 = "cat <<EOF\ndon't\nEOF\necho 'x'"
P1 = 'python3 -c "\n# not a comment\n" # real'

# Functions
def mask_quotes(text):
    # a quote inside $( ) opened in double quotes has its own quotes (quote_mask.py).
    return quote_mask.scan(text)[0]


def quotes_closed(text):
    return quote_mask.quotes_closed(text)

def strip_comments(text):
    if not isinstance(text, str):
        return ""
    masked = mask_quotes(text)
    res = []
    i = 0
    n = len(text)
    while i < n:
        if masked[i] == "#" and (i == 0 or masked[i-1] in (" ", "\t", "\n", ";", "|", "&", "(")):
            k = masked.find("\n", i)
            if k == -1:
                k = n
            while res and res[-1] in (" ", "\t"):
                res.pop()
            i = k
        else:
            res.append(text[i])
            i += 1
    return ''.join(res)

def extract_heredocs(text):
    if not isinstance(text, str):
        return ("", [])
    out = []
    bodies = []
    pending = []
    line_start = 0
    i = 0
    n = len(text)
    state = 0  # 0 OUTSIDE, 1 SIMPLE, 2 DOUBLE

    while i < n:
        c = text[i]
        if state == 1:  # SIMPLE
            out.append(c)
            if c == "'":
                state = 0
            elif c == "\n":
                line_start = i + 1
            i += 1
        elif state == 2:  # DOUBLE
            # a "<<EOF" quoted inside $( ), ${ } or backticks opened in double quotes is not a heredoc.
            if text[i:i+2] in ("$(", "${") or c == "`":
                e = quote_mask.region_end(text, i + (1 if c == "`" else 2), "tick" if c == "`" else ("paren" if text[i+1] == "(" else "brace"))
                e = n if e == -1 else e
                out.append(text[i:e])
                if "\n" in text[i:e]:
                    line_start = text.rfind("\n", i, e) + 1
                i = e
            elif c == '\\' and i + 1 < n:
                out.append(text[i:i+2])
                if text[i+1] == "\n":
                    line_start = i + 2
                i += 2
            else:
                out.append(c)
                if c == '"':
                    state = 0
                elif c == "\n":
                    line_start = i + 1
                i += 1
        else:  # OUTSIDE
            # a. backslash
            if c == '\\' and i + 1 < n:
                out.append(text[i:i+2])
                i += 2
            # a comment is never a heredoc operator (ls # <<EOF hid the next lines).
            elif c == "#" and (i == 0 or text[i-1] in " \t\n;|&("):
                e = text.find("\n", i)
                e = n if e == -1 else e
                out.append(text[i:e])
                i = e
            # b. quotes
            elif c == "'":
                out.append(c)
                state = 1
                i += 1
            elif c == '"':
                out.append(c)
                state = 2
                i += 1
            # c. heredoc detection
            elif text[i:i+2] == "<<" and text[i+2:i+3] != "<" and (i == 0 or text[i-1] != "<"):
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
                    q += 1
                m = re.match(r"[A-Za-z_][A-Za-z0-9_]*", text[q:])
                if not m:
                    out.append("<<")
                    i += 2
                else:
                    end = q + len(m.group(0)) + (1 if quoted else 0)
                    pending.append((m.group(0), dash))
                    out.append(text[i:end])
                    i = end
            # d. newline with pending
            elif c == "\n" and pending:
                line = text[line_start:i]
                j = i + 1
                for delim, dash in pending:
                    body_lines = []
                    while j < n:
                        e = text.find("\n", j)
                        if e == -1:
                            e = n
                        l = text[j:e]
                        j = e + 1
                        cmp = l.lstrip("\t") if dash else l
                        if cmp == delim:
                            break
                        else:
                            body_lines.append(cmp)
                    bodies.append({"delimiter": delim, "body": "\n".join(body_lines), "line": line})
                pending = []
                if j < n:
                    out.append("\n")
                i = j
                line_start = j
            # e. newline without pending
            elif c == "\n":
                out.append(c)
                line_start = i + 1
                i += 1
            # f. other
            else:
                out.append(c)
                i += 1

    # End of text, pending not closed
    for delim, dash in pending:
        bodies.append({"delimiter": delim, "body": "", "line": text[line_start:]})

    return "".join(out), bodies

NOTICE = """NAME      shell_quotes.py - masks quoted text, strips comments and lifts heredoc bodies out of a shell command, so that only real shell syntax is judged.
READS     nothing: pure module; it works on the command text it is given.
WRITES    nothing: every function returns a new string, a boolean or a list.
EXAMPLE   python3 shell_quotes.py --notice
PITFALLS  2026-09-25 a Python heredoc whose body held '<path>' was refused as a write: a heredoc body is data, not shell.
          2026-09-25 a trailing comment naming the delegation tool exempted a real write: a comment is never shell."""

usage_str = "usage: shell_quotes.py --notice | --autotest"

def run_autotest():
    all_pass = True
    lines = []

    # Test 1
    try:
        obtained1 = (
            mask_quotes('echo "a;b" \'c|d\' e'),
            mask_quotes('say "x\\"y" z'),
            mask_quotes("a 'b\nc' d"),
            mask_quotes(5),
            quotes_closed("echo 'abc"),
            quotes_closed('echo "a" \'b\''),
            quotes_closed("it\\'s"),
            quotes_closed(None)
        )
        expected1 = (
            'echo "   " \'   \' e',
            'say "    " z',
            "a '   ' d",
            "",
            False,
            True,
            True,
            False
        )
        ok = obtained1 == expected1
        if not ok: all_pass = False
        lines.append(f"{'PASS' if ok else 'FAIL'} 1 - expected: {expected1!r}, got: {obtained1!r}")
    except Exception as e:
        all_pass = False
        lines.append(f"FAIL 1 - exception: {e!r}")

    # Test 2
    try:
        obtained2 = (
            strip_comments("tee /tmp/x.py # delegate-tool.py"),
            strip_comments("echo '#not' x"),
            strip_comments("find . -name a#b"),
            strip_comments("# whole line"),
            strip_comments("ls;# c"),
            strip_comments("echo ${#arr}"),
            strip_comments(P1),
            strip_comments("a # x\nb # y"),
            strip_comments(None)
        )
        expected2 = (
            "tee /tmp/x.py",
            "echo '#not' x",
            "find . -name a#b",
            "",
            "ls;",
            "echo ${#arr}",
            'python3 -c "\n# not a comment\n"',
            "a\nb",
            ""
        )
        ok = obtained2 == expected2
        if not ok: all_pass = False
        lines.append(f"{'PASS' if ok else 'FAIL'} 2 - expected: {expected2!r}, got: {obtained2!r}")
    except Exception as e:
        all_pass = False
        lines.append(f"FAIL 2 - exception: {e!r}")

    # Test 3
    try:
        obtained3 = (
            extract_heredocs(H1),
            extract_heredocs(H2)
        )
        expected3 = (
            ("python3 - <<'EOF'\nls", [{"delimiter": "EOF", "body": "print('<path>')", "line": "python3 - <<'EOF'"}]),
            ("cat <<-END > out.py\necho done", [{"delimiter": "END", "body": "x = 1", "line": "cat <<-END > out.py"}])
        )
        ok = obtained3 == expected3
        if not ok: all_pass = False
        lines.append(f"{'PASS' if ok else 'FAIL'} 3 - expected: {expected3!r}, got: {obtained3!r}")
    except Exception as e:
        all_pass = False
        lines.append(f"FAIL 3 - exception: {e!r}")

    # Test 4
    try:
        obtained4 = (
            extract_heredocs(H3),
            extract_heredocs(H4),
            extract_heredocs(H5),
            extract_heredocs(None),
            extract_heredocs(M1),
            extract_heredocs(M2)
        )
        expected4 = (
            ("cat <<A <<B", [{"delimiter": "A", "body": "a1", "line": "cat <<A <<B"}, {"delimiter": "B", "body": "b1\nb2", "line": "cat <<A <<B"}]),
            (H4, []),
            ("cat <<EOF", [{"delimiter": "EOF", "body": "no end", "line": "cat <<EOF"}]),
            ("", []),
            ("echo 'a\nb' <<EOF", [{"delimiter": "EOF", "body": "body", "line": "b' <<EOF"}]),
            ("cat <<EOF\necho 'x'", [{"delimiter": "EOF", "body": "don't", "line": "cat <<EOF"}])
        )
        ok = obtained4 == expected4
        if not ok: all_pass = False
        lines.append(f"{'PASS' if ok else 'FAIL'} 4 - expected: {expected4!r}, got: {obtained4!r}")
    except Exception as e:
        all_pass = False
        lines.append(f"FAIL 4 - exception: {e!r}")

    # Test 5
    try:
        script = os.path.abspath(__file__)
        # --notice
        proc_notice = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
        # without argument
        proc_noarg = subprocess.run([sys.executable, script], capture_output=True, text=True)
        ok_notice = (proc_notice.returncode == 0) and proc_notice.stdout.startswith("NAME      shell_quotes.py")
        ok_noarg = (proc_noarg.returncode == 2) and (proc_noarg.stdout == usage_str + "\n")
        ok = ok_notice and ok_noarg
        if not ok: all_pass = False
        obtained5 = (proc_notice.returncode, proc_notice.stdout[:50], proc_noarg.returncode, proc_noarg.stdout)
        expected5 = (0, "NAME      shell_quotes.py", 2, usage_str + "\n")
        lines.append(f"{'PASS' if ok else 'FAIL'} 5 - expected: {expected5!r}, got: {obtained5!r}")
    except Exception as e:
        all_pass = False
        lines.append(f"FAIL 5 - exception: {e!r}")

    for line in lines:
        print(line)
    return all_pass

def _cli():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--notice":
            print(NOTICE)
            sys.exit(0)
        elif sys.argv[1] == "--autotest":
            success = run_autotest()
            sys.exit(0 if success else 1)
        else:
            print(usage_str)
            sys.exit(2)
    else:
        print(usage_str)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "shell_quotes", sys.argv[1:])
