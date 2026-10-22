import ast
import os
import re
import sys
import subprocess
import warnings


FORBIDDEN_NAMES = {"remove", "unlink", "rename", "renames", "rmdir", "removedirs", "mkdir", "makedirs", "chmod", "lchmod", "chown", "lchown", "chflags", "lchflags", "symlink_to", "hardlink_to", "link_to", "utime", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "breakpoint", "__builtins__", "builtins", "subprocess", "system", "popen", "Popen", "fork", "forkpty", "pty", "runpy", "importlib", "ctypes", "io", "codecs", "fileinput", "shutil", "fdopen", "write_text", "write_bytes", "pwrite", "writev", "sendfile", "truncate", "ftruncate", "link", "symlink", "mkfifo", "mknod", "touch", "startfile", "urlretrieve", "multiprocessing", "asyncio", "pickle", "marshal", "code", "codeop", "timeit", "pydoc", "pdb", "bdb", "cProfile", "profile", "trace", "doctest", "tkinter", "webbrowser", "methodcaller", "attrgetter", "FileType", "get_type_hints", "ForwardRef", "make_dataclass", "modules", "copy", "copy_into", "move", "move_into", "copyfile", "copytree", "setxattr", "removexattr"}

HAZARD_NAMES = {"copy", "copy_into", "move", "move_into"}

READ_MODES = {"r", "rt", "tr", "rb", "br"}

MODE_PATTERN = re.compile(r"[rwaxbt+]{1,3}")

SAFE_ROOTS = {"sys", "os", "re", "json", "shlex", "math", "statistics", "string", "textwrap", "difflib", "datetime", "time", "glob", "fnmatch", "hashlib", "base64", "collections", "itertools", "functools", "operator", "pprint", "typing", "dataclasses", "enum", "decimal", "fractions", "random", "heapq", "bisect", "unicodedata", "ast", "tokenize", "keyword", "csv", "struct", "zlib", "binascii", "uuid", "ipaddress", "locale", "platform", "tomllib", "configparser", "argparse", "contextlib", "html", "pathlib"}


def str_proven(node, str_names):
    if isinstance(node, ast.Constant):
        return isinstance(node.value, (str, bytes))
    if isinstance(node, ast.Name):
        return node.id in str_names
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Attribute) and node.func.attr == "read":
            if not node.args and not node.keywords:
                inner = node.func.value
                if isinstance(inner, ast.Call) and isinstance(inner.func, ast.Name) and inner.func.id == "open":
                    return True
            return False
        if isinstance(node.func, ast.Attribute) and node.func.attr == "replace":
            return str_proven(node.func.value, str_names)
        return False
    if isinstance(node, ast.Subscript):
        if isinstance(node.value, ast.Attribute) and node.value.attr == "argv":
            if isinstance(node.value.value, ast.Name) and node.value.value.id == "sys":
                return True
        return False
    return False


def _compute_bound(tree):
    simple_targets = set()
    assigns = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            if len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                simple_targets.add(id(node.targets[0]))
                name = node.targets[0].id
                assigns.setdefault(name, []).append(node.value)

    other_bound = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Store) and id(node) not in simple_targets:
                other_bound.add(node.id)
            if isinstance(node.ctx, ast.Del):
                other_bound.add(node.id)
        if isinstance(node, ast.alias):
            if node.asname is not None:
                other_bound.add(node.asname)
            else:
                other_bound.add(node.name.split(".")[0])
        if isinstance(node, ast.arg):
            other_bound.add(node.arg)
        if isinstance(node, (ast.Global, ast.Nonlocal)):
            for n in node.names:
                other_bound.add(n)
        if not isinstance(node, ast.alias):
            nv = getattr(node, "name", None)
            if isinstance(nv, str):
                other_bound.add(nv)
        rv = getattr(node, "rest", None)
        if isinstance(rv, str):
            other_bound.add(rv)

    const_values = {}
    for name, values in assigns.items():
        if name in other_bound:
            continue
        if all(isinstance(v, ast.Constant) and isinstance(v.value, str) for v in values):
            const_values[name] = set(v.value for v in values)

    str_names = set()
    for name, values in assigns.items():
        if name in other_bound:
            continue
        if all(str_proven(v, set()) for v in values):
            str_names.add(name)

    return const_values, str_names


def _alias_bad(alias):
    candidates = [alias.name] + alias.name.split(".")
    if alias.asname is not None:
        candidates.append(alias.asname)
    for c in candidates:
        if c in FORBIDDEN_NAMES:
            return True
        if c == "open" or c == "replace" or c == "*":
            return True
        if c.startswith("_"):
            return True
    return False


