import ast
import os
import re
import subprocess
import sys
import warnings

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import command_head
import shell_quotes
import shell_split
import shell_tokens
import shell_targets
import inline_writes
import python_read_proof
import python_write_proof
import python_file_import
import shell_vars
import chain_vars
import safe_vars
import restore_rules
import quote_mask

WRITE_SIGNS = (
    "open(",
    ".write",
    "write_text",
    "write_bytes",
    "writeFileSync",
    "appendFileSync",
    "createWriteStream",
    "File.write",
    "shutil.copy",
    "os.replace",
    "os.rename",
)
RUN_SIGNS = (
    "os.system",
    "subprocess",
    "popen",
    "execSync",
    "spawnSync",
    "system(",
)
LITERAL = re.compile(r"""(['"])([^'"\n]+)\1""")
RUN_CALL = re.compile(
    r"""(?:system|popen|execSync|spawnSync|run|call|check_output|check_call|Popen)\(\s*(['"])(.+?)\1"""
)

# a literal of inline Python names a write target only through a write sink.
SUBPROCESS_FUNCS = ("run", "call", "check_call", "check_output", "Popen")
WRITE_TOOLS = ("cp", "mv", "tee", "install", "rsync", "ln", "touch", "sed")
READ_TOOLS = (
    "grep", "egrep", "fgrep", "rg", "head", "tail", "cat", "wc", "less", "more",
    "diff", "cmp", "file", "stat", "ls", "find", "sort", "uniq", "cut", "tr",
    "ps", "date", "pwd", "which", "type", "echo", "printf",
)
WRITE_ALIAS_MODULES = ("os", "shutil", "pathlib")
WRITE_ALIAS_FUNCS = (
    "write_text", "write_bytes", "touch", "open", "copy", "copy2", "copyfile", "move",
    "replace", "rename", "renames", "remove", "unlink", "rmdir", "removedirs",
    "link", "symlink", "system", "popen",
)


