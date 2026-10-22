#!/usr/bin/env python3
import ast
import os
import re
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_tokens
import python_literal_roles

UNKNOWN_REASON = "inline code writes to a path the guard cannot read"
WRITE_REASON = "inline code"


def _argv_words(words):
    # the argument words of a <python> - ARG ... or <python> -c CODE ARG ...
    # shell command, in the order the interpreter binds them to sys.argv[1:] ; None when
    # the proven form is not there. The trailing << operator and delimiter of a heredoc
    # owner are not arguments.
    if not words:
        return None
    head = os.path.basename(words[0] or "")
    if not head.startswith("python"):
        return None
    if len(words) > 1 and words[1] == "-":
        args = list(words[2:])
    elif len(words) > 2 and words[1] in ("-c", "--command"):
        args = list(words[3:])
    else:
        return None
    # the << operator and its delimiter, one token or two, are not arguments
    while args and (args[-1].startswith("<<")
                    or (len(args) >= 2 and args[-2].startswith("<<"))):
        args.pop()
        if len(args) >= 2 and args[-2].startswith("<<"):
            args.pop()
    return args


def _resolve(node, bindings, words=None):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return [node.value]
    if isinstance(node, ast.Name):
        return bindings.get(node.id)
    # sys.argv[i] of a <python> - ARG ... / -c CODE ARG ... command is the
    # i-th argument word (already read by the shell resolvers); an index the argument
    # list does not name, or a word the shell would still expand, stays unread.
    if isinstance(node, ast.Subscript):
        v = node.value
        if (isinstance(v, ast.Attribute) and v.attr == "argv"
                and isinstance(v.value, ast.Name) and v.value.id == "sys"):
            s = node.slice
            if isinstance(s, ast.Constant) and isinstance(s.value, int) and s.value >= 1:
                args = _argv_words(words)
                if args is not None and s.value - 1 < len(args):
                    w = args[s.value - 1]
                    if w and not re.search(r"[$`]", w):
                        return [w]
        return None
    if isinstance(node, ast.JoinedStr):
        if node.values and isinstance(node.values[-1], ast.FormattedValue):
            return None
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            elif isinstance(v, ast.FormattedValue):
                parts.append("")
            else:
                parts.append("")
        return ["".join(parts)]
    if isinstance(node, ast.BinOp):
        if isinstance(node.op, ast.Add):
            r = _resolve(node.right, bindings)
            if r is None:
                return None
            l = _resolve(node.left, bindings)
            if l is None:
                l = [""]
            return [a + b for a in l for b in r]
        if isinstance(node.op, ast.Div):
            r = _resolve(node.right, bindings)
            if r is None:
                return None
            l = _resolve(node.left, bindings)
            if l is None:
                l = [""]
            return [a + "/" + b if a != "" else b for a in l for b in r]
    if isinstance(node, ast.Call):
        func = node.func
        if (isinstance(func, ast.Name) and func.id == "Path") or \
           (isinstance(func, ast.Attribute) and func.attr == "Path"):
            if len(node.args) < 1:
                return None
            last_r = _resolve(node.args[-1], bindings)
            if last_r is None:
                return None
            result = [""]
            for arg in node.args:
                r = _resolve(arg, bindings)
                if r is None:
                    return None
                result = [a + "/" + b if a != "" else b for a in result for b in r]
            return result
        if isinstance(func, ast.Attribute) and func.attr in ("join", "joinpath"):
            if len(node.args) < 1:
                return None
            if func.attr == "joinpath":
                depart = _resolve(func.value, bindings)
                if depart is None:
                    depart = [""]
            else:
                depart = [""]
            last_r = _resolve(node.args[-1], bindings)
            if last_r is None:
                return None
            result = list(depart)
            for arg in node.args:
                r = _resolve(arg, bindings)
                if r is None:
                    return None
                result = [a + "/" + b if a != "" else b for a in result for b in r]
            return result
        if isinstance(func, ast.Attribute) and func.attr == "with_suffix":
            if len(node.args) < 1:
                return None
            return _resolve(node.args[0], bindings)
        if isinstance(func, ast.Attribute) and func.attr in ("expanduser", "abspath", "realpath"):
            # os.path.expanduser('~/x') and friends read as their one argument.
            if len(node.args) == 1:
                return _resolve(node.args[0], bindings)
            return None
    return None