def _module_part_bad(part):
    if part in FORBIDDEN_NAMES:
        return True
    if part == "open" or part == "replace" or part == "*":
        return True
    if part.startswith("_"):
        return True
    return False


def written_paths(code):
    try:
        if not isinstance(code, str) or not code.strip():
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(code)
        const_values, str_names = _compute_bound(tree)

        open_call_func_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                open_call_func_ids.add(id(node.func))

        for node in ast.walk(tree):
            if isinstance(node, ast.Name):
                if node.id in FORBIDDEN_NAMES:
                    return None
                if len(node.id) >= 4 and node.id.startswith("__") and node.id.endswith("__") and node.id not in ("__name__", "__file__", "__doc__"):
                    return None
            if isinstance(node, ast.Attribute):
                a = node.attr
                if a in FORBIDDEN_NAMES:
                    return None
                if a == "open":
                    return None
                if a.startswith("exec") or a.startswith("spawn") or a.startswith("posix_spawn") or a.startswith("fork"):
                    return None
                if a.startswith("_"):
                    return None
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if _alias_bad(alias):
                        return None
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    if _alias_bad(alias):
                        return None
                if node.module is not None:
                    for part in node.module.split("."):
                        if _module_part_bad(part):
                            return None
                if node.level > 0:
                    return None
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == "open":
                    return None
            if isinstance(node, ast.arg):
                if node.arg == "open":
                    return None
            if isinstance(node, ast.Attribute) and node.attr == "replace":
                parent = None
                for pn in ast.walk(tree):
                    if isinstance(pn, ast.Call) and pn.func is node:
                        parent = pn
                        break
                if parent is None:
                    return None
                if not str_proven(node.value, str_names):
                    return None

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "open":
                if id(node) not in open_call_func_ids:
                    return None

        paths = set()
        for node in ast.walk(tree):
            if not (isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open"):
                continue
            if any(isinstance(a, ast.Starred) for a in node.args):
                return None
            if any(kw.arg is None for kw in node.keywords):
                return None
            if any(kw.arg == "opener" for kw in node.keywords):
                return None

            if len(node.args) >= 2:
                mode_node = node.args[1]
            else:
                mode_node = None
                for kw in node.keywords:
                    if kw.arg == "mode":
                        mode_node = kw.value
                        break

            if mode_node is None:
                continue
            if not (isinstance(mode_node, ast.Constant) and isinstance(mode_node.value, str)):
                return None
            m = mode_node.value
            if m in READ_MODES:
                continue
            if MODE_PATTERN.fullmatch(m) is None:
                return None
            if not any(c in m for c in "wax+"):
                continue

            if node.args:
                path_node = node.args[0]
            else:
                path_node = None
                for kw in node.keywords:
                    if kw.arg == "file":
                        path_node = kw.value
                        break
            if path_node is None:
                return None
            if isinstance(path_node, ast.Constant) and isinstance(path_node.value, str):
                paths.add(path_node.value)
            elif isinstance(path_node, ast.Name) and path_node.id in const_values:
                paths.update(const_values[path_node.id])
            else:
                return None

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in SAFE_ROOTS:
                        return None
            if isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    root = node.module.split(".")[0]
                    if root not in SAFE_ROOTS:
                        return None

        return sorted(paths)
    except Exception:
        return None


def hazard(code):
    try:
        if not isinstance(code, str) or not code.strip():
            return True
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(code)
        const_values, str_names = _compute_bound(tree)

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute):
                if node.attr in HAZARD_NAMES:
                    return True
            if isinstance(node, ast.Name):
                if node.id in HAZARD_NAMES:
                    return True
            if isinstance(node, ast.alias):
                if node.name in HAZARD_NAMES or node.name == "replace":
                    return True
                if node.asname is not None:
                    if node.asname in HAZARD_NAMES or node.asname == "replace":
                        return True
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "replace":
                found = False
                for parent in ast.walk(tree):
                    if isinstance(parent, ast.Call) and parent.func is node:
                        found = True
                        break
                if not found:
                    return True
                if not str_proven(node.value, str_names):
                    return True
        return False
    except Exception:
        return True