def _subprocess_names(tree):
    # the names that denote the subprocess module (import and aliases).
    names = {"subprocess"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name == "subprocess" or a.name.startswith("subprocess."):
                    names.add(a.asname or "subprocess")
        elif isinstance(node, ast.ImportFrom) and node.module == "subprocess":
            for a in node.names:
                names.add(a.asname or a.name)
    return names


def _write_alias(code):
    # a sink bound to another name (f = open, s = os.system,
    # from os import rename as r, an imported copy module, getattr): the whole
    # body keeps its previous verdict. Returns True on the first sign.
    try:
        # judged code holding an invalid escape makes ast.parse emit a
        # SyntaxWarning; the silence is local to this parse, nothing else changes.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(code)
    except Exception:
        return False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in WRITE_ALIAS_MODULES and a.asname is not None:
                    return True
        elif isinstance(node, ast.ImportFrom):
            root = (node.module or "").split(".")[0]
            for a in node.names:
                if a.name in WRITE_ALIAS_FUNCS and (root in WRITE_ALIAS_MODULES or True):
                    return True
        elif isinstance(node, ast.Assign):
            v = node.value
            if isinstance(v, ast.Name) and v.id == "open":
                return True
            if isinstance(v, ast.Attribute) and v.attr in WRITE_ALIAS_FUNCS:
                return True
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "getattr":
            return True
    return False


def _python_head(t):
    # a command token that names a python interpreter: the sys.executable
    # marker, or a plain word whose base name starts with python (python3, /usr/bin/python).
    return t[0] == "interp" or (t[0] == "str" and os.path.basename(t[1] or "").startswith("python"))


def _c_code(toks):
    # the text run by <interpreter> -c CODE, an interpreter by plain
    # name included ; None otherwise. A non-literal CODE stays unread here.
    for i, t in enumerate(toks):
        if t and t[0] == "str" and t[1] in ("-c", "--command"):
            if i >= 1 and toks[i - 1] is not None and _python_head(toks[i - 1]):
                if i + 1 < len(toks) and toks[i + 1] is not None and toks[i + 1][0] == "str":
                    return toks[i + 1][1]
    return None


def _cmd_elts(first):
    # the elements of a command list, including through a + of
    # lists; None if it is not a readable command list.
    def els(node):
        if isinstance(node, (ast.List, ast.Tuple)):
            return list(node.elts)
        if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
            l = els(node.left)
            r = els(node.right)
            if l is None or r is None:
                return None
            return l + r
        return None
    return els(first)


def _is_interp(e):
    return (isinstance(e, ast.Attribute) and e.attr == "executable"
            and isinstance(e.value, ast.Name) and e.value.id == "sys")


def _judge_cmd_list(toks, config, depth, max_depth, exts):
    # a command list readable from Python. Returns a write/unknown
    # verdict, or None if the command is proven free:
    #  - <interpreter> -c CODE: CODE is judged as python code (an interpreter by
    #    plain name included);
    #  - <interpreter> script: the script is read, a readable argument that names
    #    a code file is a write target;
    #  - <interpreter> -m module: a readable argument that names a code file is a
    #    write target;
    #  - tool head (cp, mv, sed, ...): the rebuilt command is judged;
    #  - unreadable head: unknown.
    unknown_r = {"verdict": "unknown", "targets": ["<unknown>"],
                 "reason": "inline code runs a command the guard cannot read"}
    if not toks:
        return dict(unknown_r)
    head = toks[0]
    if head is None:
        return dict(unknown_r)
    is_py = _python_head(head)
    if not is_py:
        parts = []
        for t in toks:
            if t is None:
                return dict(unknown_r)
            parts.append("python3" if t[0] == "interp" else t[1])
        r = judge_command(" ".join(parts), config, depth + 1, max_depth)
        return None if r["verdict"] == "free" else r
    ccode = _c_code(toks)
    if ccode is not None:
        if depth >= max_depth:
            return {"verdict": "unknown", "targets": ["<unknown>"], "reason": "python runs code too deep"}
        r = judge_code(ccode, config, depth + 1, max_depth, ("python3",))
        return None if r["verdict"] == "free" else r
    if len(toks) > 1 and toks[1] is not None and toks[1][0] == "str" and toks[1][1] in ("-m", "--module"):
        for t in toks[2:]:
            if t is None:
                return dict(unknown_r)
            if t[0] == "str" and shell_tokens.classify_target(t[1], exts) == "code":
                return {"verdict": "write", "targets": [t[1]], "reason": "inline code"}
        return None
    # the first non-flag argument is the script (read); the readable arguments that
    # follow and name a code file are write targets
    i = 1
    while i < len(toks):
        t = toks[i]
        if t is None:
            return dict(unknown_r)
        if t[0] == "str" and t[1].startswith("-") and len(t[1]) > 1:
            i += 1
            continue
        break
    if i >= len(toks):
        return None
    writes = []
    for t in toks[i + 1:]:
        if t is None:
            return dict(unknown_r)
        v = t[1]
        if v.startswith("-"):
            v = v.split("=", 1)[1] if "=" in v else ""
        if v and shell_tokens.classify_target(v, exts) == "code":
            writes.append(v)
    if writes:
        return {"verdict": "write", "targets": writes, "reason": "inline code"}
    return None


def _subprocess_sinks(code, config, depth, max_depth):
    # the subprocess / os.system calls of a python body.
    # Returns (non-free verdicts, unknown, count of commands read and judged):
    # a write tool command or one passed through a shell is judged; the code run
    # by <interpreter> -c is judged as python code (an interpreter by plain name
    # included); an unreadable command keeps the previous verdict (unknown).
    exts = list(config.get("code_extensions", []))
    results = []
    unknown = False
    n_runs = 0
    try:
        # judged code holding an invalid escape makes ast.parse emit a
        # SyntaxWarning; the silence is local to this parse, nothing else changes.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(code)
    except Exception:
        return results, False, 0
    bindings = inline_writes._build_bindings(tree)
    sub_names = _subprocess_names(tree)
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not isinstance(node.func, ast.Attribute):
            continue
        attr = node.func.attr
        base = node.func.value
        # os.system / os.popen / X.system (a shell command in a string)
        if attr in ("system", "popen"):
            if node.args and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                r = judge_command(node.args[0].value, config, depth + 1, max_depth)
                if r["verdict"] != "free":
                    results.append(r)
                n_runs += 1
            else:
                unknown = True
            continue
        if attr in SUBPROCESS_FUNCS and isinstance(base, ast.Name) and base.id in sub_names:
            if not node.args:
                unknown = True
                continue
            first = node.args[0]
            if isinstance(first, ast.Constant) and isinstance(first.value, str):
                r = judge_command(first.value, config, depth + 1, max_depth)
                if r["verdict"] != "free":
                    results.append(r)
                n_runs += 1
                continue
            elts = _cmd_elts(first)
            if elts is None:
                unknown = True
                continue
            toks = []
            for e in elts:
                if _is_interp(e):
                    toks.append(("interp", None))
                    continue
                vals = inline_writes._resolve(e, bindings)
                toks.append(("str", vals[0]) if vals else None)
            r = _judge_cmd_list(toks, config, depth, max_depth, exts)
            if r is not None:
                results.append(r)
                if r["verdict"] == "unknown":
                    unknown = True
            n_runs += 1
            continue
    return results, unknown, n_runs


def _sink_whitelist(code, config, depth, max_depth, exts, exec_results,
                  sub_results=(), sub_unknown=False, sub_reads=0, words=()):
    # the refused body is re-examined by the write-sink whitelist:
    # a literal is a target only if it reaches a sink; the commands started by
    # subprocess are judged; the whole body is freed if everything is proven.
    for r in exec_results:
        if r.get("verdict") == "write":
            return {"verdict": "write",
                    "targets": [t for t in r.get("targets", []) if t != "<unknown>"],
                    "reason": r.get("reason", "inline code")}
        if r.get("verdict") == "unknown":
            return {"verdict": "unknown", "targets": ["<unknown>"],
                    "reason": r.get("reason", "inline code")}
    # the command words are the only oracle of a sys.argv[i] write target.
    summary = inline_writes.write_sinks_summary(code, words, exts)
    if summary is None:
        return {"verdict": "unknown", "targets": ["<unknown>"],
                "reason": "inline code writes to a path the guard cannot read"}
    code_targets, unreadable, n_sinks, n_temp = summary
    if code_targets:
        return {"verdict": "write", "targets": list(code_targets), "reason": "python writes a code file"}
    if unreadable:
        return {"verdict": "unknown", "targets": ["<unknown>"],
                "reason": "inline code writes to a path the guard cannot read"}
    writes = [t for r in sub_results for t in r.get("targets", [])
              if r.get("verdict") == "write" and t != "<unknown>"]
    if writes:
        return {"verdict": "write", "targets": writes, "reason": "inline code"}
    if sub_unknown:
        return {"verdict": "unknown", "targets": ["<unknown>"],
                "reason": "inline code runs a command the guard cannot read"}
    # a copy/move/replace on a base the sink scan cannot see (an alias, an attribute
    # chain, a rebound name) is a write the summary does not see: unknown.
    if python_write_proof.hazard(code):
        return {"verdict": "unknown", "targets": ["<unknown>"],
                "reason": "inline code writes to a path the guard cannot read"}
    # the refusal is lifted only on a proven form: a read sink, a command the guard
    # read and judged, or a proven read of a local module; otherwise the previous
    # verdict stands.
    if n_sinks > 0 or n_temp > 0:
        return {"verdict": "free", "targets": [], "reason": "free"}
    if python_read_proof.read_proven(python_file_import.rewrite(code)):
        return {"verdict": "free", "targets": [], "reason": "free"}
    if sub_reads > 0:
        return {"verdict": "free", "targets": [], "reason": "free"}
    return {"verdict": "unknown", "targets": ["<unknown>"],
            "reason": "inline code writes to a path the guard cannot read"}

NOTICE = """NAME      shell_rules.py - judges a whole shell command: every simple command, every subshell, inline code and code heredocs, merged into one verdict with its targets.
READS     nothing: pure module; it works on the command and a config dict (code_extensions, delegate_tools), with shell_split.py, shell_tokens.py and shell_targets.py beside it.
WRITES    nothing: judge_command() returns verdict (free, write, unknown), targets and reason.
EXAMPLE   python3 shell_rules.py --notice
PITFALLS  2026-10-07 a code file moved or copied from a temp directory into a directory destination passed; it is now judged as a code write.
          2026-10-06 literal text piped into an interpreter reading stdin ran unjudged; it is now judged as that interpreter's code.
          2026-10-06 rm of a guard journal through a variable, or text piped into an interpreter with extra flags, was not judged; both are now.
          2026-09-25 a heredoc body is judged only when the command that reads it runs code (an interpreter or a shell); otherwise it is data.
          Inline code is judged on its string literals only: a path held in a variable, or an argument list, is not seen.
          2026-10-03 Python that exec/eval built or read code, compiles, imports or loads a name the guard cannot read, or runs a name aliased to one of these, is unknown; a literal exec/eval is judged as code; a write whose target is not a string literal is unknown; git mv to a code destination is a write; a path joined under a tempfile directory or built on the name of a returned temporary file (f.name) is outside the project and stays free.
          2026-10-05 git restore/checkout of paths and a same-extension copy into a temporary folder were judged as code writes; they are free now, a copy into the project or an extension change still is a write.
          2026-10-05 a string literal of inline Python naming a code file was taken as a write target; only a literal that reaches a write sink is a target now, and code run by sys.executable -c is judged as code.
          2026-10-06 a python interpreter started by subprocess with -c under its plain name was not judged; its inline code is now judged like sys.executable -c.
          2026-10-05 a redirection to a variable folder with a literal non-code file name was refused as unreadable; the literal suffix now decides, and variables set in the chain are resolved first.
          2026-10-05 git stash, a git archive unpacked into a temporary folder and an inline write to sys.argv naming a non-code file were refused; they are judged by their real target now.
          2026-10-14 a judged code holding an invalid escape made ast.parse print a SyntaxWarning on every call: warnings are silenced around the parse only."""


# output-file names: a target that ends with one of these is not a code
# write, even when the name also happens to be a code extension.
OUTPUT_SUFFIXES = (".txt", ".json", ".err", ".out", ".log", ".md", ".init", ".doc", ".np")


def _output_name(path):
    # True when the file name ends with an output suffix.
    base = path.rsplit("/", 1)[-1]
    return os.path.splitext(base)[1] in OUTPUT_SUFFIXES


_TEMP_DIRS = ("/tmp", "/private/tmp", "/var/folders")


def _dest_temp(path):
    # a normalized path inside a temporary folder; a relative path,
    # and a .. that leaves the temporary zone, are not.
    p = os.path.normpath(path)
    if not p.startswith("/"):
        return False
    return any(p == d or p.startswith(d + "/") for d in _TEMP_DIRS)


def _copy_dir_dest(seg, config, resolved_seg=None):
    # a cp or mv whose destination is a probable folder (a . or .., a
    # word ending in /, a last component without a dot) places, for every source,
    # the file normpath(join(destination, basename(source))) in that folder; a
    # source whose name carries a code extension that is not an output name, or a
    # source in a temporary folder with the -r, -R or -a option, is a code write;
    # a destination in a temporary folder stays free (the folder is read with the
    # only resolver, safe_vars, on the chain text when the caller has it); None
    # at the least doubt, where the previous verdict stands.
    try:
        exts = list(config.get("code_extensions", []))

        def words(text):
            toks = shell_tokens.tokenize(text)
            if toks is None:
                return None
            try:
                _t, _u, plain = shell_tokens.redirections(toks, exts)
            except Exception:
                return None
            toks2, sure = command_head.skip(plain)
            if not sure:
                return None
            if toks2[0].rsplit("/", 1)[-1] not in ("cp", "mv"):
                return None
            return [a for a in toks2[1:] if a.startswith("-")], \
                [a for a in toks2[1:] if not a.startswith("-")]

        pair = words(seg)
        if pair is None:
            return None
        opts, nonopt = pair
        if len(nonopt) < 2:
            return None
        dest = nonopt[-1]
        if dest not in (".", "..") and not dest.endswith("/") and "." in dest.rsplit("/", 1)[-1]:
            return None
        recop = any(o in ("-r", "-R", "-a") for o in opts) or any(
            o.startswith("-") and not o.startswith("--") and len(o) > 2
            and any(ch in o[1:] for ch in "rRa") for o in opts)
        resolved = None
        try:
            for text in filter(None, (resolved_seg, safe_vars.resolve(seg))):
                rpair = words(text)
                if rpair is not None and len(rpair[1]) == len(nonopt):
                    resolved = rpair[1]
                    break
        except Exception:
            resolved = None
        if resolved is None:
            resolved = list(nonopt)
        if not any(ch in resolved[-1] for ch in "$`") and _dest_temp(resolved[-1]):
            return None
        files = []
        for src, rsrc in zip(nonopt[:-1], resolved[:-1]):
            code = shell_tokens.classify_target(src, exts) == "code" and not _output_name(src)
            temp = recop and _dest_temp(os.path.dirname(rsrc))
            if not (code or temp):
                continue
            f = os.path.normpath(os.path.join(dest, os.path.basename(rsrc)))
            if f not in files:
                files.append(f)
        if not files:
            return None
        return {"verdict": "write", "targets": files, "reason": "copy"}
    except Exception:
        return None


def _redir_dests(seg):
    # the file destination of every > / >> / 2> / &> in a segment
    # (a >N duplication carries no file). None when the segment cannot be tokenized.
    toks = shell_tokens.tokenize(seg)
    if toks is None:
        return None
    dests = []
    i = 0
    n = len(toks)
    while i < n:
        op = re.sub(r"^\d+", "", toks[i])
        if op in (">", ">>", ">|", "&>", "&>>"):
            if i + 1 < n:
                dests.append(toks[i + 1])
            i += 2
        elif op == ">&":
            i += 2 if (i + 1 < n and (toks[i + 1].isdigit() or toks[i + 1] == "-")) else 1
        else:
            i += 1
    return dests


# the characters that keep a word dynamic for the shell.
_DYNAMIC_CHARS = set("$`*?[{")


def _literal_word(w):
    # True for a non-empty word the shell will not expand.
    return isinstance(w, str) and w != "" and not any(c in _DYNAMIC_CHARS for c in w)


def _stash_proven(seg):
    # git stash [push] [-q] [-- paths] restores the paths to the state of the
    # last commit: it writes no code, and the quiet pop/apply is proven the same way. A plain
    # pop or apply, and any non-literal word, keep the previous verdict.
    toks = shell_tokens.tokenize(seg)
    if toks is None or os.path.basename(toks[0]) != "git":
        return False
    args = toks[1:]
    if args[:1] == ["-C"]:
        if len(args) < 2 or not _literal_word(args[1]):
            return False
        args = args[2:]
    if not args or args[0] != "stash":
        return False
    rest = args[1:]
    if rest and rest[0] in ("pop", "apply"):
        return rest[1:] == ["-q"]
    i = 0
    n = len(rest)
    if i < n and rest[i] == "push":
        i += 1
    if i < n and rest[i] == "-q":
        i += 1
    if i < n and rest[i] == "--":
        i += 1
    return all(_literal_word(w) for w in rest[i:])


def _git_archive_proven(seg):
    # git [ -C <path> ] archive <ref> [paths], every word literal.
    if seg is None:
        return False
    toks = shell_tokens.tokenize(seg)
    if toks is None or os.path.basename(toks[0]) != "git":
        return False
    args = toks[1:]
    if args[:1] == ["-C"]:
        if len(args) < 2 or not _literal_word(args[1]):
            return False
        args = args[2:]
    if not args or args[0] != "archive":
        return False
    rest = args[1:]
    return len(rest) >= 1 and all(_literal_word(w) for w in rest)


def _temp_unpack(prev_seg, tar_seg):
    # git archive <ref> [paths] | tar -x -C <folder> unpacks a snapshot into a
    # temporary folder: no code write. The folder is normalized before the comparison: a ..
    # that leaves the temporary zone, a relative folder, a missing -C, an archive operand or an
    # unreadable word keeps the previous verdict.
    toks = shell_tokens.tokenize(tar_seg)
    if toks is None or os.path.basename(toks[0]) != "tar":
        return False
    args = toks[1:]
    has_x = False
    dest = None
    n_dir = 0
    i = 0
    n = len(args)
    while i < n:
        a = args[i]
        if a == "-C":
            if i + 1 >= n:
                return False
            dest = args[i + 1]
            n_dir += 1
            i += 2
            continue
        if a.startswith("--"):
            if a == "--extract":
                has_x = True
            else:
                return False
        elif a.startswith("-"):
            if "f" in a:
                return False
            if "x" in a:
                has_x = True
        i += 1
    if not has_x or n_dir != 1:
        return False
    if not _literal_word(dest):
        return False
    p = os.path.normpath(dest)
    if not p.startswith("/"):
        return False
    temp = ("/tmp", "/private/tmp", "/var/folders")
    if not any(p == d or p.startswith(d + "/") for d in temp):
        return False
    return _git_archive_proven(prev_seg)


def _unquoted_expands(body):
    # the shell runs a $(...) command substitution and the unescaped
    # backticks of an unquoted heredoc body before any reader sees it; a plain $NAME
    # is data, not a command.
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == "\\":
            i += 2
            continue
        if c == "`":
            return True
        if c == "$" and i + 1 < n and body[i + 1] == "(":
            return True
        i += 1
    return False


# the shells that read their input, and their only allowed flag.
_STDIN_SHELLS = ("bash", "sh", "zsh")


def _plain_word(w):
    # a non-empty word the shell will not expand, with no subshell
    # marker left by the splitter.
    return _literal_word(w) and "__SUB__" not in w


def _stdin_interp(seg):
    # an interpreter whose stdin is the pipe: bash, sh, zsh with
    # short no-argument options (x, e, u, v, s, grouped), then -- and any words;
    # python, python3 with -u, -B, -E, -I, -O, -S, then -. Returns "shell" or
    # "python"; None for a script, a -c / -e code, any other flag, a <
    # redirection, or an unreadable head.
    toks = shell_tokens.tokenize(seg)
    if toks is None:
        return None
    if any(re.match(r"\d*<", t) for t in toks):
        return None
    rest, sure = command_head.skip(toks)
    if not sure or not rest:
        return None
    head = rest[0].rsplit("/", 1)[-1]
    args = []
    i = 1
    n = len(rest)
    while i < n:
        a = rest[i]
        # an output redirection keeps the pipe on stdin: the operator and its
        # target are not arguments of the interpreter.
        if re.fullmatch(r"\d*(&>>|&>|>>|>\||>)", a):
            i += 2
            continue
        if re.fullmatch(r"\d*>&", a):
            if i + 1 < n and (rest[i + 1].isdigit() or rest[i + 1] == "-"):
                i += 2
                continue
        args.append(a)
        i += 1
    if head in _STDIN_SHELLS:
        # the short no-argument options (x, e, u, v, s, grouped
        # as in -xs), then -- and any words; a script name, a -c or any other
        # flag keeps the previous verdict.
        k = 0
        n2 = len(args)
        while k < n2 and re.fullmatch(r"-[xevsu]{1,8}", args[k]):
            k += 1
        if k < n2 and args[k] == "--":
            return "shell"
        return "shell" if k == n2 else None
    if re.fullmatch(r"python3?(\.\d+)?", head):
        # the flags that take no argument (u, B, E, I, O, S),
        # then the - that reads the script from stdin; a script name, a -c or
        # any other flag keeps the previous verdict.
        k = 0
        n2 = len(args)
        while k < n2 and args[k] in ("-u", "-B", "-E", "-I", "-O", "-S"):
            k += 1
        if k < n2 and args[k] == "-":
            k += 1
        return "python" if k == n2 else None
    return None


def _segment_seps(outer):
    # the top-level segments with the kind of separator that ends each
    # one ("|", ";", "\n", "&", "||", "&&", None for the last); empty segments are
    # dropped, the way the splitter does, so the order matches its segments.
    masked = shell_quotes.mask_quotes(outer)
    n = len(masked)
    i = 0
    start = 0
    out = []
    while i < n:
        if masked[i] == "\\":
            i += 2
            continue
        if i + 1 < n and masked[i:i + 2] in ("||", "&&"):
            seg = shell_split.clean_segment(outer[start:i])
            if seg:
                out.append((seg, masked[i:i + 2]))
            start = i + 2
            i += 2
            continue
        c = masked[i]
        if (c in (";", "\n")
                or (c == "|" and (i == 0 or masked[i - 1] != ">"))
                or (c == "&" and (i == 0 or masked[i - 1] not in ("<", ">"))
                    and (i + 1 >= n or masked[i + 1] != ">"))):
            seg = shell_split.clean_segment(outer[start:i])
            if seg:
                out.append((seg, c))
            start = i + 1
            i += 1
            continue
        i += 1
    seg = shell_split.clean_segment(outer[start:])
    if seg:
        out.append((seg, None))
    return out


def _piped_text(prev):
    # the text an echo / printf of literal words sends over the pipe,
    # as the reader sees it (one line per echo, the format of the printf for each
    # literal); None when the upstream is not such a literal echo / printf (a flag,
    # a dynamic word, a subshell marker, a foreign format).
    toks = shell_tokens.tokenize(prev)
    if toks is None:
        return None
    rest, sure = command_head.skip(toks)
    if not sure or not rest:
        return None
    head = rest[0].rsplit("/", 1)[-1]
    args = rest[1:]
    if head == "echo":
        if any(a.startswith("-") for a in args):
            return None
        if not args or not all(_plain_word(a) for a in args):
            return None
        return " ".join(args) + "\n"
    if head == "printf":
        fmt = None
        lits = []
        for a in args:
            if fmt is None:
                if a.startswith("-"):
                    continue
                if not _plain_word(a):
                    return None
                fmt = a
                continue
            if not _plain_word(a):
                return None
            lits.append(a)
        if fmt is None:
            return None
        if re.fullmatch(r"(?:%s|\\n|\s)+", fmt) is None:
            return None
        out = []
        k = 0
        i = 0
        while i < len(fmt):
            if fmt.startswith("%s", i):
                if k >= len(lits):
                    return None
                out.append(lits[k])
                k += 1
                i += 2
            elif fmt.startswith("\\n", i):
                out.append("\n")
                i += 2
            else:
                out.append(" ")
                i += 1
        if k != len(lits):
            return None
        return "".join(out) or None
    return None


def _loop_words(segs, i):
    # the quoted words of `for V in W...; do echo "$V"; done` when the
    # whole output goes to the pipe into segment i: the body prints only $V (echo, or
    # printf with a literal pass-through format) and the words are literals. None
    # otherwise.
    if i < 3:
        return None
    if shell_tokens.tokenize(segs[i - 1]) != ["done"]:
        return None
    body = shell_tokens.tokenize(segs[i - 2])
    if body is None or len(body) < 2 or body[0] != "do":
        return None
    body = body[1:]
    if body[0] == "echo":
        uses = body[1:]
    elif body[0] == "printf":
        if len(body) < 3:
            return None
        if not _plain_word(body[1]) or "$" in body[1] \
                or re.fullmatch(r"(?:%s|\\n|\s)+", body[1]) is None:
            return None
        uses = body[2:]
    else:
        return None
    if len(uses) != 1:
        return None
    m = re.fullmatch(r"\$\{?([A-Za-z_][A-Za-z0-9_]*)\}?", uses[0])
    if m is None:
        return None
    head = shell_tokens.tokenize(segs[i - 3])
    if head is None or len(head) < 4 or head[0] != "for":
        return None
    if head[1] != m.group(1) or head[2] != "in":
        return None
    words = []
    for w in head[3:]:
        if not _plain_word(w):
            return None
        words.append(w)
    return words if words else None


def _judge_piped(text, kind, config, depth, max_depth):
    # the piped text is code for the reader: shell text is judged as
    # commands (like a -c body), python text as inline code (like a -c / - body).
    if kind == "shell":
        return judge_command(text, config, depth + 1, max_depth)
    return judge_code(text, config, depth + 1, max_depth, ("python3",))


def _resolved_var_names(text):
    # the names safe_vars.resolve() reads in the text, with that module's own
    # binding rule: a single top-level plain literal assignment and every other occurrence a
    # $NAME or ${NAME} use. The set is the only oracle of the unquoted heredoc gate; at the
    # least doubt a name is not in the set.
    names = set()
    try:
        masked, closed = quote_mask.scan(text)
        if not closed:
            return names
        if safe_vars.EVAL_SOURCE_RE.search(text) is not None:
            return names
        if safe_vars.DOT_HEAD_RE.search(masked) is not None:
            return names
        regions = safe_vars._body_regions(text)
        quotes = safe_vars._single_quote_spans(text)

        def in_body(i):
            return any(a <= i < b for a, b in regions)

        def in_single(i):
            return any(a <= i < b for a, b in quotes)

        depth = safe_vars._depth_after(masked)
        candidates = []
        for s in safe_vars._command_starts(masked):
            m = safe_vars.ASSIGN_RE.match(masked, s)
            if m is None:
                continue
            if s > 0 and depth[s - 1] != 0:
                continue
            if safe_vars.ALONE_RE.match(masked, m.end()) is None:
                continue
            candidates.append((m.group(1), m.start(1), m.end(2)))
        by_name = {}
        for nm, a, e in candidates:
            by_name.setdefault(nm, []).append((a, e))
        for nm, entries in by_name.items():
            if len(entries) != 1:
                continue
            a_start, a_end = entries[0]
            token = re.compile(r"(?<![A-Za-z0-9_])" + re.escape(nm) + r"(?![A-Za-z0-9_])")
            blocked = False
            for m in token.finditer(text):
                p = m.start()
                if a_start <= p < a_end:
                    continue
                if in_body(p):
                    continue
                if in_single(p):
                    blocked = True
                    break
                before = text[p - 1] if p > 0 else ""
                if before == "$":
                    continue
                if text[p - 2:p] == "${" and text[m.end():m.end() + 1] == "}":
                    continue
                blocked = True
                break
            if not blocked:
                names.add(nm)
    except Exception:
        pass
    return names


def _body_dollar_unread(body, text):
    # True when an unquoted heredoc body keeps a $NAME the shell would expand
    # for the reader and that the resolver did not read in the command. A $ in single quotes
    # is data for the reader; a lone $ (not a $NAME) is an expansion of unknown width.
    names = _resolved_var_names(text)
    i = 0
    n = len(body)
    while i < n:
        c = body[i]
        if c == "'":
            j = body.find("'", i + 1)
            if j == -1:
                return True
            i = j + 1
            continue
        if c == "\\" and i + 1 < n:
            i += 2
            continue
        if c != "$":
            i += 1
            continue
        m = re.match(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", body[i:])
        if m is None:
            m = re.match(r"\$([A-Za-z_][A-Za-z0-9_]*)", body[i:])
            if m is None:
                return True
        if m.group(1) not in names:
            return True
        i += m.end()
    return False


def merge(results):
    targets = []
    first_unknown_reason = None
    first_write_reason = None
    has_unknown = False

    for r in results:
        for t in r.get("targets", []):
            if t != "<unknown>" and t not in targets:
                targets.append(t)
        if r.get("verdict") == "unknown" and first_unknown_reason is None:
            first_unknown_reason = r.get("reason")
            has_unknown = True
        if r.get("verdict") == "write" and first_write_reason is None:
            first_write_reason = r.get("reason")

    if has_unknown:
        return {
            "verdict": "unknown",
            "targets": targets + ["<unknown>"],
            "reason": first_unknown_reason,
        }
    if targets:
        return {
            "verdict": "write",
            "targets": targets,
            "reason": first_write_reason,
        }
    return {"verdict": "free", "targets": [], "reason": "free"}


def judge_code(code, config, depth=0, max_depth=4, words=()):
    exts = list(config.get("code_extensions", []))
    # the script path run by Python and a temporary file suffix are not targets (python_literal_roles.py).
    # Missing or broken module: nothing is spared, the old stricter verdict stands.
    try:
        import python_literal_roles
        benign = python_literal_roles.benign_literals(code)
    except Exception:
        benign = set()
    literals = [m.group(2) for m in LITERAL.finditer(code) if m.group(2) not in benign]
    head = os.path.basename(next((w for w in words if "=" not in w), ""))
    is_python = head.startswith("python")
    # a sink bound to another name keeps the old verdict; the proven
    # early return is skipped for it.
    aliased = _write_alias(code) if is_python else False
    written = python_write_proof.written_paths(code) if (is_python and not aliased) else None
    if written is not None:
        hits = [(p, shell_tokens.classify_target(p, exts)) for p in written]
        return merge([{"verdict": "write" if k == "code" else "unknown", "targets": [p], "reason": "python writes a code file"}
                      for p, k in hits if k] or [{"verdict": "free", "targets": [], "reason": "free"}])
    # exec/eval of built or read code, compile, a non-literal __import__, a builtins getattr, runpy/importlib loaders or an alias of them make the non-write proof impossible: unknown.
    if is_python:
        dyn = python_write_proof.dynamic_exec(code)
        if dyn is not None:
            return {"verdict": "unknown", "targets": ["<unknown>"], "reason": dyn}

    # a literal exec/eval is itself judged as code, bounded.
    exec_results = []
    if is_python:
        for lit in python_write_proof.exec_literals(code):
            if depth >= max_depth:
                exec_results.append({"verdict": "unknown", "targets": ["<unknown>"], "reason": "python runs code too deep"})
            else:
                exec_results.append(judge_code(lit, config, depth + 1, max_depth, ("python3",)))

    if not is_python:
        # non-python inline code (node/js) keeps the old sign-based literal scan.
        results = list(exec_results)
        # the words keep their positions: the arguments of a -c / - code
        # start after the code word, and sys.argv[i] is read from them.
        results += list(inline_writes.write_targets(code, list(words), exts) or [])
        if any(sign in code for sign in WRITE_SIGNS):
            for s in literals:
                if shell_tokens.classify_target(s, exts) == "code":
                    results.append({"verdict": "write", "targets": [s], "reason": "inline code"})
        if any(sign in code for sign in RUN_SIGNS):
            run_calls = list(RUN_CALL.finditer(code))
            run_literal_spans = []
            for m in run_calls:
                results.append(judge_command(m.group(2), config, depth + 1, max_depth))
                run_literal_spans.append((m.start(2), m.end(2)))
            for m_lit in LITERAL.finditer(code):
                s = m_lit.group(2)
                is_run_arg = any(m_lit.start() <= cs and m_lit.end() >= ce for cs, ce in run_literal_spans)
                if is_run_arg or s in benign:
                    continue
                if shell_tokens.classify_target(s, exts) == "code":
                    results.append({"verdict": "write", "targets": [s], "reason": "inline code"})
        return merge(results)

    # loading a local module by its path to print its verdicts is a read (python_file_import.py), but never over a write already found.
    if not exec_results and python_read_proof.read_proven(python_file_import.rewrite(code)) and not python_write_proof.hazard(code):
        return {"verdict": "free", "targets": [], "reason": "free"}

    # a refusal is lifted only on a proven form. The previous verdict is
    # computed first; the write-sink whitelist re-examines the refused bodies and the
    # standing verdict stands in every case the whitelist does not prove.
    unproven = [{"verdict": "write", "targets": [s], "reason": "unproven python names a code file"}
                for s in literals if shell_tokens.classify_target(s, exts) == "code"]
    results = list(exec_results)
    # the words keep their positions: the arguments of a -c / - code
    # start after the code word, and sys.argv[i] is read from them.
    results += list(inline_writes.write_targets(code, list(words), exts) or [])

    if any(sign in code for sign in WRITE_SIGNS):
        for s in literals:
            if shell_tokens.classify_target(s, exts) == "code":
                results.append(
                    {"verdict": "write", "targets": [s], "reason": "inline code"}
                )

    if any(sign in code for sign in RUN_SIGNS):
        # the regex also matches quoted data inside string literals; for a Python body the
        # AST scan in _subprocess_sinks is authoritative, so the regex findings only feed
        # the previous verdict, never the whitelist short-circuit.
        run_calls = list(RUN_CALL.finditer(code))
        run_literal_spans = []
        for m in run_calls:
            results.append(judge_command(m.group(2), config, depth + 1, max_depth))
            run_literal_spans.append((m.start(2), m.end(2)))

        for m_lit in LITERAL.finditer(code):
            s = m_lit.group(2)
            lit_start = m_lit.start()
            lit_end = m_lit.end()
            is_run_arg = any(
                lit_start <= cmd_start and lit_end >= cmd_end
                for cmd_start, cmd_end in run_literal_spans
            )
            if is_run_arg or s in benign:
                continue
            if shell_tokens.classify_target(s, exts) == "code":
                results.append(
                    {"verdict": "write", "targets": [s], "reason": "inline code"}
                )

    if unproven and not any(r.get("verdict") == "write" for r in results):
        results += unproven
    # the code a body runs through an interpreter -c (sys.executable
    # or an interpreter by plain name) is judged like sys.executable -c; the scan
    # feeds the standing verdict before its free return, so a body with no other
    # sign cannot escape it.
    sub_results, sub_unknown, sub_reads = ([], False, 0)
    if not aliased:
        sub_results, sub_unknown, sub_reads = _subprocess_sinks(code, config, depth, max_depth)
        results += list(sub_results)
    old = merge(results)
    if old["verdict"] == "free":
        return {"verdict": "free", "targets": [], "reason": "free"}
    # a sink bound to another name (f = open, w = Path(p).write_text, from os import
    # rename as r, a module alias, getattr) is not in the whitelist: the whole body
    # keeps its previous verdict.
    if aliased:
        return old
    # the words keep their positions for the sys.argv[i] read.
    return _sink_whitelist(code, config, depth, max_depth, exts, exec_results,
                         sub_results, sub_unknown, sub_reads, list(words))


def judge_command(text, config, depth=0, max_depth=4):
    if depth > max_depth:
        return {
            "verdict": "unknown",
            "targets": ["<unknown>"],
            "reason": "nesting too deep",
        }

    # R=$PWD/x.md; printf x >> $R was refused; a certain assignment is resolved (shell_vars.py).
    # cd x && f=a.md && sed -i y $f was refused; a NAME=value between two && is resolved in its chain (chain_vars.py).
    resolved = shell_vars.resolve(chain_vars.resolve_chained(text))
    sp = shell_split.split_command(resolved)
    if sp["error"] is not None:
        return {
            "verdict": "unknown",
            "targets": ["<unknown>"],
            "reason": sp["error"],
        }

    # the whitelist (restore_rules.py) alone sees a further resolved text, where a
    # variable bound earlier in the same command to a literal path is resolved (safe_vars.py):
    # a substitution never adds a separator, so the segments stay aligned; at the least doubt they do not.
    wl_segs = None
    try:
        rtext = safe_vars.resolve(resolved)
        if rtext != resolved:
            rsp = shell_split.split_command(rtext)
            if rsp["error"] is None and len(rsp["segments"]) == len(sp["segments"]):
                wl_segs = rsp["segments"]
    except Exception:
        wl_segs = None

    # a variable bound on an earlier binding (D=$S/x after S=/tmp/x) is read
    # only when the resolver is applied again on its own output; a substitution never adds a
    # separator, so the segments and the heredoc bodies stay aligned; at the least doubt
    # they do not and the previous verdict stands.
    deep_text = resolved
    deep_segs = None
    deep_bodies = None
    try:
        for _ in range(4):
            d2 = safe_vars.resolve(deep_text)
            if d2 == deep_text:
                break
            deep_text = d2
        if deep_text != resolved:
            dsp = shell_split.split_command(deep_text)
            if (dsp["error"] is None and len(dsp["segments"]) == len(sp["segments"])
                    and len(dsp["bodies"]) == len(sp["bodies"])
                    and all(x["body"] == y["body"] and x["delimiter"] == y["delimiter"]
                            for x, y in zip(dsp["bodies"], sp["bodies"]))):
                deep_segs = dsp["segments"]
                deep_bodies = dsp["bodies"]
    except Exception:
        deep_segs = None
        deep_bodies = None

    results = []

    for i, seg in enumerate(sp["segments"]):
        r = shell_targets.judge_segment(seg, config)
        # a name rm cannot place is a write the guard cannot place,
        # like a truncate of the same name; a literal name keeps its previous
        # verdict, the protected-path controls seeing the journals.
        if r.get("head") == "rm" and r.get("verdict") != "unknown":
            toks = shell_tokens.tokenize(seg)
            if toks is not None:
                toks2, sure = command_head.skip(toks)
                if sure:
                    exts = list(config.get("code_extensions", []))
                    for a in toks2[1:]:
                        if not a.startswith("-") and shell_tokens.classify_target(a, exts) == "unknown":
                            r = {"verdict": "unknown", "targets": ["<unknown>"],
                                 "reason": "rm", "head": "rm", "nested": r.get("nested")}
                            break
        # a git restore/checkout from a git object and a same-extension cp/mv into a
        # temporary folder write no code (restore_rules.py); the rest of the command is judged as before.
        if r.get("reason") in ("copy", "git") and restore_rules.spare(wl_segs[i] if wl_segs else seg, config):
            r = {"verdict": "free", "targets": [], "reason": "free", "head": r.get("head", ""), "nested": None}
        # a code file moved or copied from a temp directory into a
        # directory destination is judged as a code write (see _copy_dir_dest);
        # the previous verdict stands at the least doubt.
        if r.get("head") in ("cp", "mv") and r.get("verdict") in ("free", "write"):
            rseg = wl_segs[i] if wl_segs is not None and i < len(wl_segs) else None
            cdir = _copy_dir_dest(seg, config, rseg)
            if cdir is not None:
                r = dict(r)
                r.update(cdir)
        # git stash [push] [-q] [-- paths] restores the paths to the last commit:
        # no code write; the quiet pop/apply is proven the same way.
        if r.get("head") == "git" and _stash_proven(seg):
            r = {"verdict": "free", "targets": [], "reason": "free", "head": r.get("head", ""), "nested": None}
        # a git archive unpacked into a temporary folder writes no code; the
        # folder is read in the resolved text and normalized before the comparison.
        if (r.get("verdict") == "unknown" and r.get("reason") == "archive" and r.get("head") == "tar" and i > 0):
            tseg = deep_segs[i] if deep_segs is not None and i < len(deep_segs) else seg
            if _temp_unpack(sp["segments"][i - 1], tseg):
                r = {"verdict": "free", "targets": [], "reason": "free", "head": r.get("head", ""), "nested": None}
        # a redirection target that ends with an output file name is
        # not a code write, even when the name is also a code extension.
        if r.get("verdict") == "write" and r.get("reason") == "redirection" and r.get("targets") \
                and all(_output_name(t) for t in r["targets"]):
            r = dict(r)
            r["verdict"] = "nested" if r.get("nested") is not None else "free"
            r["targets"] = []
        # a redirection target held in a variable the chain set to a literal
        # is read with the safe_vars text (the only resolver): a code file it names is a
        # write, an absolute non-code file is free, and a relative non-code file (or one
        # left unreadable) keeps the previous verdict. Only redirections are read this way.
        if (r.get("verdict") == "unknown" and r.get("reason") == "redirection" and wl_segs is not None
                and i < len(wl_segs) and wl_segs[i] != seg):
            dests = _redir_dests(wl_segs[i])
            exts = list(config.get("code_extensions", []))
            if dests is not None and dests and all(not re.search(r"[$`]", d) for d in dests):
                cats = [shell_tokens.classify_target(d, exts) for d in dests]
                code = [d for d, c in zip(dests, cats) if c == "code"]
                if code:
                    r = dict(r)
                    r["verdict"] = "write"
                    r["targets"] = code
                elif all(c is None and d.startswith("/") for d, c in zip(dests, cats)):
                    r = {"verdict": "free", "targets": [], "reason": "free", "head": r.get("head", ""), "nested": r.get("nested")}
        results.append(r)
        nested = r.get("nested")
        if nested is not None:
            kind = nested.get("kind")
            nested_text = nested.get("text")
            if kind == "code" and "$" in nested_text and not re.search(r"-c '[^']*'(\s|$)", seg) and re.search(r"(?<!\\)\$[\w{(]", seg):
                # the certain variables of the chain (safe_vars, the only
                # resolver) are read into the code first, and $HOME is the home folder:
                # the code is judged with those values, not "code expanded by the
                # shell"; a variable left unreadable keeps the previous verdict.
                code_exp = nested_text
                if wl_segs is not None and i < len(wl_segs) and wl_segs[i] != seg:
                    n2 = shell_targets.judge_segment(wl_segs[i], config).get("nested")
                    if n2 and n2.get("kind") == "code":
                        code_exp = n2["text"]
                if "$" in code_exp:
                    code_exp = re.sub(r"\$HOME(?![A-Za-z0-9_])", os.path.expanduser("~"), code_exp)
                if "$" in code_exp or "`" in code_exp:
                    results.append({"verdict": "unknown", "targets": ["<unknown>"], "reason": "code expanded by the shell"})
                else:
                    # the command words are read in the resolved text so the
                    # arguments of a -c / - code are read through the certain variables.
                    dw = deep_segs[i] if deep_segs is not None and i < len(deep_segs) else seg
                    results.append(judge_code(code_exp, config, depth + 1, max_depth, shell_tokens.tokenize(dw) or []))
            elif kind == "code":
                dw = deep_segs[i] if deep_segs is not None and i < len(deep_segs) else seg
                results.append(judge_code(nested_text, config, depth + 1, max_depth, shell_tokens.tokenize(dw) or []))
            elif kind == "command":
                results.append(judge_command(nested_text, config, depth + 1, max_depth))

    # the text piped into an interpreter that reads its input (bash, sh,
    # zsh with no argument or only -s; python, python3 with no argument or only -) is
    # code for that interpreter: the literals of an echo / printf, or the quoted words
    # of a for loop whose whole output is piped, are judged like a -c / - body; a
    # script or a -c reads data and stays as before; any other upstream is unknown.
    try:
        rest_h, _bodies_h = shell_quotes.extract_heredocs(resolved)
        rest_h = shell_quotes.strip_comments(rest_h)
        outer_h, _inners_h = shell_split.extract_subshells(rest_h)
        seps = _segment_seps(outer_h)
    except Exception:
        seps = []
    for i, seg in enumerate(sp["segments"]):
        kind = _stdin_interp(seg)
        if kind is None or i == 0 or i >= len(seps) or seps[i - 1][1] != "|":
            continue
        prev = sp["segments"][i - 1]
        # a pipe inside a loop body (do echo/printf ... | interp): the words are
        # judged by the loop rule that owns the body; the old verdict stands here.
        ptoks = shell_tokens.tokenize(prev)
        if ptoks and ptoks[0] == "do":
            continue
        text = _piped_text(prev)
        if text is not None:
            results.append(_judge_piped(text, kind, config, depth, max_depth))
            continue
        words = _loop_words(sp["segments"], i)
        if words is not None:
            for w in words:
                results.append(_judge_piped(w, kind, config, depth, max_depth))
            continue
        results.append({"verdict": "unknown", "targets": ["<unknown>"],
                        "reason": "piped text runs code the guard cannot read"})

    for bi, b in enumerate(sp["bodies"]):
        segs = shell_split.split_segments(b["line"])
        owner = next((s for s in segs if "<<" in s), b["line"])
        head = shell_targets.judge_segment(owner, config)["head"]
        body_txt = b["body"]
        owner_txt = owner
        if deep_bodies is not None and bi < len(deep_bodies):
            dsegs = shell_split.split_segments(deep_bodies[bi]["line"])
            owner_txt = next((s for s in dsegs if "<<" in s), deep_bodies[bi]["line"])
            body_txt = deep_bodies[bi]["body"]
        if not re.search(r"<<-?\s*['\"\\]" + re.escape(b["delimiter"]), b["line"]):
            # the shell expands an unquoted heredoc body before its owner reads it.
            results += [judge_command(s, config, depth + 1, max_depth) for s in shell_split.extract_subshells(b["body"])[1]]
            # the shell runs a $(...) and an unescaped backtick of the body
            # before any reader: for every reader the previous verdict stands. A reader that
            # runs code also keeps it when the body keeps a $NAME the resolver did not read.
            if (_unquoted_expands(b["body"])
                    or (head in shell_targets.CODE_FLAGS
                        and _body_dollar_unread(b["body"], deep_text))):
                results.append({"verdict": "unknown", "targets": ["<unknown>"], "reason": "unquoted heredoc expands"})
                continue
        if head in shell_targets.CODE_FLAGS:
            results.append(judge_code(body_txt, config, depth + 1, max_depth, shell_tokens.tokenize(owner_txt) or []))
        elif head in shell_targets.SHELLS:
            results.append(judge_command(body_txt, config, depth + 1, max_depth))
        # source /dev/stdin, sed -f - or awk -f - run the heredoc body as a program nobody here can read.
        elif head in ("source", ".") or re.search(r"(?<!\S)(-f\s*-|--file[=\s]-|/dev/stdin|/dev/fd/0|/proc/self/fd/0)(?!\S)", owner):
            results.append({"verdict": "unknown", "targets": ["<unknown>"], "reason": "heredoc read as a program"})

    return merge(results)


CFG = {"code_extensions": [".py", ".sh"], "delegate_tools": ["deleg-tool"]}


def J(t):
    r = judge_command(t, CFG)
    return (r["verdict"], r["targets"])


U = ("unknown", ["<unknown>"])
F = ("free", [])
H1 = "python3 - <<'EOF'\nprint('<path>')\nEOF"
H2 = "python3 - <<'EOF'\nopen('w.py','w').write('x')\nEOF"
H3 = "bash <<EOF\ntee b.sh\nEOF"
H4 = "cat > /tmp/s.py <<EOF\nprint(1)\nEOF"
H5 = "cat <<EOF\nx > y.py\nEOF"


def _test1():
    expected = [
        ("write", ["/tmp/t.py"]),
        F,
        ("write", ["a.py"]),
        U,
        U,
        "unbalanced subshell",
    ]
    obtained = [
        J("printf x | tee /tmp/t.py # deleg-tool"),
        J("cat f; ls | grep x"),
        J('echo "$(tee a.py)" && ls'),
        J("echo 'abc"),
        J("echo $(a"),
        judge_command("echo $(a", CFG)["reason"],
    ]
    return obtained, expected


def _test2():
    expected = [
        F,
        ("write", ["w.py"]),
        ("write", ["b.sh"]),
        ("write", ["/tmp/s.py"]),
        F,
    ]
    obtained = [J(H1), J(H2), J(H3), J(H4), J(H5)]
    return obtained, expected


def _test3():
    expected = [
        ("write", ["x.py"]),
        F,
        ("write", ["b/a.py"]),
        ("write", ["c.sh"]),
        ("write", ["e.py"]),
        F,
        ("write", ["g.py"]),
        ("write", ["out.py"]),
    ]
    obtained = [
        J("python3 -c \"open('x.py','w')\""),
        J("python3 -c \"import json; json.dump(1, open('d.json','w'))\""),
        J("bash -c 'cp a.py b/'"),
        J("python3 -c \"import os; os.system('tee c.sh')\""),
        J("eval 'tee e.py'"),
        J("rm -rf build && cp -r src dst"),
        J("perl -pi -e 's/a/b/' g.py"),
        J('python3 -c \'import subprocess;subprocess.run(["tee","out.py"])\''),
    ]
    return obtained, expected


def _test4():
    expected = (
        ["n.js"],
        "free",
        "free",
        {"verdict": "unknown", "targets": ["<unknown>"], "reason": "nesting too deep"},
        ("write", ["z.py"]),
        {"verdict": "free", "targets": [], "reason": "free"},
    )
    obtained = (
        judge_code(
            "fs.writeFileSync('n.js', s)",
            {"code_extensions": [".js"], "delegate_tools": []},
        )["targets"],
        judge_code("print('a.py')", CFG)["verdict"],
        judge_code("import subprocess; print('it is \"quoted')", CFG)["verdict"],
        judge_command("eval eval eval tee z.py", CFG, 0, 1),
        J("eval eval eval tee z.py"),
        merge([]),
    )
    return obtained, expected


def _test5():
    p_notice = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True,
    )
    p_usage = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True,
        text=True,
    )
    expected = (
        F,
        0,
        True,
        2,
        "usage: shell_rules.py --notice | --autotest\n",
    )
    obtained = (
        J(""),
        p_notice.returncode,
        p_notice.stdout.startswith("NAME      shell_rules.py"),
        p_usage.returncode,
        p_usage.stdout,
    )
    return obtained, expected


