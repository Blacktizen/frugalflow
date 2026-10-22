import os
import re
import shlex
import sys
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

JOURNAL_EXTS = [".jsonl", ".json", ".log"]
TOUCHING_HEADS = {"rm", "unlink", "truncate", "shred", "mv", "ln", "chflags", "chmod", "chown", "rsync", "install"}
FILE_TOOLS = {"Write", "Edit", "MultiEdit", "NotebookEdit"}

# a literal output-file name: a write destination that ends with one of
# these is a data file, not a protected journal, even when the folder is a variable.
OUTPUT_SUFFIXES = (".txt", ".json", ".err", ".out", ".log", ".md", ".init", ".doc", ".np")


def _non_code_suffix(dest):
    """Return True when the text of dest after its last expansion is a literal name
    that ends with an output-file extension; the expansion is the last $NAME, ${NAME},
    $(...) or backquote span. A fully literal or empty suffix never counts."""
    if not isinstance(dest, str):
        return False
    n = len(dest)
    i = 0
    last = -1
    while i < n:
        ch = dest[i]
        if ch == "$":
            if dest.startswith("$(", i):
                depth = 1
                j = i + 2
                while j < n and depth:
                    if dest[j] == "(":
                        depth += 1
                    elif dest[j] == ")":
                        depth -= 1
                    j += 1
                if depth:
                    return False
                i = j
            else:
                m = re.match(r"\$\{[^{}]*\}|\$[A-Za-z_][A-Za-z0-9_]*", dest[i:])
                i += m.end() if m else 1
            last = i
            continue
        if ch == "`":
            j = dest.find("`", i + 1)
            if j == -1:
                return False
            i = j + 1
            last = i
            continue
        i += 1
    if last < 0:
        return False
    base = dest[last:].rsplit("/", 1)[-1]
    ext = os.path.splitext(base)[1]
    if not ext and base.startswith(".") and "." not in base[1:]:
        ext = base
    return ext in OUTPUT_SUFFIXES

def protected_paths(home, settings):
    """Return the list of protected paths."""
    paths = []

    def add(p):
        p = os.path.expanduser(p)
        if not os.path.isabs(p):
            p = os.path.join(home, p)
        if p not in paths:
            paths.append(p)

    add("delegations.jsonl")
    add("guard.json")
    add("blocks")

    dl = settings.get("delegation_logs", [])
    if isinstance(dl, str):
        dl = [dl]
    elif not isinstance(dl, (list, tuple)):
        dl = []
    for p in dl:
        add(p)

    audit = settings.get("audit_log", "")
    if isinstance(audit, str) and audit:
        add(audit)

    return paths

def normal(path, cwd):
    """Normalize a path: replace $HOME/ or ${HOME}/, expanduser, make absolute, realpath."""
    if path.startswith("$HOME/"):
        path = "~/" + path[len("$HOME/"):]
    elif path.startswith("${HOME}/"):
        path = "~/" + path[len("${HOME}/"):]
    path = os.path.expanduser(path)
    if not os.path.isabs(path):
        path = os.path.join(cwd, path)
    return os.path.realpath(path)

def is_protected(path, protected, cwd):
    """Return True if path is protected."""
    p = normal(path, cwd)
    for x in protected:
        px = normal(x, cwd)
        if p == px or p.startswith(px + os.sep):
            return True
    return False

WRITE_DEST_HEADS = {"cp", "tee", "ln", "install", "rsync", "mv"}

def _redirection_dests(seg):
    """Return the raw destinations of the > and >> redirections of a segment."""
    import shell_tokens

    toks = shell_tokens.tokenize(seg)
    if not toks:
        return []
    dests = []
    i = 0
    n = len(toks)
    while i < n:
        t = toks[i]
        op = re.sub(r"^\d+", "", t)
        if op in (">", ">>", ">|", "&>", "&>>"):
            if i + 1 < n:
                if op == ">&" and (toks[i + 1].isdigit() or toks[i + 1] == "-"):
                    i += 2
                    continue
                dests.append(toks[i + 1])
                i += 2
                continue
        i += 1
    return dests

REDIR_OP = re.compile(r"(?:\d*)?(?:&>>|&>|>>|>\||>|<<<|<<-|<<|<)(?:&\d+)?")

def _is_redir_op(w):
    """Return True when the word is only a redirection operator (>, >>, >|, <, <<,
    <<- , <<<, &>, &>>, 2>, 2>>, 2>&1, >&2 ...): an operator is never a path."""
    return isinstance(w, str) and REDIR_OP.fullmatch(w) is not None

def _python_inline_codes(seg, bodies):
    """Return (head, args, codes, heredocs) for a segment whose head is a python
    interpreter: codes are its -c arguments and the bodies of the heredocs whose
    line sits in the segment; heredocs are those bodies. A segment that is not a
    python run gives (None, None, [], [])."""
    try:
        words = shlex.split(seg)
    except ValueError:
        words = seg.split()
    i = 0
    while i < len(words) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i]):
        i += 1
    if i >= len(words):
        return None, None, [], []
    head = os.path.basename(words[i])
    if not re.fullmatch(r"python3?(\.\d+)?", head):
        return None, None, [], []
    args = words[i + 1:]
    # A script name or a -m before the first -c: the segment runs a file, and a
    # python segment without inline code is never a reader. Redirection words are
    # skipped: they are judged as redirections, never as arguments of the head.
    k = 0
    while k < len(args):
        a = args[k]
        if _is_redir_op(a):
            k += 2
            continue
        if a.startswith("<") or a.startswith(">"):
            k += 1
            continue
        if a == "-m":
            return None, None, [], []
        if a == "-c":
            break
        if not a.startswith("-"):
            return None, None, [], []
        k += 1
    codes = [args[k + 1] for k, a in enumerate(args) if a == "-c" and k + 1 < len(args)]
    heredocs = [b for b in bodies if b.get("line") and _heredoc_owner(b["line"]) == seg]
    codes += [b.get("body", "") for b in heredocs]
    return head, args, codes, heredocs

def _heredoc_owner(line):
    """Return the segment of a heredoc line that owns the heredoc operator."""
    import shell_split

    local = shell_split.split_segments(line)
    return next((x for x in local if "<<" in x), line)

def _heredoc_is_quoted(b):
    """Return True when the delimiter of a heredoc body is quoted in its line."""
    delim = b.get("delimiter", "")
    line = b.get("line", "")
    if not delim:
        return False
    return re.search(r"<<-?\s*['\"\\]" + re.escape(delim), line) is not None

def _proven_python_reader(seg, bodies):
    """Return True when the segment is a python run that only reads: it carries at
    least one inline code, every inline code is a proven read, and none of its
    unquoted heredocs carries $( or a backquote: the shell would run them before
    any reader. A python segment without inline code (a script, -m) is never a
    reader. In every doubt the answer is False."""
    import python_read_proof

    _head, _args, codes, heredocs = _python_inline_codes(seg, bodies)
    if not codes:
        return False
    if not all(c.strip() and python_read_proof.read_proven(c) for c in codes):
        return False
    for b in heredocs:
        if not _heredoc_is_quoted(b):
            body = b.get("body", "")
            if "$(" in body or "`" in body:
                return False
    return True

def _python_code_texts(command, cfg):
    """Return the inline Python bodies of the command: the heredocs read by a
    Python interpreter and the code of its -c flags."""
    import shell_split
    import shell_targets

    texts = []
    sp = shell_split.split_command(command)
    for b in sp.get("bodies", []):
        line = b.get("line", "")
        segs = shell_split.split_segments(line)
        owner = next((s for s in segs if "<<" in s), line)
        head = shell_targets.judge_segment(owner, cfg).get("head", "")
        if head == "python3":
            texts.append(b.get("body", ""))
    for s in sp.get("segments", []):
        r = shell_targets.judge_segment(s, cfg)
        if r.get("head") == "python3" and r.get("nested") and r["nested"].get("kind") == "code":
            texts.append(r["nested"].get("text", ""))
    return texts

# the guard lists the tools that only read. A simple command that
# contacts a protected zone with a head outside that list is a touch: a whole
# word that is a protected path, a path inside one, or a parent of one; a
# relative word while the current directory sits in the zone or cannot be
# read; a write option or an output redirection into the zone; an inline
# interpreter naming the zone. In every doubt, the contact is a touch.
READER_HEADS = {
    "cat", "head", "tail", "less", "more", "wc", "grep", "egrep", "fgrep", "rg",
    "jq", "ls", "stat", "file", "du", "diff", "cmp", "shasum", "sha256sum", "md5",  # lang-ok
    "md5sum", "readlink", "realpath", "basename", "dirname", "test", "[", "echo",
    "printf",
}
STRUCT_KW = {"for", "while", "until", "select", "case", "fi", "esac", "done", "in", "{", "}"}
STRIP_KW = {"then", "else", "elif", "do", "if", "time"}

