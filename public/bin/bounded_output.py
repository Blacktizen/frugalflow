"""bounded_output.py - tells whether a shell command can only print a short output."""

import os
import re
import shlex
import subprocess
import sys

MAX_LINES = 50
MAX_BYTES = 5000
SHELL_NAMES = {"sh", "bash", "zsh", "dash", "ksh", "fish", "source", ".", "eval", "exec", "xargs", "parallel", "env", "sudo", "nohup", "time", "ssh"}
RANKERS = {"sort", "uniq", "awk", "gawk", "mawk", "nawk"}
GREP_NAMES = {"grep", "egrep", "fgrep"}
GREP_VALUE_OPTIONS = {"-e", "-f", "-m", "-A", "-B", "-C", "--regexp", "--file"}
SAFE_NAMES = {"grep", "egrep", "fgrep", "sort", "uniq", "cut", "tr", "cat", "head", "tail", "wc", "ls", "jq", "git", "echo", "printf", "awk", "gawk", "mawk", "nawk"}
BANNED_PARTS = ("/dev/", "stderr", "debug", "compress-program", "getline", "system", "@include")
AWK_NAMES = {"awk", "gawk", "mawk", "nawk"}


def mask_line(line):
    """Mask characters between quotes; return (mask, closed)."""
    mask = list(line)
    state = None
    i = 0
    n = len(line)
    while i < n:
        ch = line[i]
        if state == "'":
            if ch == "'":
                state = None
            else:
                mask[i] = ' '
            i += 1
        elif state == '"':
            if ch == '\\':
                mask[i] = ' '
                if i + 1 < n:
                    mask[i + 1] = ' '
                    i += 2
                else:
                    i += 1
            elif ch == '"':
                state = None
                i += 1
            else:
                mask[i] = ' '
                i += 1
        else:
            if ch == "'":
                state = "'"
            elif ch == '"':
                state = '"'
            i += 1
    closed = (state is None)
    return ''.join(mask), closed


def strip_heredocs(command):
    """Remove heredoc bodies; return text or None on doubt."""
    lines = command.split("\n")
    kept = []
    i = 0
    n = len(lines)
    while i < n:
        L = lines[i]
        mask, closed = mask_line(L)
        if not closed:
            return None
        delims = []
        p = 0
        while p < len(mask) - 1:
            if mask[p:p + 2] == "<<" and mask[p:p + 3] != "<<<" and (p == 0 or mask[p - 1] != "<"):
                m = re.match(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][A-Za-z0-9_]*)\2", L[p:])
                if m is None:
                    return None
                delims.append(m.group(3))
                p += 2
            else:
                p += 1
        if delims:
            words = re.findall(r"[^\s|&;<>()]+", mask)
            for w in words:
                b = os.path.basename(w)
                if b in SHELL_NAMES or b in RANKERS:
                    return None
            kept.append(L)
            for delim in delims:
                i += 1
                found = False
                while i < n:
                    if lines[i].strip() == delim:
                        found = True
                        i += 1
                        break
                    i += 1
                if not found:
                    return None
        else:
            kept.append(L)
            i += 1
    return "\n".join(kept)


def bounding(cmd):
    """Return True if cmd bounds its output (head, tail, wc, grep -c)."""
    if not cmd:
        return False
    name = os.path.basename(cmd[0])
    rest = cmd[1:]

    if name in ("head", "tail"):
        lines_val = None
        bytes_val = None
        j = 0
        while j < len(rest):
            t = rest[j]
            if t in ("-n", "-c"):
                if j + 1 >= len(rest):
                    return False
                val_str = rest[j + 1]
                if not re.fullmatch(r"\d+", val_str):
                    return False
                val = int(val_str)
                if t == "-n":
                    lines_val = val if lines_val is None else max(lines_val, val)
                else:
                    bytes_val = val if bytes_val is None else max(bytes_val, val)
                j += 2
            else:
                m = re.fullmatch(r"-([nc])(\d+)", t)
                if m:
                    kind = m.group(1)
                    val = int(m.group(2))
                    if kind == "n":
                        lines_val = val if lines_val is None else max(lines_val, val)
                    else:
                        bytes_val = val if bytes_val is None else max(bytes_val, val)
                    j += 1
                    continue
                m = re.fullmatch(r"-(\d+)", t)
                if m:
                    val = int(m.group(1))
                    lines_val = val if lines_val is None else max(lines_val, val)
                    j += 1
                    continue
                if t == "-q":
                    j += 1
                    continue
                return False
        if lines_val is not None and lines_val > MAX_LINES:
            return False
        if bytes_val is not None and bytes_val > MAX_BYTES:
            return False
        return True

    if name == "wc":
        for t in rest:
            if not re.fullmatch(r"-[lcwmL]+", t):
                return False
        return True

    if name in GREP_NAMES:
        j = 0
        while j < len(rest):
            t = rest[j]
            if t == "--":
                break
            if t in GREP_VALUE_OPTIONS:
                j += 2
                continue
            if re.fullmatch(r"-[A-Za-z]*[cq][A-Za-z]*", t) or t in ("--count", "--quiet", "--silent"):
                return True
            j += 1
        return False

    return False