def _test6():
    H = "python3 - <<'EOF'\n{}\nEOF"
    expected = [
        U,
        U,
        U,
        F,
        U,
        U,
        U,
        F,
        F,
        F,
        ("write", ["out.py"]),
        ("write", ["b.py"]),
        F,
        U,
        U,
        U,
        U,
        U,
        U,
        U,
        U,
        ("write", ["x.py"]),
    ]
    obtained = [
        J(H.format("open(os.environ['D'], 'w').write('x')")),
        J(H.format("os.rename('a.txt', os.environ['D'])")),
        J(H.format("shutil.copy('a.txt', os.environ.get('D'))")),
        J(H.format("print(os.environ.get('HOME'))")),
        J("python3 -c \"exec(open('a.txt').read())\""),
        J("python3 -c \"exec('op'+'en(...)')\""),  # lang-ok: en is a fragment of open, not French
        J("python3 -c \"eval(compile(open('a.txt').read(), 'x', 'exec'))\""),
        J("python3 -c \"import os; print(os.environ['HOME'])\""),
        J("sh -c 'ls -la'"),  # lang-ok: la is the ls -la flag, not French
        J("bash -c 'git status --short'"),
        J("git mv notes.md out.py"),
        J("git mv a.py b.py"),
        J("git mv notes.md out.md"),
        J(H.format("from os import environ\nopen(environ['D'], 'w')")),
        J(H.format("import os as o\nopen(o.environ['D'], 'w')")),
        J(H.format("p = os.environ['D']\nopen(p, 'w')")),
        J(H.format("import sys\nopen(sys.argv[1], 'w')")),
        J(H.format("import builtins\nbuiltins.exec(open('a.txt').read())")),
        J(H.format("e = eval; e('print(1)')")),
        J(H.format("import runpy\nrunpy.run_path('x.py')")),
        J(H.format("exec('open(x, \"w\")')")),
        J(H.format("import builtins\nbuiltins.eval('open(\"x.py\", \"w\")')")),
    ]
    return obtained, expected