def _open_sink(node, bindings):
    # one single source of truth for the open() sinks.
    # Returns (target, unreadable): target is the node to resolve (None on a read),
    # unreadable is True when the mode or the argument is not a readable literal
    # (the read cannot be proven: the previous verdict, unknown, stands).
    starred = any(isinstance(a, ast.Starred) for a in node.args)
    ddouble = any(kw.arg is None for kw in node.keywords)
    mode = None
    if len(node.args) >= 2:
        mode = node.args[1]
    else:
        for kw in node.keywords:
            if kw.arg == "mode":
                mode = kw.value
    if mode is not None:
        if isinstance(mode, ast.Constant) and isinstance(mode.value, str):
            if not any(c in mode.value for c in "wax+"):
                return None, False  # read mode proven
            return (node.args[0] if node.args
                    else next((kw.value for kw in node.keywords if kw.arg == "file"), None)), False
        return None, True  # non-literal mode: the read is not proven
    if starred or ddouble:
        return None, True  # open(*a) / open(**k): the mode is not read
    return None, False  # no mode: default read


def _iter_sinks(tree, bindings, temp, trusted, words=None):
    # walks the tree and yields a dict per write sink:
    # {"target": node to resolve or None, "unreadable": bool, "temp": bool}.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target = None
        unreadable = False

        # a. open(...)
        if isinstance(func, ast.Name) and func.id == "open":
            target, unreadable = _open_sink(node, bindings)
            if target is None:
                if unreadable:
                    yield {"target": None, "unreadable": True, "temp": False}
                continue

        # b. .write_text / .write_bytes / .touch
        elif isinstance(func, ast.Attribute) and func.attr in ("write_text", "write_bytes", "touch"):
            target = func.value

        # c. .open() where func.value is NOT a Name
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            if not isinstance(func.value, ast.Name):
                mode = None
                if len(node.args) >= 1:
                    mode = node.args[0]
                else:
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode = kw.value
                if mode is not None and isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    if any(c in mode.value for c in "wax+"):
                        target = func.value

        # d. shutil.copy / copy2 / copyfile / move
        elif isinstance(func, ast.Attribute) and func.attr in ("copy", "copy2", "copyfile", "move"):
            if isinstance(func.value, ast.Name) and func.value.id == "shutil" and len(node.args) >= 2:
                target = node.args[1]

        # e. os.replace / rename / renames
        elif isinstance(func, ast.Attribute) and func.attr in ("replace", "rename", "renames"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 2:
                target = node.args[1]

        # f. os.remove / unlink / rmdir / removedirs
        elif isinstance(func, ast.Attribute) and func.attr in ("remove", "unlink", "rmdir", "removedirs"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 1:
                target = node.args[0]

        # g. os.link / symlink
        elif isinstance(func, ast.Attribute) and func.attr in ("link", "symlink"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 2:
                target = node.args[1]

        if target is None:
            continue
        if python_literal_roles.safe_temp_path(target, temp, trusted):
            yield {"target": None, "unreadable": False, "temp": True}
            continue
        yield {"target": target, "unreadable": False, "temp": False}


def _build_bindings(tree, words=None):
    # a name bound exactly once to a rebuilt string stands for that string.
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            vals = _resolve(node.value, bindings, words)
            if vals is not None:
                bindings.setdefault(name, []).extend(vals)
        elif isinstance(node, ast.For):
            if isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.List, ast.Tuple)):
                if all(isinstance(el, ast.Constant) and isinstance(el.value, str) for el in node.iter.elts):
                    name = node.target.id
                    bindings.setdefault(name, []).extend(el.value for el in node.iter.elts)
        elif (isinstance(node, ast.AugAssign) and isinstance(node.op, ast.Add)
                and isinstance(node.target, ast.Name)
                and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)):
            # p = 'a.md'; p += '.py' also stands for 'a.py'.
            name = node.target.id
            for old in list(bindings.get(name, [])):
                bindings.setdefault(name, []).append(old + node.value.value)
    return bindings


