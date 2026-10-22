import sys
import os
import re
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_quotes
import subshells

NOTICE = """NAME      shell_split.py - cuts a shell command into the simple commands it will really run, subshells and process substitutions included, and reports what it cannot read.
READS     nothing: pure module; it works on the command text it is given, with shell_quotes.py beside it.
WRITES    nothing: split_command() returns the segments, the heredoc bodies and an error or None.
EXAMPLE   python3 shell_split.py --notice
PITFALLS  2026-09-25 a write hidden in a subshell or behind a comment was never judged: every subshell is cut out and judged on its own.
          An unreadable command is never free: split_command() returns an error, and the caller refuses.
"""

USAGE = "usage: shell_split.py --notice | --autotest\n"

H1 = "python3 - <<'EOF'\nprint('<path>')\nEOF\nls"
DEEP5 = "$($($($($(x)))))"
DEEP6 = "$($($($($($(x))))))"


def extract_subshells(text):
    # a command inside $(( )) was never judged; the quotes inside $( ) follow the shell (subshells.py).
    return subshells.extract_subshells(text)


def clean_segment(seg):
    s = seg.strip()
    while True:
        if s.startswith("("):
            s = s[1:].strip()
        elif s.startswith("{") and (len(s) == 1 or s[1] in (" ", "\t")):
            s = s[1:].strip()
        else:
            break

    while True:
        m = shell_quotes.mask_quotes(s)
        if s.endswith(")") and m.count(")") > m.count("("):
            s = s[:-1].strip()
        elif s == "}" or s.endswith(" }") or s.endswith("\t}"):
            s = s[:-1].strip()
        else:
            break
    return s


def split_segments(text):
    masked = shell_quotes.mask_quotes(text)
    segments = []
    start = 0
    i = 0
    n = len(masked)

    while i < n:
        # An escaped character is never a separator (find -exec ... \;)
        if masked[i] == "\\":
            i += 2
            continue
        # Two-character separators first
        if i + 1 < n and masked[i:i + 2] in ("||", "&&"):
            seg = text[start:i]
            cleaned = clean_segment(seg)
            if cleaned:
                segments.append(cleaned)
            start = i + 2
            i += 2
            continue

        # Single-character separators
        c = masked[i]
        if (c in (";", "\n") or (c == "|" and (i == 0 or masked[i - 1] != ">"))) or (  # >| is a redirection
                c == "&" and
                (i == 0 or masked[i - 1] not in ("<", ">")) and
                (i + 1 >= n or masked[i + 1] != ">")
        ):
            seg = text[start:i]
            cleaned = clean_segment(seg)
            if cleaned:
                segments.append(cleaned)
            start = i + 1
            i += 1
            continue

        i += 1

    # Last segment
    seg = text[start:]
    cleaned = clean_segment(seg)
    if cleaned:
        segments.append(cleaned)

    return segments


def split_command(text, max_depth=5):
    if not isinstance(text, str):
        return {"segments": [], "bodies": [], "error": "not a string"}

    segs = []
    bodies = []

    def _split(t, depth):
        if depth > max_depth:
            raise ValueError("nesting deeper than " + str(max_depth))

        rest, b = shell_quotes.extract_heredocs(t)
        bodies.extend(b)

        rest = shell_quotes.strip_comments(rest)

        if not shell_quotes.quotes_closed(rest):
            raise ValueError("unterminated quote")

        outer, inners = extract_subshells(rest)
        segs.extend(split_segments(outer))

        for inner in inners:
            _split(inner, depth + 1)

    try:
        _split(text, 0)
        return {"segments": segs, "bodies": bodies, "error": None}
    except ValueError as e:
        return {"segments": segs, "bodies": bodies, "error": str(e)}


# ----------------------------------------------------------------------
# Autotest
# ----------------------------------------------------------------------

def test1():
    res = extract_subshells("echo $(cat > a.py) done")
    assert isinstance(res, tuple) and len(res) == 2, f"Expected tuple of 2, got {type(res)}"
    assert res == ("echo __SUB__ done", ["cat > a.py"]), f"Expected ('echo __SUB__ done', ['cat > a.py']), got {res}"

    res = extract_subshells("x=`tee b.py`; ls")
    assert res == ("x=__SUB__; ls", ["tee b.py"]), f"Expected ('x=__SUB__; ls', ['tee b.py']), got {res}"

    res = extract_subshells("echo '$(not)' ok")
    assert res == ("echo '$(not)' ok", []), f"Expected ('echo '$(not)' ok', []), got {res}"

    res = extract_subshells('echo "$(tee a.py)"')
    assert res == ('echo "__SUB__"', ["tee a.py"]), f"Expected ('echo \"__SUB__\"', ['tee a.py']), got {res}"

    res = extract_subshells("echo $(a $(b) c)")
    assert res == ("echo __SUB__", ["a $(b) c"]), f"Expected ('echo __SUB__', ['a $(b) c']), got {res}"