def _test7():
    H = "python3 - <<'EOF'\n{}\nEOF"
    expected = [
        F,
        F,
        F,
        F,
        F,
        F,
        U,
        U,
        F,
        F,
        F,
        ("write", ["x.py"]),
        U,
        U,
    ]
    obtained = [
        J(H.format("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, 'a.py'), 'w')")),
        J(H.format("import tempfile, os\nwith tempfile.TemporaryDirectory() as d:\n    open(os.path.join(d, 'a.py'), 'w')")),
        J(H.format("import tempfile\nfd, p = tempfile.mkstemp(suffix='.py')\nopen(p, 'w')")),
        J(H.format("import tempfile, os\nd = tempfile.mkdtemp()\np = os.path.join(d, 'a.py')\nopen(p, 'w')")),
        J(H.format("import tempfile\nfrom pathlib import Path\nd = tempfile.mkdtemp()\n(Path(d) / 'a.py').write_text('x')")),
        J("git add $(for f in a.py b.py; do echo --livrer public/bin/$f=x; done)"),
        J(H.format("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, '..', 'x.py'), 'w')")),
        J(H.format("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, '/tmp/x.py'), 'w')")),
        J(H.format("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nopen(f.name, 'w')")),
        J(H.format("import tempfile, os\nwith tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:\n    open(f.name, 'w')")),
        J(H.format("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nos.unlink(f.name)")),
        J(H.format("import tempfile, shutil\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nshutil.copy(f.name, 'x.py')")),
        J(H.format("import tempfile, os\nf = 'x.py'\nopen(f.name, 'w')")),
        J(H.format("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nf = 'x.py'\nopen(f.name, 'w')")),
    ]
    return obtained, expected