def dynamic_exec(code):
    """Return a reason when inline Python executes code the guard cannot read, else None.

    exec/eval of anything but a constant literal, compile, __import__ of a non-literal
    name, getattr on the builtins, runpy/importlib loaders and a name aliased to one of
    these make the non-write proof impossible: unknown. A literal exec/eval is not named
    here: it is handed back as code by exec_literals().
    """
    try:
        if not isinstance(code, str) or not code.strip():
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(code)
    except Exception:
        return None

    dangerous_names = {"exec", "eval", "compile", "__import__", "getattr"}
    loader_attrs = {"run_path", "import_module", "reload"}
    builtins_names = {"builtins", "__builtins__"}

    def is_builtins(node):
        return isinstance(node, ast.Name) and node.id in builtins_names

    def is_loader_base(node):
        return is_builtins(node) or (
            isinstance(node, ast.Name) and node.id in ("runpy", "importlib")
        )

    # Collect names bound by "import builtins as X" before any pass.
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "builtins" and alias.asname is not None:
                    builtins_names.add(alias.asname)

    # Pass 1: a name aliased to a dangerous call is itself dangerous.
    aliases = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            if len(targets) != 1 or not isinstance(targets[0], ast.Name):
                continue
            v = node.value
            if isinstance(v, ast.Name) and v.id in dangerous_names:
                aliases.add(targets[0].id)
            elif isinstance(v, ast.Attribute):
                if (v.attr in dangerous_names and is_builtins(v.value)) or \
                   (v.attr in loader_attrs and is_loader_base(v.value)):
                    aliases.add(targets[0].id)

    # Pass 2: calls that run code the guard cannot read.
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        if isinstance(f, ast.Name):
            if f.id in ("exec", "eval"):
                if not node.args:
                    return "python runs code the guard cannot read"
                if not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    return "python runs code the guard cannot read"
            elif f.id == "compile":
                return "python compiles code the guard cannot read"
            elif f.id == "__import__":
                if not node.args:
                    return "python imports a module the guard cannot read"
                if not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    return "python imports a module the guard cannot read"
            elif f.id == "getattr":
                if node.args and is_builtins(node.args[0]):
                    return "python reads a built-in the guard cannot see"
            elif f.id in aliases:
                return "python runs code the guard cannot read"
        elif isinstance(f, ast.Attribute):
            if f.attr in ("exec", "eval") and is_builtins(f.value):
                if not node.args:
                    return "python runs code the guard cannot read"
                if not (isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str)):
                    return "python runs code the guard cannot read"
            elif f.attr == "compile" and is_builtins(f.value):
                return "python compiles code the guard cannot read"
            elif f.attr in loader_attrs and is_loader_base(f.value):
                return "python loads a module the guard cannot read"

    # Pass 3 (closed): a namespace the guard cannot see reaches builtin access.
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "__dict__" and is_builtins(node.value):
            return "python reads a namespace the guard cannot see"
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == "vars":
                for arg in node.args:
                    if is_builtins(arg):
                        return "python reads a namespace the guard cannot see"
                for kw in node.keywords:
                    if is_builtins(kw.value):
                        return "python reads a namespace the guard cannot see"
        if isinstance(node, ast.Subscript):
            value = node.value
            if isinstance(value, ast.Call) and isinstance(value.func, ast.Name) and value.func.id in ("vars", "globals", "locals"):
                return "python reads a namespace the guard cannot see"
            if isinstance(value, ast.Attribute) and value.attr == "__dict__":
                return "python reads a namespace the guard cannot see"
            if is_builtins(value):
                return "python reads a namespace the guard cannot see"
    return None


def exec_literals(code):
    """Return the literal code texts passed to exec/eval in inline Python.

    Only exec/eval reached by their own name, or on builtins/__builtins__, are followed;
    an alias of exec/eval is unknown, not followed (dynamic_exec() names it).
    """
    try:
        if not isinstance(code, str) or not code.strip():
            return []
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(code)
    except Exception:
        return []

    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        f = node.func
        name = None
        if isinstance(f, ast.Name) and f.id in ("exec", "eval"):
            name = f.id
        elif isinstance(f, ast.Attribute) and f.attr in ("exec", "eval"):
            if isinstance(f.value, ast.Name) and f.value.id in ("builtins", "__builtins__"):
                name = f.attr
        if name is None:
            continue
        if not node.args:
            continue
        arg = node.args[0]
        if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
            out.append(arg.value)
    return out


PROVEN = [
    ("print(open('x.py').read())", []),
    ("open('notes.md', 'w').write('see bin/x.py')", ["notes.md"]),
    ("import json\njson.dump({'t': 'lib/a.py'}, open('res.json', 'w'))", ["res.json"]),
    ("p = 'a.md'\np = 'b.txt'\ns = open(p).read()\nopen(p, 'w').write(s.replace('x', 'y').replace('u', 'v'))", ["a.md", "b.txt"]),
    ("with open('r.txt', 'a') as f:\n    f.write('ok')", ["r.txt"]),
    ("print('x', file=open('lib/b.py', 'w+'))", ["lib/b.py"]),
    ("open(file='o.md', mode='x')", ["o.md"]),
]