def _expand_tilde(p):
    """Expand a leading ~ or $HOME / ${HOME} of a path."""
    if p.startswith("$HOME/"):
        p = "~/" + p[len("$HOME/"):]
    elif p.startswith("${HOME}/"):
        p = "~/" + p[len("${HOME}/"):]
    return os.path.expanduser(p)

def _brace_expand(w, _cap=16):
    """Expand a brace group of the form {a,b} into its alternatives."""
    i = w.find("{")
    if i < 0:
        return [w]
    j = w.find("}", i)
    if j < 0:
        return [w]
    head_s, mid, tail = w[:i], w[i + 1:j], w[j + 1:]
    out = []
    for a in mid.split(","):
        out.extend(_brace_expand(head_s + a + tail, _cap))
        if len(out) >= _cap:
            return out[:_cap]
    return out

def _pattern_zone(pre, protected, cwd):
    """Return True when a pattern's literal prefix reaches a protected path.

    The prefix is the text before the first pattern character; its directory
    part is normalized before the comparison. A protected path that starts
    with the prefix, or a prefix that starts with a protected path, is a
    contact; a pattern is compared as text, never expanded.
    """
    p = _expand_tilde(pre)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    p = os.path.normpath(p)
    for x in protected:
        px = normal(x, cwd)
        if p == px or px.startswith(p) or p.startswith(px):
            return True
    return False

def _component_in(text, marker):
    """Return True when marker is a whole component of a path in the text:
    bounded by a slash, a quote or a space."""
    pat = "(?:^|[\"' \t/])" + re.escape(marker) + "(?:$|[\"' \t/])"
    return re.search(pat, text) is not None

PERSONAL_SOURCES = ("expanduser", "env" + "iron", "get" + "env", "Path.home", "HOM" + "E", "~")

def _python_home_touch(code, markers):
    """Return True when inline python code builds a protected path from the
    personal folder: a protected name as a whole component next to any source
    of that folder. A body proven read stays free; in every other doubt the
    contact stands."""
    if not code:
        return False
    if not any(_component_in(code, m) for m in markers):
        return False
    return any(h in code for h in PERSONAL_SOURCES)

def _zone_cwd(d, protected, cwd):
    """Return True if directory d is a protected path, sits inside one, or is
    a parent of one located under the home: the home itself counts as a
    parent of the zone, a directory above it does not."""
    try:
        pd = normal(d, cwd)
        pxs = [normal(x, cwd) for x in protected]
        if not pxs:
            return False
        in_zone = any(pd == px or pd.startswith(px + os.sep) for px in pxs)
        if in_zone:
            return True
        if not any(px.startswith(pd + os.sep) for px in pxs):
            return False
        home = os.path.expanduser("~")
        return pd == home or pd.startswith(home + os.sep)
    except Exception:
        return True

def _zone_rel(path, protected, cwd):
    """Return True if path is a protected path, is inside one, or is a parent of one."""
    p = normal(path, cwd)
    for x in protected:
        px = normal(x, cwd)
        if p == px or p.startswith(px + os.sep) or px.startswith(p + os.sep):
            return True
    return False

def _zone_markers(protected):
    """Return the protected names: the fixed zone names and the dotted basenames."""
    markers = [".frugalflow", ".guardian", "blocks"]
    for x in protected:
        b = os.path.basename(x)
        if "." in b and b not in markers:
            markers.append(b)
    return markers

# the shells whose head reads a heredoc body from stdin, and the
# options of python -m json.tool. -mMODULE is -m MODULE everywhere.
SHELL_BODY_HEADS = {"bash", "sh", "zsh", "dash", "ksh", "mksh", "yash", "posh"}
JSON_TOOL_OPTIONS = {"--sort-keys", "--no-ensure-ascii", "--json-lines", "--compact", "--tab", "--no-indent"}

def _target_unreadable(t):
    """Return True when a target text cannot be read: <unknown>, a subshell or an expansion."""
    return t == "<unknown>" or "__SUB__" in t or "$" in t

def _dotted_zone_names(protected):
    """Return the basename of each protected path that carries a dot."""
    return [os.path.basename(x) for x in protected if "." in os.path.basename(x)]

def _named_unreadable_dest(segs, protected):
    """Return True when a redirection destination is unreadable and carries the
    dotted basename of a protected path as a whole component: an unreadable
    target named like a journal is a contact."""
    names = _dotted_zone_names(protected)
    if not names:
        return False
    for s in segs:
        for d in _redirection_dests(s):
            if _target_unreadable(d) and any(_component_in(d, n) for n in names):
                return True
    return False

def _shell_body_reader(seg):
    """Return True when the segment is a shell head reading its body from stdin:
    a head whose basename is a known shell (a path counts: /bin/sh), every other
    word an option starting with - (a lone - included) or exactly /dev/stdin;
    any other argument (a script) makes it a script run, not a body reader."""
    import shell_tokens

    toks = shell_tokens.tokenize(seg)
    if not toks:
        return False
    gone = set()
    for k, t in enumerate(toks):
        if re.match(r"\d*<", t):
            gone.add(k)
            if re.fullmatch(r"\d*<(<-?|<<|&)?", t) and k + 1 < len(toks):
                gone.add(k + 1)
    kept = [t for k, t in enumerate(toks) if k not in gone]
    if not kept:
        return False
    if kept[0].rsplit("/", 1)[-1] not in SHELL_BODY_HEADS:
        return False
    return all(w == "/dev/stdin" or w.startswith("-") for w in kept[1:])

def _shell_read_heredoc(b):
    """Return True when the body of a heredoc is read by a shell: the segment
    owning the operator is a shell body reader, or a cat <<M piped into one."""
    import shell_split
    import shell_tokens

    line = b.get("line", "")
    if not line or "<<" not in line:
        return False
    local = shell_split.split_segments(line)
    idx = next((k for k, x in enumerate(local) if "<<" in x), -1)
    owner = local[idx] if idx >= 0 else line
    if _shell_body_reader(owner):
        return True
    if idx >= 0 and idx + 1 < len(local):
        toks = shell_tokens.tokenize(owner)
        if toks and toks[0].rsplit("/", 1)[-1] == "cat" and _shell_body_reader(local[idx + 1]):
            return True
    return False

def _module_of_python(args):
    """Return (module, the other words) when the python words carry -m, glued
    (-mMODULE) or separate; None when there is no -m. Redirection words are
    skipped: they are judged as redirections, never as arguments."""
    k = 0
    while k < len(args):
        a = args[k]
        if _is_redir_op(a):
            k += 2
            continue
        if a == "-m":
            mod = args[k + 1] if k + 1 < len(args) else ""
            return mod, args[:k] + args[k + 2:]
        if a.startswith("-m") and not a.startswith("--") and len(a) > 2:
            return a[2:], args[:k] + args[k + 1:]
        k += 1
    return None

def _json_tool_positionals(rest):
    """Return the positional words of json.tool; None when an option is unknown."""
    pos = []
    k = 0
    while k < len(rest):
        a = rest[k]
        if a in JSON_TOOL_OPTIONS:
            k += 1
            continue
        if a == "--indent":
            k += 2
            continue
        if a.startswith("--indent="):
            k += 1
            continue
        if a.startswith("-"):
            return None
        pos.append(a)
        k += 1
    return pos

def _json_tool_strict(seg):
    """Return True when the segment is a json.tool run with 0 or 1 positional
    and no output redirection: a strict reader, and only for its own segment."""
    try:
        words = shlex.split(seg)
    except ValueError:
        return False
    i = 0
    while i < len(words) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i]):
        i += 1
    if i >= len(words) or not re.fullmatch(r"python3?(\.\d+)?", os.path.basename(words[i])):
        return False
    ms = _module_of_python(words[i + 1:])
    if ms is None or ms[0] != "json.tool":
        return False
    if _redirection_dests(seg):
        return False
    pos = _json_tool_positionals(ms[1])
    return pos is not None and len(pos) <= 1

def _reaches_zone(p, protected, cwd):
    """Return True when a resolved path is a protected path or sits inside one;
    a parent of the zone alone does not reach it."""
    pp = normal(p, cwd)
    for x in protected:
        px = normal(x, cwd)
        if pp == px or pp.startswith(px + os.sep):
            return True
    return False