def _test8():
    # a git restore/checkout from a git object, and a cp/mv of a code file into a
    # temporary folder keeping the same extension, are free (restore_rules.py); the rest is judged as before.
    expected = [
        F,
        F,
        F,
        F,
        ("write", ["/tmp/b.py"]),
        ("write", ["bin/a.py"]),
        ("write", ["x.py"]),
        ("write", ["b.py"]),
        ("write", ["/tmp/../opt/x/bin/a.py"]),
        F,
        F,
    ]
    obtained = [
        J("git restore --source=n1 --worktree -- public/examples/"),
        J("git checkout -- public/bin/a.py"),
        J("B=/private/tmp/w/s && mkdir -p $B && cp bin/a.py $B/ && mv bin/b.py $B/"),
        J("cp bin/a.py /tmp/w/a.py"),
        J("cp notes.txt /tmp/b.py"),
        J("cp /tmp/a.py bin/a.py"),
        J("git restore --source=n1 -- x.py && echo 1 >> x.py"),
        J("git show n1:a.py | tee b.py"),
        J("cp /tmp/a.py /tmp/../opt/x/bin/a.py"),
        J("git checkout n1 -- bin/"),
        J('B=/tmp/w; cp a.py "$B/a.py"'),
    ]
    return obtained, expected