def ranks(cmd):
    """Return True if cmd ranks (sorts, counts, or extracts via grep -o)."""
    for t in cmd:
        if os.path.basename(t) in RANKERS:
            return True
    has_grep = False
    has_o = False
    for t in cmd:
        if os.path.basename(t) in GREP_NAMES:
            has_grep = True
        if re.fullmatch(r"-[A-Za-z]*o[A-Za-z]*", t) or t == "--only-matching":
            has_o = True
    return has_grep and has_o


def safe_stage(cmd):
    """Return True if cmd is a safe stage (known command, no side effects)."""
    if not cmd:
        return False
    name = os.path.basename(cmd[0])
    if name not in SAFE_NAMES:
        return False

    for t in cmd:
        if t != "/dev/null":
            tl = t.lower()
            for p in BANNED_PARTS:
                if p in tl:
                    return False

    for j, t in enumerate(cmd):
        if t and all(c in "<>&" for c in t) and ">" in t:
            if "&" in t:
                if not (t == ">&" and j >= 1 and cmd[j - 1] == "2" and j + 1 < len(cmd) and cmd[j + 1] == "1"):
                    return False

    if name in AWK_NAMES:
        for t in cmd:
            if t.startswith("-f") or t == "--file" or ">" in t or "|" in t:
                return False

    return True


def closing_paren(text, k):
    """Return index of the closing paren matching the one at k-1, or -1."""
    depth = 1
    state = None
    i = k
    n = len(text)
    while i < n:
        ch = text[i]
        if state == "'":
            if ch == "'":
                state = None
            i += 1
        else:
            if ch == '\\':
                i += 2
                continue
            if state == '"':
                if ch == '"':
                    state = None
                i += 1
            else:
                if ch == "'":
                    state = "'"
                elif ch == '"':
                    state = '"'
                elif ch == '(':
                    depth += 1
                elif ch == ')':
                    depth -= 1
                    if depth == 0:
                        return i
                i += 1
    return -1


def extract(text):
    """Extract $(...) substitutions; return (outer, inners) or None."""
    inners = []
    outer = []
    state = None
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if state == "'":
            outer.append(ch)
            if ch == "'":
                state = None
            i += 1
        elif ch == '\\':
            outer.append(ch)
            if i + 1 < n:
                outer.append(text[i + 1])
                i += 2
            else:
                i += 1
        elif ch == '`':
            return None
        elif text[i:i + 3] == "$((":
            return None
        elif text[i:i + 2] == "$(":
            j = closing_paren(text, i + 2)
            if j == -1:
                return None
            inner = text[i + 2:j]
            result = extract(inner)
            if result is None:
                return None
            inners.append(inner)
            outer.append("SUBST")
            i = j + 1
        elif state is None and ch in "()":
            return None
        else:
            if ch == '"':
                if state is None:
                    state = '"'
                else:
                    state = None
            elif ch == "'" and state is None:
                state = "'"
            outer.append(ch)
            i += 1
    if state is not None:
        return None
    return "".join(outer), inners