NOT_PROVEN = [
    "for p in ['a.md', 'b.py']:\n    open(p, 'w')",
    "def f(p):\n    open(p, 'w')",
    "(p := 'a.py')\nopen(p, 'w')",
    "p = 'a.md'\np += '.py'\nopen(p, 'w')",
    "p = q = 'a.py'\nopen(q, 'w')",
    "p = 'a.md'\ndel p\nopen(p, 'w')",
    "open('a.p' + 'y', 'w')",
    "open('a.md', mode='w'.upper())",
    "open(*['a.py', 'w'])",
    "open('a.md', 'w', opener=f)",
    "o = open\no('a.md', 'w')",
    "import mytool\nopen('a.md', 'w')",
    "import os\nos.remove('a.py')",
    "import os\nx = os\nx.replace('t.md', 'a.py')",
    "from pathlib import Path\nPath('t.md').copy('a.py')",
    "open('a.md', 'q')",
    "from os import replace\nreplace('t.md', 'a.py')",
]

HAZARD_CASES = [
    ("print('a-b'.replace('-', '_'))", False),
    ("import sys\nprint(sys.argv[0].replace('.py', ''))", False),
    ("print(open('a.txt').read().replace('a', 'b'))", False),
    ("import mymod\nprint(mymod.f(open('a.py').read()))", False),
    ("import glob\nglob.os.replace('t.md', 'a.py')", True),
    ("import pathlib\nP = pathlib.Path\nP.replace(P('t.md'), 'a.py')", True),
    ("from pathlib import Path\nPath('t.md').move('a.py')", True),
    ("s = 'a'\nimport os\ns = os\ns.replace('t.md', 'a.py')", True),
]

INVALID = [None, 42, "", "   ", "open('x.py'"]

DYNAMIC_EXEC = [
    "exec(open('a.txt').read())",
    "exec('op'+'en(...)')",  # lang-ok: en is a fragment of open, not French
    "eval(compile(open('a.txt').read(), 'x', 'exec'))",
    "compile('x','y','exec')",
    "__import__(name)",
    "getattr(__builtins__, 'open')('x.py', 'w')",
    "import builtins\nbuiltins.exec(open('a.txt').read())",
    "e = eval; e('print(1)')",
    "import builtins; e = builtins.exec; e('print(1)')",
    "import runpy\nrunpy.run_path('x.py')",
    "import importlib\nimportlib.import_module('os')",
    "import importlib\nimportlib.reload(m)",
    "__builtins__.__dict__['exec']('print(1)')",
    "__builtins__.__dict__['ex'+'ec']('print(1)')",
    "import builtins; builtins.__dict__['eval']('1')",
    "vars(__builtins__)['exec']('print(1)')",
    "globals()['__builtins__'].exec('print(1)')",
    "import builtins as b; b.__dict__['exec']('print(1)')",
]

DYNAMIC_EXEC_OK = [
    "exec('print(1)')",
    "eval('print(1)')",
    "__import__('os')",
    "print(open('a.txt').read())",
    "import builtins\nbuiltins.eval('print(1)')",
    "import importlib.util\ns = importlib.util.spec_from_file_location('b', 'tool.py')",
    "d = {'a': 1}; print(d['a'])",
    "import json; print(json.loads('[1]')[0])",
]