def _test9():
    # a literal of inline Python naming a code file is a write target only
    # through a write sink; code run by sys.executable -c is judged as code.
    cfg = {"code_extensions": [".py"], "delegate_tools": []}
    cases = [
        ("python3 -c \"import subprocess,sys; subprocess.run([sys.executable,'bin/tool.py','--x'],capture_output=True)\"", "free"),
        ("python3 -c \"s=open('o.txt').read(); open('o.txt','w').write(s.replace('a > A','a > A.py'))\"", "free"),
        ("python3 -c \"L=['echo 1 > x.py','cp a.txt b.py']; print(len(L))\"", "free"),
        ("python3 -c \"import json; print('delegate.py' in str(json.load(open('a.json'))))\"", "free"),
        ("python3 -c \"p='k.md'; t=open(p).read(); open(p,'w').write(t+'lint_cmd.py')\"", "free"),
        ("python3 -c \"n='x.py'; open(n,'w').write('1')\"", "write"),
        ("python3 -c \"import subprocess,sys; subprocess.run([sys.executable,'-c','open(\\\"x.py\\\",\\\"w\\\")'])\"", "write"),
        ("python3 -c \"import subprocess; subprocess.run(['cp','a.txt','b.py'])\"", "write"),
        ("python3 -c \"import json; L=['a.py']; open(L[0],'w')\"", "write_or_unknown"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        if want == "write_or_unknown" and v in ("write", "unknown"):
            v = "write_or_unknown"
        obtained.append(v)
    return obtained, expected


def _test10():
    # an interpreter by plain name (python, python3, a path) started
    # with -c is judged like sys.executable -c; a non-literal code argument keeps
    # the previous verdict.
    cfg = {"code_extensions": [".py"], "delegate_tools": []}
    cases = [
        ("python3 - <<'EOF'\nimport subprocess\nsubprocess.run(['python3','-c',\"open('y.py','w')\"])\nEOF", "write"),
        ("python3 -c \"import subprocess; subprocess.run(['python','-c','open(\\\"x.py\\\",\\\"w\\\")'])\"", "write"),
        ("python3 -c \"import subprocess; subprocess.run(['python3','-c','print(1)'])\"", "free"),
        ("python3 -c \"import subprocess; subprocess.run(['python3','-c',C])\"", "write_or_unknown"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        if want == "write_or_unknown" and v in ("write", "unknown"):
            v = "write_or_unknown"
        obtained.append(v)
    return obtained, expected


def _test11():
    # the literal suffix of a redirection target decides: a variable
    # folder with a literal non-code file name is free; a variable the chain set to
    # a literal is resolved first (safe_vars, the only resolver); an unreadable
    # target keeps the previous verdict; $HOME of inline code is the home folder.
    cfg = {"code_extensions": [".py", ".txt"], "delegate_tools": []}
    cases = [
        ("S=/tmp/x; aws p get > $S/b.json 2>$S/b.err", "free"),
        ("T=$(mktemp -d) && python3 a.py init > $T.init 2>&1", "free"),
        ("S=/tmp/x/c.txt; python3 r/o.txt > $S 2>&1", "free"),
        ("S=bin; echo 1 > $S/x.py", "write"),
        ("T=$(mktemp -d); echo 1 > $T/x.py", "write_or_unknown"),
        ("X=$(cat f); echo 1 > $X", "unknown"),
        ("echo 1 > $X$Y", "unknown"),
        ("S=/a/b/c.py; printf x > $S", "write"),
        ("python3 -c \"import sys;sys.path.insert(0,'$HOME/x');print(1)\"", "free"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        if want == "write_or_unknown" and v in ("write", "unknown"):
            v = "write_or_unknown"
        obtained.append(v)
    return obtained, expected


def _test12():
    # git stash [push] [-q] [-- paths] is a restore (free), the quiet
    # pop/apply too; a git archive unpacked into a temporary folder is free; a write to
    # sys.argv of a - / -c code is judged by the real argument; a plain pop, a non-temp
    # folder, a .. that leaves the temporary zone, an unquoted heredoc body the shell runs
    # ($( ... ) or a backtick) and an argv word the resolver did not read keep the
    # previous verdict.
    cfg = {"code_extensions": [".py"], "delegate_tools": []}
    cases = [
        ("git stash -q -- r/o.txt", "free"),
        ("D=/tmp/w; git -C /r archive HEAD public | tar -x -C $D/work", "free"),
        ("F=r/a.txt && python3 - \"$F\" <<'EOF'\nimport sys\nopen(sys.argv[1],'w').write('x')\nEOF", "free"),
        ("F=r/a.py && python3 - \"$F\" <<'EOF'\nimport sys\nopen(sys.argv[1],'w').write('x')\nEOF", "write"),
        ("git -C /r archive HEAD public | tar -x -C bin", "write_or_unknown"),
        ("git stash pop", "write_or_unknown"),
        ("git -C /r archive HEAD | tar -x -C /tmp/../opt/x", "write_or_unknown"),
        ("cat > /tmp/a.md <<EOF\n`cp x lib/a.py`\nEOF", "write_or_unknown"),
        ("python3 - <<EOF\nprint('$(cp x lib/a.py)')\nEOF", "write_or_unknown"),
        ("python3 -c \"import sys; open(sys.argv[1],'w')\" notes.md", "free"),
        ("F=a.txt; F=x.py; python3 - \"$F\" <<'EOF'\nimport sys\nopen(sys.argv[1],'w').write('x')\nEOF", "write_or_unknown"),
        ("python3 - \"$X\" <<'EOF'\nimport sys\nopen(sys.argv[1],'w').write('x')\nEOF", "write_or_unknown"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        if want == "write_or_unknown" and v in ("write", "unknown"):
            v = "write_or_unknown"
        obtained.append(v)
    return obtained, expected


def _test13():
    # literal text piped into an interpreter that reads its input is
    # judged as that interpreter's code (bash/sh/zsh bare or -s; python/python3 bare
    # or -): an echo/printf of literals, the quoted words of a for loop whose whole
    # output is piped; a script or a -c reads data; any other upstream is unknown.
    cfg = {"code_extensions": [".py", ".sh"], "delegate_tools": []}
    cases = [
        ('echo "echo 1 > x.py" | bash', "write"),
        ('echo "open(\'x.py\',\'w\')" | python3', "write"),
        ('for c in "echo 1 > x.py"; do echo "$c"; done | bash', "write"),
        ('for c in "cp a b.py"; do echo "$c"; done | sh -s', "write"),
        ('for c in "ls" "pwd"; do echo "$c"; done | bash', "free"),
        ('echo "print(1)" | python3', "free"),
        ('for c in "echo 1 > x.py"; do echo "$c"; done | wc -l', "free"),
        ('for c in "echo 1 > x.py"; do echo "$c"; done | python3 t.py', "free"),
        ('echo x | python3 -c "print(1)"', "free"),
        ('echo x | bash -c "ls"', "free"),
        ('printf "%s\\n" "echo 1 > x.py" | sh', "write"),
        ('echo $X | bash', "unknown"),
        ('cat f | bash', "unknown"),
        ('for c in "$X"; do echo "$c"; done | bash', "unknown"),
        ('echo "echo 1 > x.py" | bash -s', "write"),
        ('echo "echo 1 > x.py" | bash 2>&1', "write"),
        ('echo "echo 1 > x.py" | bash < f', "free"),
        # the short no-argument options and the python flags.
        ('echo "echo 1 > x.py" | bash -x', "write"),
        ('echo "echo 1 > x.py" | sh -xs', "write"),
        ('echo "echo 1 > x.py" | zsh -e -u -v -s', "write"),
        ('echo "echo 1 > x.py" | bash -s -- a b', "write"),
        ('echo "open(\'x.py\',\'w\')" | python3 -u -', "write"),
        ('echo "open(\'x.py\',\'w\')" | python -B -O -I', "write"),
        ('echo "ls" | bash -x', "free"),
        ('echo "print(1)" | python3 -u', "free"),
        ('echo x | bash -c "ls"', "free"),
        ('echo x | python3 t.py', "free"),
        ('echo x | bash -t', "free"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        obtained.append(v)
    return obtained, expected


def _test14():
    # a name rm cannot place is a write the guard cannot place,
    # like a truncate of the same name; a literal name keeps its previous verdict.
    cfg = {"code_extensions": [".py", ".sh"], "delegate_tools": []}
    cases = [
        ("rm $S", "unknown"),
        ("S=$(date); rm $S", "unknown"),
        ("B=$D; rm -rf $B", "unknown"),
        ("rm -rf $D/{a,b}", "unknown"),
        ("rm x.py", "free"),
        ("rm -rf /tmp/w", "free"),
        ("rm -f a.txt", "free"),
        ("rm -rf", "free"),
    ]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        obtained.append(v)
    return obtained, [w for _, w in cases]


def _test15():
    # a code file moved or copied from a temp directory into a directory
    # destination is a code write; a copy into a temporary folder stays free.
    cfg = {"code_extensions": [".py", ".sh"], "delegate_tools": []}
    cases = [
        ("mv /tmp/a.py bin/a.py", "write"),
        ("mv x/a.py y/a.py", "write"),
        ("cd bin; cp /tmp/w/a.py .", "write"),
        ("cp /tmp/a.py ..", "write"),
        ("cp /tmp/a.py bin", "write"),
        ("cp -R /tmp/w/pkg .", "write"),
        ("cp bin/a.py bin/b.py /tmp/w/", "free"),
        ("cp bin/a.py /tmp/w/", "free"),
        ("cp notes.md docs", "free"),
        ("mv /tmp/a.log logs/", "free"),
    ]
    expected = [w for _, w in cases]
    obtained = []
    for cmd, want in cases:
        v = judge_command(cmd, cfg)["verdict"]
        obtained.append(v)
    return obtained, expected


R02_CMD = r'''python3 -c "
import shlex
for s in ['echo x 2>&1 >out.py', 'cat f>>a.py', 'echo \$n \${x}/a.py', 'find . -name \"*.py\" -print0', 'x &>/dev/null', 'cmd >| f.py', 'a=1 b=\$(c) env X=2 tee -a lib/u.py', 'curl -oout.py http://h/x', 'sed -i.bak s/a/b/ f.py', 'echo a>&2']:
    l=shlex.shlex(s,posix=True,punctuation_chars=True); print(list(l))
"'''


def _test16():
    # the code quoted by R02 holds \$, an invalid escape: ast.parse used to
    # print a SyntaxWarning on every call. The case runs in a subprocess under
    # -W error::SyntaxWarning: the parse must stay silent and the verdict stay free.
    driver = ("import sys, shell_rules\n"
              "print(shell_rules.judge_command(sys.stdin.read(), shell_rules.CFG)['verdict'])")
    try:
        completed = subprocess.run(
            [sys.executable, "-W", "error::SyntaxWarning", "-c", driver],
            input=R02_CMD,
            capture_output=True,
            text=True,
            cwd=os.path.dirname(os.path.abspath(__file__)),
            timeout=60,
        )
        got = completed.stdout.strip() if completed.returncode == 0 else "exit " + str(completed.returncode)
    except Exception as exc:
        got = "exception " + repr(exc)
    return (got, "free")


def _autotest():
    tests = [
        ("test 1", _test1),
        ("test 2", _test2),
        ("test 3", _test3),
        ("test 4", _test4),
        ("test 5", _test5),
        ("test 6", _test6),
        ("test 7", _test7),
        ("test 8", _test8),
        ("test 9", _test9),
        ("test 10", _test10),
        ("test 11", _test11),
        ("test 12", _test12),
        ("test 13", _test13),
        ("test 14", _test14),
        ("test 15", _test15),
        ("test 16", _test16),
    ]
    all_pass = True
    for name, fn in tests:
        got, want = fn()
        ok = got == want
        print(f"{'PASS' if ok else 'FAIL'} {name}: want={want!r} got={got!r}")
        all_pass = all_pass and ok
    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) == 1:
        print("usage: shell_rules.py --notice | --autotest")
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: shell_rules.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "shell_rules", sys.argv[1:])