def bounded(command):
    """Return True if the shell command can only produce short output."""
    if not isinstance(command, str):
        return False
    try:
        text = strip_heredocs(command)
        if text is None:
            return False
        r = extract(text)
        if r is None:
            return False
        outer, inners = r
        for inner in inners:
            if not bounded(inner):
                return False
        text = outer

        lex = shlex.shlex(text, posix=True, punctuation_chars="();<>|&\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        lex.commenters = ""
        tokens = list(lex)

        pipelines = []
        current_pipeline = []
        current_cmd = []

        for tok in tokens:
            if tok and all(c in ";&|\n" for c in tok):
                stripped = tok.replace("\n", "")
                if stripped in ("|", "|&"):
                    if current_cmd:
                        current_pipeline.append(current_cmd)
                        current_cmd = []
                else:
                    if current_cmd:
                        current_pipeline.append(current_cmd)
                    if current_pipeline:
                        pipelines.append(current_pipeline)
                    current_cmd = []
                    current_pipeline = []
            else:
                current_cmd.append(tok)

        if current_cmd:
            current_pipeline.append(current_cmd)
        if current_pipeline:
            pipelines.append(current_pipeline)

        for pipeline in pipelines:
            if any(ranks(cmd) for cmd in pipeline):
                for cmd in pipeline:
                    if not safe_stage(cmd):
                        return False
                if not bounding(pipeline[-1]):
                    return False

        return True
    except Exception:
        return False


def _notice():
    print("NAME      bounded_output.py - tells whether a shell command can only print a short output: every pipeline that ranks ends with head, tail, wc or grep -c.")
    print("READS     nothing: pure module; it works on the command text it is given.")
    print("WRITES    nothing: bounded() returns True or False; --judge prints BOUNDED or UNBOUNDED.")
    print('EXAMPLE   python3 bounded_output.py --judge "grep -o x a.log | sort | uniq -c | head -20"')
    print("PITFALLS  2026-09-27 the digest check refused a grep -o piped into tail -3, and a here-document whose text only mentioned uniq -c.")
    print("          Here-document text is data and is dropped, unless a shell reads it; any doubt means unbounded.")
    print("          2026-09-27 a first version let sort -rn >&2 | head -3 and tee /dev/stderr through: every stage of a ranking pipeline must be a known command that writes only to its output.")
    print("          2026-09-27 a quoted parenthesis refused grep -o '(a|b)' | tail -4: only unquoted ( and ) are doubts; each $( ... ) is judged on its own.")


def _autotest():
    F1 = "grep -o x a.log | sort | uniq -c | sort -rn | head -20"
    F2 = "grep -o x a.log | sort | uniq -c | sort -rn"
    F3 = "cat <<'EOF'\nsort -rn a.log\nEOF"
    F4 = "bash <<'EOF'\nsort -rn a.log\nEOF"
    F5 = "grep -o x a.log | head -n 999"
    fixtures = [
        (F1, "BOUNDED", 0),
        (F2, "UNBOUNDED", 1),
        (F3, "BOUNDED", 0),
        (F4, "UNBOUNDED", 1),
        (F5, "UNBOUNDED", 1),
    ]
    all_pass = True
    for idx, (fixture, expected_out, expected_code) in enumerate(fixtures, 1):
        proc = subprocess.run(
            [sys.executable, __file__, "--judge", fixture],
            capture_output=True,
            text=True,
        )
        first_line = proc.stdout.strip().split("\n")[0] if proc.stdout.strip() else ""
        got_code = proc.returncode
        passed = (first_line == expected_out and got_code == expected_code)
        if not passed:
            all_pass = False
        status = "PASS" if passed else "FAIL"
        print(f"{status} test {idx}: expected={expected_out}/{expected_code} got={first_line}/{got_code}")
    sys.exit(0 if all_pass else 1)


def main():
    args = sys.argv[1:]
    if len(args) == 1 and args[0] == "--notice":
        _notice()
        sys.exit(0)
    elif len(args) == 1 and args[0] == "--autotest":
        _autotest()
    elif len(args) == 2 and args[0] == "--judge":
        result = bounded(args[1])
        if result:
            print("BOUNDED")
            sys.exit(0)
        else:
            print("UNBOUNDED")
            sys.exit(1)
    else:
        print("usage: bounded_output.py --judge COMMAND | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bounded_output", sys.argv[1:])