def write_sinks_summary(code, words, exts):
    # the write-sink summary of a python body:
    # (code targets, unreadable, non-temporary sinks, temporary sinks).
    # None if the code is not Python.
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None
    temp = python_literal_roles.temp_names(tree)
    trusted = python_literal_roles.trusted_tempfile(tree)
    bindings = _build_bindings(tree, words)
    code_targets = set()
    unreadable = False
    n_sinks = 0
    n_temp = 0
    for sink in _iter_sinks(tree, bindings, temp, trusted, words):
        if sink["temp"]:
            n_temp += 1
            continue
        n_sinks += 1
        if sink["unreadable"]:
            unreadable = True
            continue
        vals = _resolve(sink["target"], bindings, words)
        if vals is None:
            unreadable = True
        else:
            for v in vals:
                if shell_tokens.classify_target(v, exts) == "code":
                    code_targets.add(v)
    return sorted(code_targets), unreadable, n_sinks, n_temp


def write_targets(code, words, exts):
    # the previous sink scan, kept as the standing verdict; the whitelist
    # refinement is write_sinks_summary, which only re-examines a refused body.
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return None

    temp = python_literal_roles.temp_names(tree)
    trusted = python_literal_roles.trusted_tempfile(tree)

    # Step 1: bindings (a name bound to a statically rebuilt string stands for that string)
    bindings = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
            name = node.targets[0].id
            vals = _resolve(node.value, bindings, words)
            if vals is not None:
                bindings.setdefault(name, []).extend(vals)
        elif isinstance(node, ast.For):
            if isinstance(node.target, ast.Name) and isinstance(node.iter, (ast.List, ast.Tuple)):
                if all(isinstance(el, ast.Constant) and isinstance(el.value, str) for el in node.iter.elts):
                    name = node.target.id
                    bindings.setdefault(name, []).extend(el.value for el in node.iter.elts)

    # Step 3 & 4: a write whose target is not a readable string literal is unknown.
    results = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        target = None

        # a. open(...)
        if isinstance(func, ast.Name) and func.id == "open":
            mode = None
            if len(node.args) >= 2:
                mode = node.args[1]
            else:
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode = kw.value
            if mode is not None and isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                if any(c in mode.value for c in "wax+"):
                    target = node.args[0] if node.args else next((kw.value for kw in node.keywords if kw.arg == "file"), None)

        # b. .write_text / .write_bytes
        elif isinstance(func, ast.Attribute) and func.attr in ("write_text", "write_bytes"):
            target = func.value

        # c. .open() where func.value is NOT a Name
        elif isinstance(func, ast.Attribute) and func.attr == "open":
            if not isinstance(func.value, ast.Name):
                mode = None
                if len(node.args) >= 1:
                    mode = node.args[0]
                else:
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode = kw.value
                if mode is not None and isinstance(mode, ast.Constant) and isinstance(mode.value, str):
                    if any(c in mode.value for c in "wax+"):
                        target = func.value

        # d. shutil.copy / copy2 / copyfile / move
        elif isinstance(func, ast.Attribute) and func.attr in ("copy", "copy2", "copyfile", "move"):
            if isinstance(func.value, ast.Name) and func.value.id == "shutil" and len(node.args) >= 2:
                target = node.args[1]

        # e. os.replace / rename / renames
        elif isinstance(func, ast.Attribute) and func.attr in ("replace", "rename", "renames"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 2:
                target = node.args[1]

        # f. os.remove / unlink / rmdir / removedirs
        elif isinstance(func, ast.Attribute) and func.attr in ("remove", "unlink", "rmdir", "removedirs"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 1:
                target = node.args[0]

        # g. os.link / symlink
        elif isinstance(func, ast.Attribute) and func.attr in ("link", "symlink"):
            if isinstance(func.value, ast.Name) and func.value.id == "os" and len(node.args) >= 2:
                target = node.args[1]

        if target is None:
            continue
        if python_literal_roles.safe_temp_path(target, temp, trusted):
            continue

        vals = _resolve(target, bindings, words)
        if vals is not None:
            codes = [v for v in vals if shell_tokens.classify_target(v, exts) == "code"]
            if codes:
                results.append({"verdict": "write", "targets": codes, "reason": WRITE_REASON})
        else:
            results.append({"verdict": "unknown", "targets": ["<unknown>"], "reason": UNKNOWN_REASON})
    return results


_NOTICE = (
    "NAME      inline_writes.py - reads inline Python code and says which code files it writes, "
    "even through a variable or a built path.\n"
    "READS     nothing: pure module; it works on the code text and the code extensions, "
    "with shell_tokens.py beside it.\n"
    "WRITES    nothing: write_targets() returns a list of verdicts (write, unknown) with targets "
    "and reason, or None when the code is not Python.\n"
    "EXAMPLE   python3 inline_writes.py --notice\n"
    "PITFALLS  2026-10-03 a write whose target is not rebuilt into a string literal is unknown; "
    "os.environ, sys.argv, an import alias or an attribute of an imported module are never read, "
    "so the guard refuses rather than guess; a target from tempfile (mkdtemp, TemporaryDirectory, "
    "mkstemp, a returned file or its f.name path) is in the temporary zone, outside the project, "
    "and is not a code write.\n"
    "          2026-10-05 a string literal of inline Python naming a code file was taken as a write "
    "target; only a literal that reaches a write sink is a target now, and code run by sys.executable "
    "-c is judged as code. An open() whose mode is not a readable literal, and Path.touch(), are sinks.\n"
    "          2026-10-05 git stash, a git archive unpacked into a temporary folder and an inline write "
    "to sys.argv naming a non-code file were refused; they are judged by their real target now.\n"
)

_USAGE = "usage: inline_writes.py --notice | --autotest\n"


def _autotest():
    EXTS = [".py", ".sh"]

    def W(code, words=()):
        r = write_targets(code, list(words), EXTS)
        return None if r is None else [(d["verdict"], d["targets"]) for d in r]

    U = [("unknown", ["<unknown>"])]
    ARGV = "import sys\nopen(sys.argv[1], 'w').write('x')"

    ok = True

    # Test 1
    expected = [
        [("write", ["a.py"])],
        [("write", ["a.py"])],
        [],
        [("write", ["b.py"])],
        [],
    ]
    got = [
        W("open('a.py', 'w').write('x')"),
        W("p = 'a.py'\nopen(p, 'w')"),
        W("p = 'PLAN.md'\ns = open(p).read()\nopen(p, 'w').write(s)"),
        W("for p in ['a.md', 'b.py']:\n    open(p, 'w')"),
        W("open('a.py')"),
    ]
    if got == expected:
        print(f"PASS 1 expected={expected} got={got}")
    else:
        print(f"FAIL 1 expected={expected} got={got}")
        ok = False

    # Test 2
    expected = [
        [("write", ["a.py"])],
        [("write", [".py"])],
        [("write", ["d/a.sh"])],
        [],
        [("write", ["d/a.py"])],
    ]
    got = [
        W("p = 'a' + '.py'\nopen(p, 'w')"),
        W("n = 'a'\nopen(f'{n}.py', 'w')"),
        W("from pathlib import Path\n(Path('d') / 'a.sh').write_text('x')"),
        W("import os\nopen(os.path.join(d, 'x') + '.md', 'w')"),
        W("from pathlib import Path\nPath('d').joinpath('a' + '.p' + 'y').write_text('x')"),
    ]
    if got == expected:
        print(f"PASS 2 expected={expected} got={got}")
    else:
        print(f"FAIL 2 expected={expected} got={got}")
        ok = False

    # Test 3
    expected = [
        U,
        [("write", ["x.py"])],
        U,
        U,
        [],
        U,
        U,
        U,
    ]
    got = [
        W(ARGV),
        W(ARGV, ["python3", "-", "x.py"]),
        W("import os\nopen(os.environ['F'], 'w')", ["F=a.py", "python3", "-"]),
        W(ARGV, ["python3", "-", "$F"]),
        W(ARGV, ["python3", "-", "notes.md"]),
        W("import os\nopen(os.environ['D'], 'w').write('x')", ["python3", "-"]),
        W("import os\nos.rename('a.txt', os.environ['D'])", ["python3", "-"]),
        W("import shutil\nshutil.copy('a.txt', os.environ.get('D'))", ["python3", "-"]),
    ]
    if got == expected:
        print(f"PASS 3 expected={expected} got={got}")
    else:
        print(f"FAIL 3 expected={expected} got={got}")
        ok = False

    # Test 8 : sys.argv[i] read from the command arguments of a <python> - ARG ... /
    # -c CODE ARG ... command; a word the shell would still expand stays unread.
    expected8 = [
        U,
        U,
        [("write", ["x.py"])],
        [],
        [("write", ["a.py"])],
    ]
    got8 = [
        W(ARGV, ["python3", "-", "$X"]),
        W("import sys\np = sys.argv[1]\nopen(p, 'w')", ["python3", "-", "$F"]),
        W("import sys\np = sys.argv[1]\nopen(p, 'w')", ["python3", "-", "x.py"]),
        W("import sys\np = sys.argv[1]\nopen(p, 'w')", ["python3", "-", "notes.md"]),
        W("import sys; open(sys.argv[1], 'w').write('x')", ["python3", "-c", "import sys; open(sys.argv[1], 'w').write('x')", "a.py"]),
    ]
    if got8 == expected8:
        print(f"PASS 8 expected={expected8} got={got8}")
    else:
        print(f"FAIL 8 expected={expected8} got={got8}")
        ok = False

    # Test 4
    expected = [
        [("write", ["b.py"])],
        [("write", ["c.sh"])],
        [("write", ["e.py"])],
        [("write", ["a.py"])],
        [("write", ["a.py"])],
        U,
        U,
        U,
        [],
        None,
    ]
    got = [
        W("import shutil\nshutil.copy('a.txt', 'b.py')"),
        W("import os\nos.replace(tmp, 'c.sh')"),
        W("from pathlib import Path\nPath('e.py').open('w')"),
        W("import os\nos.remove('a.py')"),
        W("import os\nos.symlink('t', 'a.py')"),
        W("from os import environ\nopen(environ['D'], 'w')"),
        W("import os as o\nopen(o.environ['D'], 'w')"),
        W("p = os.environ['D']\nopen(p, 'w')"),
        W("print(1)"),
        W("def ("),
    ]
    if got == expected:
        print(f"PASS 4 expected={expected} got={got}")
    else:
        print(f"FAIL 4 expected={expected} got={got}")
        ok = False

    # Test 5
    r5 = write_targets(ARGV, [], EXTS)
    reason_ok = r5 is not None and r5[0]["reason"] == UNKNOWN_REASON
    sp1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    notice_ok = sp1.returncode == 0 and sp1.stdout.startswith("NAME      inline_writes.py")
    sp2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True
    )
    usage_ok = sp2.returncode == 2 and sp2.stdout == "usage: inline_writes.py --notice | --autotest\n"
    expected5 = (True, True, True)
    got5 = (reason_ok, notice_ok, usage_ok)
    if got5 == expected5:
        print(f"PASS 5 expected={expected5} got={got5}")
    else:
        print(f"FAIL 5 expected={expected5} got={got5}")
        ok = False

    # Test 6
    expected6 = [
        [],
        [],
        [],
        [],
        [],
        U,
        U,
    ]
    got6 = [
        W("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, 'a.py'), 'w')"),
        W("import tempfile, os\nwith tempfile.TemporaryDirectory() as d:\n    open(os.path.join(d, 'a.py'), 'w')"),
        W("import tempfile\nfd, p = tempfile.mkstemp(suffix='.py')\nopen(p, 'w')"),
        W("import tempfile, os\nd = tempfile.mkdtemp()\np = os.path.join(d, 'a.py')\nopen(p, 'w')"),
        W("import tempfile\nfrom pathlib import Path\nd = tempfile.mkdtemp()\n(Path(d) / 'a.py').write_text('x')"),
        W("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, '..', 'x.py'), 'w')"),
        W("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, '/tmp/x.py'), 'w')"),
    ]
    if got6 == expected6:
        print(f"PASS 6 expected={expected6} got={got6}")
    else:
        print(f"FAIL 6 expected={expected6} got={got6}")
        ok = False

    # Test 7
    expected7 = [
        [],
        [],
        [],
        [],
        [],
        [("write", ["x.py"])],
        U,
        U,
    ]
    got7 = [
        W("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nopen(f.name, 'w')"),
        W("import tempfile, shutil\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nshutil.copy('a.txt', f.name)"),
        W("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nos.rename('a.txt', f.name)"),
        W("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nos.unlink(f.name)"),
        W("import tempfile, os\nwith tempfile.NamedTemporaryFile('w', suffix='.py', delete=False) as f:\n    open(f.name, 'w')"),
        W("import tempfile, shutil\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nshutil.copy(f.name, 'x.py')"),
        W("import tempfile, os\nf = 'x.py'\nopen(f.name, 'w')"),
        W("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nf = 'x.py'\nopen(f.name, 'w')"),
    ]
    if got7 == expected7:
        print(f"PASS 7 expected={expected7} got={got7}")
    else:
        print(f"FAIL 7 expected={expected7} got={got7}")
        ok = False

    return 0 if ok else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(_NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    sys.stdout.write(_USAGE)
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "inline_writes", sys.argv[1:])