def _word_names_zone(w, protected, cwd, markers):
    """Return True when a word of the command names a protected path.

    Judged on the resolved path: a word that carries an unresolved expansion,
    or that climbs above itself with a parent component, names the zone when
    it carries a protected name; a plain word names it only when its resolved
    path is the zone or sits inside it, or the pattern prefix reaches it."""
    if not w or w.startswith("-"):
        return False
    # a word that is only a redirection operator is never a path.
    if _is_redir_op(w):
        return False
    if "$" in w or "__SUB__" in w:
        return any(m in w for m in markers)
    if ".." in w.split("/"):
        return any(m in w for m in markers)
    gpos = next((k for k, ch in enumerate(w) if ch in "*?[{"), None)
    pre = w[:gpos] if gpos is not None else w
    if not pre:
        return False
    try:
        if pre.startswith("~") or os.path.isabs(pre):
            return _reaches_zone(pre, protected, cwd)
        if pre in (".", "..") or pre.startswith(("./", "../")):
            return _reaches_zone(pre, protected, cwd)
        return _reaches_zone(os.path.join(cwd, pre), protected, cwd)
    except Exception:
        return True

def _command_names_zone(segs, bodies, protected, cwd, markers):
    """Return True when the command names a protected path.

    The shell words are judged on their resolved path; a heredoc body read by
    a python interpreter is judged as code: a protected name counts in it as a
    whole component, a body proven read-only stays free."""
    import shell_split
    import shell_targets

    for s in segs:
        try:
            words = shlex.split(s)
        except ValueError:
            words = s.split()
        for w in words:
            if _word_names_zone(w, protected, cwd, markers):
                return True
    import python_read_proof
    for b in bodies:
        line = b.get("line", "")
        if not line:
            continue
        local = shell_split.split_segments(line)
        owner = next((x for x in local if "<<" in x), line)
        try:
            head = shell_targets.judge_segment(owner, {"code_extensions": JOURNAL_EXTS, "delegate_tools": []}).get("head", "")
        except Exception:
            head = ""
        if head == "python3":
            body = b.get("body", "")
            if body and not python_read_proof.read_proven(body):
                if any(_component_in(body, m) for m in markers):
                    return True
    return False

def _in_zone(d, protected, cwd):
    """Return True if the directory d is a protected path or sits inside one."""
    try:
        pd = os.path.realpath(_expand_tilde(d))
        for x in protected:
            px = normal(x, cwd)
            if pd == px or pd.startswith(px + os.sep):
                return True
        return False
    except Exception:
        return True

def _word_class(w, cwd_now, unreadable, protected, cwd, markers):
    """Classify a word of a simple command: none, zone contact, or unknown."""
    if w.startswith("-"):
        return "none"
    # a word that is only a redirection operator is never a path.
    if _is_redir_op(w):
        return "none"
    # an NAME=value assignment is data, not a file contact.
    if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", w):
        return "none"
    if "$" in w or "__SUB__" in w:
        return "unknown"
    gpos = next((k for k, ch in enumerate(w) if ch in "*?[{"), None)
    pre = w[:gpos] if gpos is not None else w
    if gpos is not None:
        # A pattern word is judged on its literal prefix: a brace group is
        # developed into its alternatives first, each judged the same way.
        for alt in _brace_expand(w):
            apos = next((k for k, ch in enumerate(alt) if ch in "*?[{"), None)
            a_pre = alt[:apos] if apos is not None else alt
            if a_pre.startswith("~") or os.path.isabs(a_pre):
                try:
                    if _pattern_zone(a_pre, protected, cwd):
                        return "zone"
                except Exception:
                    return "zone"
    if pre.startswith("~") or os.path.isabs(pre):
        try:
            if _zone_rel(pre, protected, cwd):
                return "zone"
            # a word that climbs above itself with a parent
            # component cannot be proven outside the zone; the earlier
            # verdict stands on the names it carries.
            if ".." in pre.split(os.sep):
                return "zone" if any(m in w for m in markers) else "none"
            return "none"
        except Exception:
            return "zone"
    if pre in (".", "..") or pre.startswith(("./", "../")):
        try:
            return "zone" if _zone_rel(pre, protected, cwd_now) else "none"
        except Exception:
            return "zone"
    if _in_zone(cwd_now, protected, cwd) or unreadable:
        return "zone"
    if gpos is not None and not pre:
        return "none"
    if not any(ch in pre for ch in "/.~"):
        return "none"
    try:
        return "zone" if _zone_rel(pre, protected, cwd_now) else "none"
    except Exception:
        return "zone"

def _dest_zone(d, cwd_now, unreadable, protected, cwd, markers):
    """Return True if a write destination lands on the protected zone."""
    if not d or d.startswith("-"):
        return False
    # a word that is only a redirection operator is never a path.
    if _is_redir_op(d):
        return False
    # a destination with a literal non-code file name is a data write,
    # not a protected touch, even from an unreadable directory.
    if _non_code_suffix(d):
        return False
    # a destination that climbs above itself with a parent
    # component cannot be proven outside the zone; a name it carries is a contact.
    if ".." in d.split("/"):
        if any(m in d for m in markers):
            return True
    gpos = next((k for k, ch in enumerate(d) if ch in "*?[{"), None)
    if gpos is not None:
        pre = d[:gpos]
        if not pre:
            return _in_zone(cwd_now, protected, cwd) or unreadable
        if pre.startswith("~") or os.path.isabs(pre):
            try:
                for alt in _brace_expand(d):
                    apos = next((k for k, ch in enumerate(alt) if ch in "*?[{"), None)
                    a_pre = alt[:apos] if apos is not None else alt
                    if (a_pre.startswith("~") or os.path.isabs(a_pre)) and _pattern_zone(a_pre, protected, cwd):
                        return True
                return _zone_rel(pre, protected, cwd)
            except Exception:
                return True
        d = pre
    if os.path.isabs(d) or d.startswith("~"):
        try:
            return _zone_rel(d, protected, cwd)
        except Exception:
            return True
    if unreadable:
        return True
    try:
        return _zone_rel(d, protected, cwd_now)
    except Exception:
        return True

def _sed_is_reader(args):
    """Return True for a read-only sed: -n, no -i, no w or e command."""
    flags = [a for a in args if a.startswith("-")]
    for a in flags:
        if a == "--in-place" or (a.startswith("-i") and not a.startswith("--")):
            return False
    has_n = any(
        not a.startswith("--") and len(a) > 1 and all(c.isalpha() for c in a[1:]) and "n" in a[1:]
        for a in flags
    )
    if not has_n:
        return False
    parts = []
    for k, a in enumerate(args):
        if a in ("-e", "--expression") and k + 1 < len(args):
            parts.append(args[k + 1])
        elif a.startswith("--expression="):
            parts.append(a.split("=", 1)[1])
        elif a in ("-f", "--file"):
            return False
        elif a.startswith("-f") and len(a) > 2 and not a.startswith("--"):
            return False
    for a in args:
        if not a.startswith("-"):
            parts.append(a)
            break
    script = " ".join(parts)
    if re.search(r"(?:^|;|\n)\s*[wW]\s+\S", script):
        return False
    if re.search(r"(?:^|;|\n)\s*e\s+\S", script):
        return False
    return True

def _awk_is_reader(args):
    """Return True for a read-only awk program: no system, no pipe, no print > file."""
    for a in args:
        if a == "-f" or (a.startswith("-f") and len(a) > 2 and not a.startswith("--")):
            return False
    parts = [a for a in args if not a.startswith("-")]
    if not parts:
        return True
    prog = parts[0]
    if "system" in prog:
        return False
    if "|" in prog:
        return False
    if re.search(r"(?:print|printf)\b[^;\n]*>\s*\S", prog):
        return False
    return True

def _sed_script(args):
    """Return the text of the sed script, empty when it cannot be read."""
    parts = []
    for k, a in enumerate(args):
        if a in ("-e", "--expression") and k + 1 < len(args):
            parts.append(args[k + 1])
        elif a.startswith("--expression="):
            parts.append(a.split("=", 1)[1])
    for a in args:
        if not a.startswith("-"):
            parts.append(a)
            break
    return " ".join(parts)