def _autotest():
    all_pass = True

    # Test 1
    expected = len(PROVEN)
    obtained = 0
    first_fail = None
    for code, want in PROVEN:
        got = written_paths(code)
        if got == want:
            obtained += 1
        else:
            if first_fail is None:
                first_fail = (code, got)
    if obtained == expected:
        print("PASS %d/%d test 1 (written_paths PROVEN)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 1 (written_paths PROVEN) first=%r got=%r" % (expected, obtained, first_fail[0], first_fail[1]))
        all_pass = False

    # Test 2
    expected = len(NOT_PROVEN)
    obtained = 0
    first_fail = None
    for code in NOT_PROVEN:
        got = written_paths(code)
        if got is None:
            obtained += 1
        else:
            if first_fail is None:
                first_fail = (code, got)
    if obtained == expected:
        print("PASS %d/%d test 2 (written_paths NOT_PROVEN)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 2 (written_paths NOT_PROVEN) first=%r got=%r" % (expected, obtained, first_fail[0], first_fail[1]))
        all_pass = False

    # Test 3
    expected = len(HAZARD_CASES)
    obtained = 0
    first_fail = None
    for code, want in HAZARD_CASES:
        got = hazard(code)
        if got == want:
            obtained += 1
        else:
            if first_fail is None:
                first_fail = (code, got)
    if obtained == expected:
        print("PASS %d/%d test 3 (hazard HAZARD_CASES)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 3 (hazard HAZARD_CASES) first=%r got=%r" % (expected, obtained, first_fail[0], first_fail[1]))
        all_pass = False

    # Test 4
    expected = len(INVALID)
    obtained = 0
    first_fail = None
    for val in INVALID:
        w = written_paths(val)
        h = hazard(val)
        if w is None and h is True:
            obtained += 1
        else:
            if first_fail is None:
                first_fail = (val, (w, h))
    if obtained == expected:
        print("PASS %d/%d test 4 (INVALID)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 4 (INVALID) first=%r got=%r" % (expected, obtained, first_fail[0], first_fail[1]))
        all_pass = False

    # Test 5
    expected = 5
    obtained = 0
    first_fail = None
    cases = [
        (str_proven(ast.parse("'a'").body[0].value, set()) is True, "case 1"),
        (str_proven(ast.parse("x").body[0].value, set()) is False, "case 2"),
        (str_proven(ast.parse("x").body[0].value, {"x"}) is True, "case 3"),
        (str_proven(ast.parse("open('a').read()").body[0].value, set()) is True, "case 4"),
        (str_proven(ast.parse("f.read()").body[0].value, set()) is False, "case 5"),
    ]
    for cond, label in cases:
        if cond:
            obtained += 1
        else:
            if first_fail is None:
                first_fail = (label, cond)
    if obtained == expected:
        print("PASS %d/%d test 5 (str_proven)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 5 (str_proven) first=%r got=%r" % (expected, obtained, first_fail[0], first_fail[1]))
        all_pass = False

    # Test 6
    expected = len(DYNAMIC_EXEC) + len(DYNAMIC_EXEC_OK)
    obtained = 0
    first_fail = None
    for code in DYNAMIC_EXEC:
        if dynamic_exec(code) is not None:
            obtained += 1
        elif first_fail is None:
            first_fail = (code, dynamic_exec(code))
    for code in DYNAMIC_EXEC_OK:
        if dynamic_exec(code) is None:
            obtained += 1
        elif first_fail is None:
            first_fail = (code, dynamic_exec(code))
    if obtained == expected:
        print("PASS %d/%d test 6 (dynamic_exec)" % (expected, obtained))
    else:
        print("FAIL %d/%d test 6 (dynamic_exec) first=%r" % (expected, obtained, first_fail))
        all_pass = False

    # Subprocess relaunches
    if os.environ.get("PWP_CHILD") != "1":
        env = dict(os.environ, PWP_CHILD="1")
        r1 = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True, env=env)
        if r1.returncode == 0:
            print("PASS subprocess --notice expected=0 got=0")
        else:
            print("FAIL subprocess --notice expected=0 got=%d" % r1.returncode)
            all_pass = False
        r2 = subprocess.run([sys.executable, __file__, "--unknown"], capture_output=True, text=True, env=env)
        if r2.returncode == 2:
            print("PASS subprocess --unknown expected=2 got=2")
        else:
            print("FAIL subprocess --unknown expected=2 got=%d" % r2.returncode)
            all_pass = False

    sys.exit(0 if all_pass else 1)


def _notice():
    print("NAME      python_write_proof.py - proves from the syntax tree which files inline Python code can write, when every written path is a constant; any doubt proves nothing.")
    print("READS     nothing: pure module; it works on the code text only and never runs it.")
    print("WRITES    nothing: written_paths() returns a sorted list or None, hazard() returns True or False, dynamic_exec() returns a reason or None, exec_literals() returns the literal exec/eval texts; none raises.")
    print("EXAMPLE   python3 python_write_proof.py --autotest")
    print("PITFALLS  2026-09-27 a module bound to a plain name (x = os; x.replace) or Path.copy on Python 3.14 escaped the read proof; hazard() closes both.")
    print("          2026-10-03 exec/eval of built or read code, compile, a non-literal __import__, getattr on the builtins, runpy/importlib loaders and a name aliased to one of them escape the non-write proof; dynamic_exec() names them, exec_literals() hands a literal exec/eval back to be judged as code.")
    sys.exit(0)


def _cli():
        if len(sys.argv) >= 2:
            if sys.argv[1] == "--autotest":
                _autotest()
            elif sys.argv[1] == "--notice":
                _notice()
            else:
                print("usage: python3 python_write_proof.py [--autotest | --notice]")
                sys.exit(2)
        else:
            print("usage: python3 python_write_proof.py [--autotest | --notice]")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "python_write_proof", sys.argv[1:])