def test2():
    res = extract_subshells("echo $((1+2)) x")
    assert res == ("echo __SUB__ x", ["(1+2)"]), f"Expected ('echo __SUB__ x', ['(1+2)']), got {res}"

    res = extract_subshells("diff <(ls a) b")
    assert res == ("diff __SUB__ b", ["ls a"]), f"Expected ('diff __SUB__ b', ['ls a']), got {res}"

    res = extract_subshells('echo $(printf ")") z')
    assert res == ("echo __SUB__ z", ['printf ")"']), f"Expected ('echo __SUB__ z', ['printf \")\"']), got {res}"

    res = extract_subshells(None)
    assert res == ("", []), "Expected ('', []) for None"

    try:
        extract_subshells("echo $(a")
        raise AssertionError("Expected ValueError for unbalanced subshell")
    except ValueError as e:
        assert str(e) == "unbalanced subshell", f"Expected 'unbalanced subshell', got {str(e)}"

    try:
        extract_subshells("echo `a")
        raise AssertionError("Expected ValueError for unbalanced subshell")
    except ValueError as e:
        assert str(e) == "unbalanced subshell", f"Expected 'unbalanced subshell', got {str(e)}"


def test3():
    res = split_segments("cat f; ls | grep x && echo ok 2>&1 &\nrm g")
    expected = ["cat f", "ls", "grep x", "echo ok 2>&1", "rm g"]
    assert res == expected, f"Expected {expected}, got {res}"

    res = split_segments('echo "a;b" && x &>/dev/null')
    expected = ['echo "a;b"', "x &>/dev/null"]
    assert res == expected, f"Expected {expected}, got {res}"

    res = split_segments("(cd d && tee a.py) ; { echo x; }")
    expected = ["cd d", "tee a.py", "echo x"]
    assert res == expected, f"Expected {expected}, got {res}"

    assert clean_segment("echo {a,b}") == "echo {a,b}", f"Expected 'echo {{a,b}}' unchanged, got {clean_segment('echo {a,b}')}"

    assert clean_segment('echo ")"') == 'echo ")"', f"Expected 'echo \")\"' unchanged, got {clean_segment('echo \")')}"

    assert clean_segment("}") == "", "Expected empty string for '}'"


def test4():
    expected = {"segments": ["echo __SUB__", "tee /tmp/x.py", "a __SUB__ c", "b"],
                "bodies": [], "error": None}
    res = split_command("echo $(a $(b) c); tee /tmp/x.py # delegate-tool.py")
    assert isinstance(res, dict), f"Expected dict, got {type(res)}"
    assert res == expected, f"Expected {expected}, got {res}"

    expected_H1 = {
        "segments": ["python3 - <<'EOF'", "ls"],
        "bodies": [{"delimiter": "EOF", "body": "print('<path>')", "line": "python3 - <<'EOF'"}],
        "error": None
    }
    res = split_command(H1)
    assert res == expected_H1, f"Expected {expected_H1}, got {res}"

    res = split_command("ls # it's fine")
    assert res == {"segments": ["ls"], "bodies": [], "error": None}, f"Expected segments ['ls'], no error, got {res}"

    res = split_command('python3 -c "\nimport x\n" && ls')
    expected_segments = ['python3 -c "\nimport x\n"', "ls"]
    assert res["segments"] == expected_segments, f"Expected segments {expected_segments}, got {res['segments']}"


def test5():
    res = split_command("echo 'abc")
    assert res["error"] == "unterminated quote", f"Expected error 'unterminated quote', got {res['error']}"

    res = split_command("echo $(a")
    assert res["error"] == "unbalanced subshell", f"Expected error 'unbalanced subshell', got {res['error']}"

    res = split_command(DEEP6)
    assert res["error"] == "nesting deeper than 5", f"Expected error 'nesting deeper than 5', got {res['error']}"

    res = split_command(DEEP5)
    assert res["error"] is None, f"Expected no error for DEEP5, got {res['error']}"
    expected_segments = ["__SUB__", "__SUB__", "__SUB__", "__SUB__", "__SUB__", "x"]
    assert res["segments"] == expected_segments, f"Expected segments {expected_segments}, got {res['segments']}"

    res = split_command(42)
    assert res == {"segments": [], "bodies": [], "error": "not a string"}, \
        f"Expected 'not a string' dict, got {res}"

    # Subprocess tests
    script = os.path.abspath(__file__)

    p = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    assert p.returncode == 0, f"Expected return code 0 for --notice, got {p.returncode}"
    assert p.stdout.startswith("NAME      shell_split.py"), \
        f"stdout does not start with NAME, got: {p.stdout[:50]!r}"

    p = subprocess.run([sys.executable, script], capture_output=True, text=True)
    assert p.returncode == 2, f"Expected return code 2 for no args, got {p.returncode}"
    assert p.stdout == USAGE, f"Expected usage line, got: {p.stdout!r}"


def autotest():
    tests = [
        ("1", test1),
        ("2", test2),
        ("3", test3),
        ("4", test4),
        ("5", test5),
    ]
    all_pass = True
    for name, func in tests:
        try:
            func()
            print(f"PASS: test {name}")
        except AssertionError as e:
            print(f"FAIL: test {name} - {e}")
            all_pass = False
        except Exception as e:
            print(f"FAIL: test {name} - unexpected {type(e).__name__}: {e}")
            all_pass = False
    return all_pass


def _cli():
    if len(sys.argv) == 1:
        sys.stdout.write(USAGE)
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        success = autotest()
        sys.exit(0 if success else 1)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "shell_split", sys.argv[1:])