def _find_is_reader(args):
    """Return True for a read-only find: no -delete, -fprint, and every -exec,
    -execdir or -ok action is itself a reader."""
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if a in ("-delete", "-fprint", "-fprintf") or a.startswith(("-fprint", "-fprintf")):
            return False
        if a in ("-exec", "-execdir", "-ok", "-okdir"):
            j = i + 1
            action = []
            while j < n and args[j] not in ("\\;", ";", "+"):
                action.append(args[j])
                j += 1
            if j >= n or not action:
                return False
            if not _strict_reader(os.path.basename(action[0]), action[1:]):
                return False
            i = j
        i += 1
    return True

def _strict_reader(head, args):
    """Return True when the head is a plain reader, or a reader with read-only options."""
    if head in READER_HEADS:
        return True
    if head == "sed":
        return _sed_is_reader(args)
    if head == "awk":
        return _awk_is_reader(args)
    if head == "find":
        return _find_is_reader(args)
    return False

def _interp_touches(code, cwd_now, unreadable, protected, cwd, markers):
    """Return True when an inline interpreter code names the zone.

    A token nobody can read (an unresolved expansion) counts only when the
    command also names the zone; the zone itself is a contact on its own."""
    if not code:
        return False
    # A protected name counts only as a whole path component of the code:
    # bounded by a slash, a quote or a space; in every other doubt the
    # earlier verdict stands.
    if any(_component_in(code, m) for m in markers):
        return True
    for tok in code.split():
        if _word_class(tok, cwd_now, unreadable, protected, cwd, markers) == "zone":
            return True
    return False

def _whitelist_touches(command, sp, protected, cwd):
    """Return the protected paths touched by a contact whose head is not a reader."""
    segs = sp.get("segments", [])
    bodies = sp.get("bodies", [])
    markers = _zone_markers(protected)
    # the command names a protected path only through a word whose
    # resolved path reaches it, or a name carried by an unresolved word; a
    # word that resolves entirely outside the zone and its parents is data.
    has_marker = _command_names_zone(segs, bodies, protected, cwd, markers)

    out = []
    cwd_now = cwd
    unreadable = False
    moved = False
    prev_contact = False
    for s in segs:
        try:
            words = shlex.split(s)
        except ValueError:
            words = s.split()
        if not words:
            prev_contact = False
            continue
        i = 0
        while i < len(words) and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i]):
            i += 1
        if i >= len(words):
            prev_contact = False
            continue
        # env and its flags and VAR= assignments are a prefix: the
        # command head is the first word after them.
        if words[i] == "env":
            i += 1
            while i < len(words) and (
                    words[i].startswith("-")
                    or re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*=.*", words[i])):
                i += 1
            if i >= len(words):
                prev_contact = False
                continue
        if words[i] in STRUCT_KW:
            prev_contact = False
            continue
        while words[i] in STRIP_KW:
            i += 1
        if i >= len(words):
            prev_contact = False
            continue
        head = os.path.basename(words[i])
        args = words[i + 1:]

        if head in ("cd", "pushd"):
            if head == "pushd" and (len(args) < 1 or args[0] == "-" or args[0].startswith("+")):
                unreadable = True
                moved = True
                prev_contact = False
                continue
            if args and not args[0].startswith("-"):
                dest = args[0]
                if any(ch in dest for ch in "$`*?{(") or "__SUB__" in dest:
                    unreadable = True
                else:
                    unreadable = False
                    if os.path.isabs(dest) or dest.startswith("~"):
                        cwd_now = _expand_tilde(dest)
                    else:
                        cwd_now = os.path.join(cwd_now, dest)
            else:
                unreadable = True
            moved = True
            prev_contact = False
            continue
        if head == "popd":
            unreadable = True
            moved = True
            prev_contact = False
            continue

        # The head is the command itself: it is not a path argument.
        zone_word = None
        dollar = False
        for w in words[i + 1:]:
            c = _word_class(w, cwd_now, unreadable, protected, cwd, markers)
            if c == "unknown":
                dollar = True
            elif c == "zone" and zone_word is None:
                zone_word = w
        head_dollar = "$" in words[i]
        if head_dollar:
            dollar = True

        if head in ("cp", "rsync"):
            # free only when the zone is the source and the destination stays out
            if zone_word is not None or dollar:
                nonopt = [a for a in args if not a.startswith("-")]
                t_dirs = []
                for k, a in enumerate(args):
                    if (a == "-t" or a == "--target-directory") and k + 1 < len(args) and not args[k + 1].startswith("-"):
                        t_dirs.append(args[k + 1])
                    elif a.startswith("-t") and len(a) > 2 and not a.startswith("--"):
                        t_dirs.append(a[2:])
                    elif a.startswith("--target-directory="):
                        t_dirs.append(a.split("=", 1)[1])
                dests = t_dirs if t_dirs else ([nonopt[-1]] if nonopt else [])
                for d in dests:
                    if _dest_zone(d, cwd_now, unreadable, protected, cwd, markers):
                        if d not in out:
                            out.append(d)
                        break
        elif head == "xargs":
            # xargs runs its arguments: judge the command it feeds, on the piped contact
            eff = next((a for a in args if not a.startswith("-")), "")
            if not _strict_reader(os.path.basename(eff), []) and (zone_word is not None or dollar or prev_contact):
                v = zone_word if zone_word is not None else "<unknown>"
                if v not in out:
                    out.append(v)
        elif re.fullmatch(r"python3?(\.\d+)?", head):
            dashc = [args[k + 1] for k, a in enumerate(args) if a == "-c" and k + 1 < len(args)]
            heredocs = [b.get("body", "") for b in bodies if b.get("line") and b["line"] in s]
            import python_read_proof
            unproven_c = [c for c in dashc if c.strip() and not python_read_proof.read_proven(c)]
            unproven_h = [c for c in heredocs if c.strip() and not python_read_proof.read_proven(c)]
            if unproven_c and (zone_word is not None or has_marker):
                v = zone_word if zone_word is not None else "<unknown>"
                if v not in out:
                    out.append(v)
            elif unproven_h and (zone_word is not None or (dollar and has_marker)):
                v = zone_word if zone_word is not None else "<unknown>"
                if v not in out:
                    out.append(v)
        elif head in ("sh", "bash", "zsh") and "-c" in args:
            k = args.index("-c")
            code = args[k + 1] if k + 1 < len(args) else ""
            if _interp_touches(code, cwd_now, unreadable, protected, cwd, markers):
                v = zone_word if zone_word is not None else "<unknown>"
                if v not in out:
                    out.append(v)
        elif head in ("perl", "node", "ruby", "osascript") and "-e" in args:
            k = args.index("-e")
            code = args[k + 1] if k + 1 < len(args) else ""
            if _interp_touches(code, cwd_now, unreadable, protected, cwd, markers):
                v = zone_word if zone_word is not None else "<unknown>"
                if v not in out:
                    out.append(v)
        else:
            if zone_word is not None and not _strict_reader(head, args):
                if zone_word not in out:
                    out.append(zone_word)
            if head == "awk":
                prog = next((a for a in args if not a.startswith("-")), "")
                if not _awk_is_reader(args) and _interp_touches(prog, cwd_now, unreadable, protected, cwd, markers):
                    v = zone_word if zone_word is not None else "<unknown>"
                    if v not in out:
                        out.append(v)
            if head == "sed":
                if not _sed_is_reader(args) and _interp_touches(_sed_script(args), cwd_now, unreadable, protected, cwd, markers):
                    v = zone_word if zone_word is not None else "<unknown>"
                    if v not in out:
                        out.append(v)
            if dollar and not _strict_reader(head, args) and has_marker:
                if "<unknown>" not in out:
                    out.append("<unknown>")

        for d in _redirection_dests(s):
            if _dest_zone(d, cwd_now, unreadable, protected, cwd, markers):
                if d not in out:
                    out.append(d)
        # A program started with the working directory inside the protected
        # zone, or on a parent of it, can write into the zone without naming
        # any path; only a reader head stays free.
        if moved and zone_word is None:
            if head_dollar and not unreadable:
                # a head the guard cannot resolve, launched from a
                # folder of the zone, is a contact like any head that is not a
                # strict reader.
                try:
                    if _zone_cwd(cwd_now, protected, cwd):
                        v = normal(cwd_now, cwd)
                        if v not in out:
                            out.append(v)
                except Exception:
                    if "<unknown>" not in out:
                        out.append("<unknown>")
            elif not dollar:
                if unreadable:
                    # from an unreadable directory, the earlier verdict
                    # stands only when the command names the zone; a reader that
                    # names nothing stays free.
                    if has_marker:
                        if "<unknown>" not in out:
                            out.append("<unknown>")
                else:
                    try:
                        # a python segment whose every inline code is
                        # a proven read is a strict reader here.
                        # so is a json.tool run with 0 or 1 positional
                        # and no redirection; it frees only its own segment.
                        if _zone_cwd(cwd_now, protected, cwd) and not _strict_reader(head, args) \
                                and not _proven_python_reader(s, bodies) \
                                and not _json_tool_strict(s):
                            v = normal(cwd_now, cwd)
                            if v not in out:
                                out.append(v)
                    except Exception:
                        if "<unknown>" not in out:
                            out.append("<unknown>")
        prev_contact = zone_word is not None or dollar
    # a heredoc body read by an interpreter that is not a shell is
    # not cut into shell commands; node, perl and ruby keep exactly the verdict
    # their inline code already has: a protected name in it is a contact.
    import shell_split
    import shell_targets

    for b in bodies:
        line = b.get("line", "")
        if not line:
            continue
        local = shell_split.split_segments(line)
        owner = next((x for x in local if "<<" in x), line)
        try:
            head = shell_targets.judge_segment(owner, {"code_extensions": JOURNAL_EXTS, "delegate_tools": []}).get("head", "")
        except Exception:
            head = ""
        if head in ("node", "ruby", "perl"):
            if _interp_touches(b.get("body", ""), cwd_now, unreadable, protected, cwd, markers):
                if "<unknown>" not in out:
                    out.append("<unknown>")
    return out

def touched(tool, tool_input, protected, cwd, depth=0):
    """Return the list of protected paths touched by the tool call.
    depth counts the nested judgings of heredoc bodies; it never exceeds 3."""
    try:
        if tool in FILE_TOOLS:
            p = tool_input.get("file_path") or tool_input.get("notebook_path")
            if isinstance(p, str) and is_protected(p, protected, cwd):
                return [p]
            return []

        if tool != "Bash":
            return []

        command = tool_input.get("command", "")
        if not isinstance(command, str):
            command = ""

        # the variables assigned in the chain are resolved first, so a
        # destination built on a plain literal earlier in the command is judged
        # on that literal, not on a name nobody can read.
        import safe_vars

        command = safe_vars.resolve(command)

        result = []

        import shell_rules
        import shell_split
        import shell_targets
        import journal_read_proof
        import python_write_proof

        cfg = {"code_extensions": JOURNAL_EXTS, "delegate_tools": []}
        judged = shell_rules.judge_command(command, cfg)
        targets = judged.get("targets", [])
        for t in targets:
            # a word that is only a redirection operator is never a path.
            if t != "<unknown>" and not _is_redir_op(t) and is_protected(t, protected, cwd):
                if t not in result:
                    result.append(t)

        # a cd or pushd moves the working directory, and a popd or a
        # move nobody can read leaves it unreadable; from then on every relative
        # path is judged from that directory: the arguments of the touching heads,
        # the in-place edits of sed and perl, the -t destination of cp, mv, install
        # and ln, the dd of=, the redirections and the inline python writes. A
        # write into a protected folder counts whatever its extension; a directory
        # nobody can read makes the relative paths unknown.
        shell_dests = set()
        # the heads that erase their arguments: a folder that
        # contains a protected path is the place the journal lives, and
        # removing it is a write of the journal.
        REMOVING_HEADS = {"rm", "unlink", "truncate", "shred"}

        def _parent_zone(path):
            try:
                p = os.path.realpath(os.path.expanduser(path))
            except Exception:
                return False
            for x in protected:
                try:
                    px = os.path.realpath(os.path.expanduser(x))
                except Exception:
                    continue
                if p != px and px.startswith(p + os.sep):
                    return True
            return False

        def scan(segs_list, bodies_list):
            # one pass of the touch scan over a list of segments,
            # with its own working-directory state; the protected-path test is
            # the same for every pass.
            cwd_local = cwd
            unreadable_local = False

            def judge(dest, parent=False):
                if not dest:
                    return
                # a word that is only a redirection operator is never a path.
                if _is_redir_op(dest):
                    return
                # a literal non-code file name is a data write, not a
                # protected touch, even from an unreadable directory.
                if _non_code_suffix(dest):
                    return
                if os.path.isabs(dest) or dest.startswith("~"):
                    full = dest
                else:
                    if unreadable_local:
                        if "<unknown>" not in result:
                            result.append("<unknown>")
                        return
                    full = os.path.join(cwd_local, dest)
                shell_dests.add(dest)
                if (is_protected(full, protected, cwd)
                        or (parent and _parent_zone(full))) and dest not in result:
                    result.append(dest)

            for s in segs_list:
                try:
                    words = shlex.split(s)
                except ValueError:
                    words = s.split()
                if not words:
                    continue
                head = os.path.basename(words[0])
                if head in ("cd", "pushd"):
                    if head == "pushd" and (len(words) < 2 or words[1] == "-" or words[1].startswith("+")):
                        unreadable_local = True
                        continue
                    if len(words) >= 2 and not words[1].startswith("-"):
                        dest = words[1]
                        if any(ch in dest for ch in "$`*?{(") or "__SUB__" in dest:
                            unreadable_local = True
                        elif os.path.isabs(dest) or dest.startswith("~"):
                            unreadable_local = False
                            cwd_local = dest
                        else:
                            if not unreadable_local:
                                cwd_local = os.path.join(cwd_local, dest)
                    else:
                        unreadable_local = True
                    continue
                if head == "popd":
                    unreadable_local = True
                    continue
                if head in TOUCHING_HEADS:
                    for w in words[1:]:
                        if not w.startswith("-"):
                            judge(w, parent=head in REMOVING_HEADS)
                if head in ("sed", "perl"):
                    args = words[1:]
                    if head == "sed":
                        inplace = any(a == "--in-place" or a.startswith("-i") for a in args)
                    else:
                        inplace = any(a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args)
                    if inplace:
                        if head == "sed":
                            scripts = {k + 1 for k, a in enumerate(args) if a in ("-e", "-f", "--expression", "--file")}
                            files = [a for k, a in enumerate(args) if k not in scripts and a and not a.startswith("-")]
                            files = files if scripts else files[1:]
                        else:
                            progs = {k + 1 for k, a in enumerate(args) if re.fullmatch(r"-[^-]*[eE]", a)}
                            files = [a for k, a in enumerate(args) if k not in progs and not a.startswith("-")]
                            files = files if any(re.match(r"-[^-]*[eE]", a) for a in args) else files[1:]
                        for f in files:
                            judge(f)
                dests = []
                if head in ("tee", "touch"):
                    dests = [w for w in words[1:] if not w.startswith("-")]
                elif head in ("cp", "mv", "install", "ln"):
                    nonopt = [w for w in words[1:] if not w.startswith("-")]
                    t_dirs = []
                    for k, a in enumerate(words):
                        if (a == "-t" or a == "--target-directory") and k + 1 < len(words) and not words[k + 1].startswith("-"):
                            t_dirs.append(words[k + 1])
                        elif a.startswith("-t") and len(a) > 2 and not a.startswith("--"):
                            t_dirs.append(a[2:])
                        elif a.startswith("--target-directory="):
                            t_dirs.append(a.split("=", 1)[1])
                    if t_dirs:
                        dests = t_dirs
                    elif nonopt:
                        dests = [nonopt[-1]]
                elif head in WRITE_DEST_HEADS:
                    nonopt = [w for w in words[1:] if not w.startswith("-")]
                    if nonopt:
                        dests = [nonopt[-1]]
                if head == "dd":
                    dests += [a[3:] for a in words[1:] if a.startswith("of=")]
                dests += _redirection_dests(s)
                for d in dests:
                    judge(d)
                if re.fullmatch(r"python3?(\.\d+)?", head):
                    codes = []
                    for k, a in enumerate(words):
                        if a == "-c" and k + 1 < len(words):
                            codes.append(words[k + 1])
                    if "<<" in s:
                        codes += [b.get("body", "") for b in bodies_list if b.get("line") and b["line"] in s]
                    for code in codes:
                        if code.strip() == "":
                            continue
                        written = python_write_proof.written_paths(code)
                        if written is None:
                            if unreadable_local or is_protected(cwd_local, protected, cwd):
                                if "<unknown>" not in result:
                                    result.append("<unknown>")
                            # inline python that builds a protected
                            # path from the personal folder next to a protected
                            # name is a touch, unless the code is a proven read.
                            import python_read_proof

                            if not python_read_proof.read_proven(code) and _python_home_touch(code, _zone_markers(protected)):
                                if "<unknown>" not in result:
                                    result.append("<unknown>")
                        else:
                            for p in written:
                                judge(p)
                    # -mMODULE is -m MODULE everywhere. A json.tool
                    # run with 0 or 1 positional is a strict reader; with 2 the
                    # second is a write target judged like a > destination; with
                    # more positionals or an unknown option it is a contact. Any
                    # other module that names the zone is a contact too.
                    ms = _module_of_python(words[1:])
                    if ms is not None:
                        module, rest = ms
                        if module == "json.tool":
                            pos = _json_tool_positionals(rest)
                            if pos is None or len(pos) > 2:
                                if "<unknown>" not in result:
                                    result.append("<unknown>")
                            elif len(pos) == 2:
                                d = pos[1]
                                if _target_unreadable(d) and any(_component_in(d, n) for n in _dotted_zone_names(protected)):
                                    if "<unknown>" not in result:
                                        result.append("<unknown>")
                                else:
                                    judge(d)
                        else:
                            named = next((w for w in rest if _word_names_zone(w, protected, cwd_local, _zone_markers(protected))), None)
                            if named is not None and named not in result:
                                result.append(named)

        sp = shell_split.split_command(command)
        bodies = sp.get("bodies", [])
        # the body of a heredoc read by a shell is cut into
        # commands and judged like the rest of the command; a body read by an
        # interpreter that is not a shell is judged as code, never cut.
        segs = list(sp.get("segments", []))
        for b in bodies:
            line = b.get("line", "")
            if not line:
                continue
            local = shell_split.split_segments(line)
            owner = next((x for x in local if "<<" in x), line)
            try:
                head = shell_targets.judge_segment(owner, cfg).get("head", "")
            except Exception:
                head = ""
            if head in shell_targets.SHELLS:
                segs += shell_split.split_segments(b.get("body", ""))
        scan(segs, bodies)
        # the touching heads are judged again on the text
        # resolved the way the public judge resolves it (chain_vars, then
        # shell_vars): a journal path bound to a variable earlier in the
        # command is read on that value; the same protected-path test
        # applies.
        try:
            import chain_vars
            import shell_vars

            resolved2 = shell_vars.resolve(chain_vars.resolve_chained(command))
        except Exception:
            resolved2 = None
        if resolved2 is not None and resolved2 != command:
            try:
                sp2 = shell_split.split_command(resolved2)
                if sp2["error"] is None:
                    scan(list(sp2.get("segments", [])), sp2.get("bodies", []))
            except Exception:
                pass

        # a journal read by proven inline code is a read, not a touch:
        # a target named only by the code is dropped; a target that a shell tool of
        # the same command also writes stays.
        read_paths = []
        for text in _python_code_texts(command, cfg):
            paths = journal_read_proof.proven_reads(text)
            if paths:
                read_paths.extend(paths)
        if read_paths:
            norm_reads = {normal(p, cwd) for p in read_paths}
            kept = []
            for t in result:
                if t != "<unknown>" and normal(t, cwd) in norm_reads and t not in shell_dests:
                    continue
                kept.append(t)
            result = kept

        illisible = any(_target_unreadable(t) for t in targets if not _is_redir_op(t))
        # a python segment whose every inline code is a proven read
        # gives no unreadable target to this control; only the other segments
        # decide it. The head of each such segment is replaced by a no-op in a
        # copy of the command, and the copy is judged again: an unreadable target
        # that survives without the reader still counts. In every doubt the
        # earlier verdict stands.
        if illisible:
            readers = [s for s in segs if _proven_python_reader(s, bodies)]
            if readers:
                variant = command
                ok = True
                for s in readers:
                    m = re.search(r"\bpython3?(\.\d+)?\b", s)
                    if m is None:
                        ok = False
                        break
                    repl = s[:m.start()] + "true" + s[m.end():]
                    pos = variant.find(s)
                    while pos != -1:
                        before = variant[pos - 1] if pos > 0 else ""
                        after = variant[pos + len(s)] if pos + len(s) < len(variant) else ""
                        if (not before or before in " \t\n;|&(") and (not after or after in " \t\n;|&)"):
                            break
                        pos = variant.find(s, pos + 1)
                    if pos == -1:
                        ok = False
                        break
                    variant = variant[:pos] + repl + variant[pos + len(s):]
                if ok and variant != command:
                    try:
                        vtargets = shell_rules.judge_command(variant, cfg).get("targets", [])
                        illisible = any(_target_unreadable(t) for t in vtargets if not _is_redir_op(t))
                    except Exception:
                        pass
        # a redirection destination nobody can read but named like a
        # journal (the dotted basename of a protected path, as a whole component)
        # is a contact. Only the segments of the command itself are looked at:
        # a variable set inside a quoted heredoc body is resolved by the body's
        # own judging, not by this control.
        if not illisible and _named_unreadable_dest(list(sp.get("segments", [])), protected):
            illisible = True
        # with an unreadable target, the name counts only on the
        # resolved path of a word, a name carried by an unresolved word stands.
        if illisible and _command_names_zone(segs, bodies, protected, cwd, _zone_markers(protected)):
            if "<unknown>" not in result:
                result.append("<unknown>")

        # the whitelist control adds to the checks above, it never
        # replaces them: a call is touched when any of the controls says so.
        sp_judged = dict(sp)
        sp_judged["segments"] = segs
        for t in _whitelist_touches(command, sp_judged, protected, cwd):
            if t not in result:
                result.append(t)

        # the body of a heredoc read by a shell is a command of its
        # own, judged by touched itself, same protected paths, same cwd. A quoted
        # body is judged as it stands, so a variable set inside it resolves
        # inside it; an unquoted body that expands a subshell is a contact.
        if depth < 3:
            for b in bodies:
                if not _shell_read_heredoc(b):
                    continue
                body = b.get("body", "")
                if not body.strip():
                    continue
                if not _heredoc_is_quoted(b) and ("$(" in body or "`" in body):
                    if "<unknown>" not in result:
                        result.append("<unknown>")
                    continue
                for t in touched("Bash", {"command": body}, protected, cwd, depth + 1):
                    if t not in result:
                        result.append(t)

        return result
    except Exception:
        return ["<unknown>"]

def run_autotest():
    """Run built-in tests and return True if all pass."""
    H = os.path.realpath(tempfile.mkdtemp())
    # ~ in the fixtures is the test home, as it is in the real calls.
    old_expanduser = os.path.expanduser

    def expanduser_h(p):
        if p == "~":
            return H
        if p.startswith("~/"):
            return H + os.sep + p[2:]
        return old_expanduser(p)

    os.path.expanduser = expanduser_h
    try:
        os.makedirs(os.path.join(H, "blocks"), exist_ok=True)
        for rel in ["delegations.jsonl", "guard.json", "blocks/guard.jsonl", "audit.jsonl"]:
            with open(os.path.join(H, rel), "w") as fh:
                pass

        protected = protected_paths(H, {"delegation_logs": ["delegations.jsonl"], "audit_log": "audit.jsonl"})

        TOUCH = [
            ("Bash", f"echo x >> {H}/delegations.jsonl", [f"{H}/delegations.jsonl"]),
            ("Bash", f"rm {H}/blocks/guard.jsonl", [f"{H}/blocks/guard.jsonl"]),
            ("Bash", f"echo x >> {H}/sub/../audit.jsonl", [f"{H}/sub/../audit.jsonl"]),
            ("Bash", f"mv {H}/delegations.jsonl /tmp/x", [f"{H}/delegations.jsonl"]),
            ("Write", f"{H}/guard.json", [f"{H}/guard.json"]),
        ]

        FREE = [
            f"wc -l {H}/delegations.jsonl",
            f"tail -3 {H}/blocks/guard.jsonl | cut -c1-80",
            f"cp {H}/delegations.jsonl /tmp/copy.jsonl",
            f"echo x >> {H}/notes.jsonl",
            f"rm {H}/notes.jsonl",
        ]

        all_pass = True

        # Proof 1
        ep1_pass = True
        ep1_error = None
        for idx in range(3):
            tool, cmd, expected = TOUCH[idx]
            tool_input = {"command": cmd} if tool == "Bash" else {"file_path": cmd}
            actual = touched(tool, tool_input, protected, H)
            if actual != expected:
                ep1_pass = False
                ep1_error = (expected, actual)
                break
        if ep1_pass:
            print("PASS 1: first three TOUCH tests")
        else:
            print(f"FAIL 1: expected {ep1_error[0]!r}, got {ep1_error[1]!r}")
            all_pass = False

        # Proof 2
        ep2_pass = True
        ep2_error = None
        # 4th TOUCH (mv)
        tool, cmd, expected = TOUCH[3]
        tool_input = {"command": cmd}
        actual = touched(tool, tool_input, protected, H)
        if actual != expected:
            ep2_pass = False
            ep2_error = (expected, actual)
        else:
            # 5th TOUCH (Write)
            tool, path, expected = TOUCH[4]
            tool_input = {"file_path": path, "content": "x"}
            actual = touched(tool, tool_input, protected, H)
            if actual != expected:
                ep2_pass = False
                ep2_error = (expected, actual)
            else:
                # Edit test
                expected = ["guard.json"]
                actual = touched("Edit", {"file_path": "guard.json", "old_string": "a", "new_string": "b"}, protected, H)
                if actual != expected:
                    ep2_pass = False
                    ep2_error = (expected, actual)
        if ep2_pass:
            print("PASS 2: last two TOUCH and Edit")
        else:
            print(f"FAIL 2: expected {ep2_error[0]!r}, got {ep2_error[1]!r}")
            all_pass = False

        # Proof 3
        ep3_pass = True
        ep3_error = None
        for cmd in FREE:
            actual = touched("Bash", {"command": cmd}, protected, H)
            if actual != []:
                ep3_pass = False
                ep3_error = ([], actual)
                break
        if ep3_pass:
            print("PASS 3: FREE commands")
        else:
            print(f"FAIL 3: expected {ep3_error[0]!r}, got {ep3_error[1]!r}")
            all_pass = False

        # Proof 4
        ep4_pass = True
        ep4_error = None
        actual = touched("Bash", {"command": f"echo x >> $(echo {H})/delegations.jsonl"}, protected, H)
        expected = ["<unknown>"]
        if actual != expected:
            ep4_pass = False
            ep4_error = (expected, actual)
        else:
            actual = touched("Read", {"file_path": H + "/delegations.jsonl"}, protected, H)
            expected = []
            if actual != expected:
                ep4_pass = False
                ep4_error = (expected, actual)
            else:
                actual = touched("Bash", None, protected, H)
                expected = ["<unknown>"]
                if actual != expected:
                    ep4_pass = False
                    ep4_error = (expected, actual)
        if ep4_pass:
            print("PASS 4: unknown write, read, None")
        else:
            print(f"FAIL 4: expected {ep4_error[0]!r}, got {ep4_error[1]!r}")
            all_pass = False

        # Proof 5
        proc = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True)
        if proc.returncode == 0 and proc.stdout.startswith("NAME      journal_guard.py"):
            print("PASS 5: --notice subprocess")
        else:
            print(f"FAIL 5: expected returncode 0 and stdout starting with 'NAME      journal_guard.py', got returncode {proc.returncode}, stdout prefix {proc.stdout[:30]!r}")
            all_pass = False

        # Proof 6
        ep6_pass = True
        ep6_error = None
        FIX6 = [
            (f"S=/tmp/zz; cp {H}/blocks/guard.jsonl $S/guard.jsonl", []),
            ("python3 - <<'EOF'\nimport json\nfor l in open('" + f"{H}/blocks/guard.jsonl" + "'): print(json.loads(l))\nEOF", []),
            (f"cp {H}/blocks/guard.jsonl {H}/blocks/guard.jsonl.bak", [f"{H}/blocks/guard.jsonl.bak"]),
            (f"S={H}/blocks; cp /tmp/x $S/guard.jsonl", "non-empty"),
            ('python3 -c "open(\'%s/blocks/guard.jsonl\',\'a\').write(\'x\')"' % H, "non-empty"),
            (f"cd {H}/blocks && cp /tmp/a guard.jsonl", "non-empty"),
        ]
        for idx, (cmd, expected) in enumerate(FIX6, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep6_pass = False
                    ep6_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep6_pass = False
                ep6_error = (expected, actual)
                break
        if ep6_pass:
            print("PASS 6: proven reads free, protected write destinations touched")
        else:
            print(f"FAIL 6: expected {ep6_error[0]!r}, got {ep6_error[1]!r}")
            all_pass = False

        # Proof 7
        ep7_pass = True
        ep7_error = None
        FIX7 = [
            (f"pushd {H}/blocks; cp /tmp/a g", "non-empty"),
            (f"cd {H}/blocks; truncate -s0 guard.jsonl", "non-empty"),
            (f"cp -t {H}/blocks /tmp/a", "non-empty"),
            (f"cd {H}/blocks; cp guard.jsonl /tmp/g.jsonl", []),
            (f"cd {H}/blocks && ls -la && tail -3 guard.jsonl", []),  # lang-ok
        ]
        for idx, (cmd, expected) in enumerate(FIX7, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep7_pass = False
                    ep7_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep7_pass = False
                ep7_error = (expected, actual)
                break
        if ep7_pass:
            print("PASS 7: relative paths after cd or pushd are judged from that folder")
        else:
            print(f"FAIL 7: expected {ep7_error[0]!r}, got {ep7_error[1]!r}")
            all_pass = False

        # Proof 8
        ep8_pass = True
        ep8_error = None
        FIX8 = [
            ("rm -rf ~", "non-empty"),
            ("find ~/blocks -delete", "non-empty"),
            ("sh -c 'rm ~/blocks/g.jsonl'", "non-empty"),
            ("sort -o ~/blocks/g.jsonl /tmp/a", "non-empty"),
            ("grep -c x ~/blocks/g.jsonl", []),
            ('git commit -m "voir ~/blocks/g.jsonl" -- a.md', []),  # lang-ok
            ("cp ~/blocks/g.jsonl /tmp/c.jsonl", []),
        ]
        for idx, (cmd, expected) in enumerate(FIX8, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep8_pass = False
                    ep8_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep8_pass = False
                ep8_error = (expected, actual)
                break
        if ep8_pass:
            print("PASS 8: the guard lists readers, any other contact is a touch")
        else:
            print(f"FAIL 8: expected {ep8_error[0]!r}, got {ep8_error[1]!r}")
            all_pass = False

        # Proof 9
        ep9_pass = True
        ep9_error = None
        FIX9 = [
            ("rm ~/blo*/g.jsonl", "non-empty"),
            ("rm ~/b{locks,x}/g.jsonl", "non-empty"),
            ("rm ~/blocks/g.json?", "non-empty"),
            ("cd ~/blocks && make", "non-empty"),
            ("cd ~/blocks && python3 /tmp/x.py", "non-empty"),
            ("cd ~/blocks && ./x", "non-empty"),
            ("cd ~ && make", "non-empty"),
            ("cd /tmp && make", []),
            ("wc -l ~/blocks/*.jsonl", []),
            ("cd ~/blocks && tail -3 g.jsonl", []),
            ("rm /tmp/w/*.txt", []),
            ("python3 -c \"open('bin/blocks_replay.py').read()\"", []),
        ]
        for idx, (cmd, expected) in enumerate(FIX9, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep9_pass = False
                    ep9_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep9_pass = False
                ep9_error = (expected, actual)
                break
        if ep9_pass:
            print("PASS 9: pattern prefixes reaching the zone and programs started from inside it are a touch")
        else:
            print(f"FAIL 9: expected {ep9_error[0]!r}, got {ep9_error[1]!r}")
            all_pass = False

        # Proof 10
        ep10_pass = True
        ep10_error = None
        FIX10 = [
            ("python3 - <<'EOF'\nc2=\"cd $S/tp && ls > $S/run.txt\"\nprint(c2)\nEOF", []),
            ("D=/tmp/w; ls $D/blocks; tail -c 9 $D/blocks/g.jsonl; echo $(date)", []),
            ("bash <<'EOF'\nrm ~/blocks/g.jsonl\nEOF", "non-empty"),
            ("python3 - <<'EOF'\nimport os\nos.remove(os.path.expanduser('~/blocks/g.jsonl'))\nEOF", "non-empty"),
            ("X=$Y; rm $X/blocks/g.jsonl", "non-empty"),
        ]
        for idx, (cmd, expected) in enumerate(FIX10, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep10_pass = False
                    ep10_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep10_pass = False
                ep10_error = (expected, actual)
                break
        if ep10_pass:
            print("PASS 10: a python heredoc body is code, a name counts only on its resolved path")
        else:
            print(f"FAIL 10: expected {ep10_error[0]!r}, got {ep10_error[1]!r}")
            all_pass = False

        # Proof 11
        ep11_pass = True
        ep11_error = None
        FIX11 = [
            ("python3 - <<'EOF'\nimport os, shutil\nshutil.rmtree(os.environ['HOME'] + '/blocks')\nEOF", "non-empty"),
            ("python3 -c \"import os; os.remove(os.getenv('HOME') + '/blocks/g.jsonl')\"", "non-empty"),
            ("python3 - <<'EOF'\nfrom pathlib import Path\n(Path.home() / 'blocks' / 'g.jsonl').unlink()\nEOF", "non-empty"),
            ("python3 -c \"print('voir ~/blocks/g.jsonl')\"", []),  # lang-ok
        ]
        for idx, (cmd, expected) in enumerate(FIX11, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep11_pass = False
                    ep11_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep11_pass = False
                ep11_error = (expected, actual)
                break
        if ep11_pass:
            print("PASS 11: inline python building a protected path from the home folder is a touch")
        else:
            print(f"FAIL 11: expected {ep11_error[0]!r}, got {ep11_error[1]!r}")
            all_pass = False

        # Proof 12
        # rm of a journal through a variable, and of a folder
        # that contains a journal, are touches; reads and out-of-zone deletes
        # stay free.
        ep12_pass = True
        ep12_error = None
        FIX12 = [
            ("F=~/blocks/g.jsonl; rm $F", "non-empty"),
            ("F=~/blocks/g.jsonl; rm \"$F\"", "non-empty"),
            ("B=~/blocks; rm -rf $B", "non-empty"),
            ("B=~; rm -rf $B", "non-empty"),
            ("rm -rf ~/blocks", "non-empty"),
            ("F=~/blocks/g.jsonl; tail -5 $F", []),
            ("S=/tmp/zz; rm $S/notes.txt", []),
            ("rm -rf /tmp/zz", []),
        ]
        for idx, (cmd, expected) in enumerate(FIX12, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep12_pass = False
                    ep12_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep12_pass = False
                ep12_error = (expected, actual)
                break
        if ep12_pass:
            print("PASS 12: rm of a journal or of a journal folder through a variable is a touch")
        else:
            print(f"FAIL 12: expected {ep12_error[0]!r}, got {ep12_error[1]!r}")
            all_pass = False

        # Proof 13
        # a python segment whose inline code is a proven read is
        # a reader run from a folder of the zone; an unproven code, an unquoted
        # heredoc that expands, and an unresolved head stay touches.
        ep13_pass = True
        ep13_error = None
        FIX13 = [
            ("cd ~/blocks && python3 - <<'E'\nprint(1)\nE", []),
            ("cd ~/blocks && python3 -c \"print(open('guard.jsonl').read())\"", []),
            ("cd ~/blocks && python3 - <<'E'\nfor l in open('guard.jsonl'):\n    print(l)\nE", []),
            ("cd ~/blocks && python3 -c \"open('guard.jsonl','w').write('')\"", "non-empty"),
            ("cd ~/blocks && python3 - <<EOF\n$(touch guard.jsonl)\nprint(1)\nEOF", "non-empty"),
            ("cd ~/blocks && python3 -c \"import os; os.remove('guard.jsonl')\"", "non-empty"),
            ("cd ~/blocks && $CMD", "non-empty"),
            ("cd ~/blocks && python3 -c \"print(1)\" && $CMD", "non-empty"),
        ]
        for idx, (cmd, expected) in enumerate(FIX13, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep13_pass = False
                    ep13_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep13_pass = False
                ep13_error = (expected, actual)
                break
        if ep13_pass:
            print("PASS 13: a proven inline read run from a folder of the zone is a reader, not a touch")
        else:
            print(f"FAIL 13: expected {ep13_error[0]!r}, got {ep13_error[1]!r}")
            all_pass = False

        # Proof 14
        # a heredoc body read by a shell is judged as a command of
        # its own, a json.tool output file is a write target, and an unreadable
        # target named guard.json is a contact; a variable set inside a quoted
        # body resolves inside it, an out-of-zone folder stays free.
        ep14_pass = True
        ep14_error = None
        FIX14 = [
            ("bash <<'EOF'\nD=~; echo > $D/guard.json\nEOF", "non-empty"),
            ("cat <<'E' | bash\nD=~/blocks; rm $D/guard.jsonl\nE", "non-empty"),
            ("echo > $D/guard.json", "non-empty"),
            ("python3 -m json.tool ~/guard.json ~/guard.json", "non-empty"),
            ("python3 -m json.tool /tmp/x.json ~/guard.json", "non-empty"),
            ("bash <<EOF\necho bonjour\nEOF", []),
            ("bash <<'EOF'\nwc -l ~/blocks/guard.jsonl\nEOF", []),
            ("python3 -m json.tool /tmp/a.json /tmp/b.json", []),
            ("bash <<'EOF'\nD=/tmp/w; echo x > $D/guard.json\nEOF", []),
        ]
        for idx, (cmd, expected) in enumerate(FIX14, 1):
            actual = touched("Bash", {"command": cmd}, protected, H)
            if expected == "non-empty":
                if not actual:
                    ep14_pass = False
                    ep14_error = ("non-empty", actual)
                    break
            elif actual != expected:
                ep14_pass = False
                ep14_error = (expected, actual)
                break
        if ep14_pass:
            print("PASS 14: a shell heredoc body, a json.tool output file and an unreadable target named guard.json are touches")
        else:
            print(f"FAIL 14: expected {ep14_error[0]!r}, got {ep14_error[1]!r}")
            all_pass = False

        return all_pass
    finally:
        os.path.expanduser = old_expanduser
        shutil.rmtree(H, ignore_errors=True)

def print_notice():
    """Print the notice exactly."""
    notice = (
        "NAME      journal_guard.py - tells whether an agent tool call writes, deletes, moves, links or disarms a protected guard file: the delegation log, the refusal logs, the guard settings.\n"
        "READS     the tool call it is given, and the guard settings for the paths to protect.\n"
        "WRITES    nothing: touched() returns the protected paths the call touches, \"<unknown>\" when a write it cannot read sits beside a protected name.\n"
        "EXAMPLE   python3 journal_guard.py --autotest\n"
        "PITFALLS  2026-10-06 rm of a guard journal through a variable, or text piped into an interpreter with extra flags, was not judged; both are now.\n"
        "          2026-10-03 echo >> delegations.jsonl was judged free, as were rm, mv, ln and edits of guard.json: the agent could forge or erase its own proof; only delegate.py writes these files now.\n"
        "          2026-10-05 a read of a guard log (the log as copy source, or opened read-only by proven inline code) was refused; variables set in the chain are now resolved first, and any write into a protected folder counts whatever its extension.\n"
        "          2026-10-05 an in-place edit (sed -i, truncate, rm, open for writing) of a relative path after cd or pushd into a protected folder, and a cp -t destination, were free; relative paths are now judged from the last cd or pushd.\n"
        "          2026-10-05 the log guard listed the tools that write, so rm -rf on a parent folder, find -delete, xargs rm, editors and inline interpreters went through; it now lists the tools that only read, and any other contact is a touch.\n"
        "          2026-10-06 the log guard compared glob and brace words as plain text and ignored programs started from inside the protected folder; a pattern whose literal prefix reaches a protected path, and any non-reader run from inside it, is now a touch.\n"
        "          2026-10-06 the log guard split the body of a heredoc read by python as shell commands and counted a protected name in a path that resolves outside the zone; such a body is now judged as inline code and a name counts only on its resolved path.\n"
        "          2026-10-06 inline python that built a protected path from the home folder through environ, getenv or Path.home went through; a protected name next to any home source is now a touch unless the code is a proven read.\n"
        "          2026-10-05 a redirection or cp/tee destination with a literal non-code file name (a .txt, .json, .np, .init, ...) after cd into an unreadable folder was refused as a journal touch; the literal suffix now decides, and an env prefix or a NAME=value argument is no longer read as a file contact.\n"
        "          2026-10-14 a proven read run from a folder of the zone was taken for a write: a python segment whose inline code is a proven read is a reader there.\n"
        "          2026-10-15 a heredoc body read by a shell, a json.tool output file and an unreadable target named guard.json were never judged: they are now.\n"
    )
    print(notice)

def main():
    if len(sys.argv) != 2:
        print("usage: journal_guard.py --notice | --autotest")
        sys.exit(2)
    if sys.argv[1] == "--notice":
        print_notice()
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        success = run_autotest()
        sys.exit(0 if success else 1)
    else:
        print("usage: journal_guard.py --notice | --autotest")
        sys.exit(2)

if __name__ == "__main__":
    main()
