#!/usr/bin/env python3
"""python_read_proof.py - proves from the syntax tree that inline Python code only reads; any doubt answers False."""

import ast
import os
import re
import sys
import subprocess
import warnings

FORBIDDEN_NAMES = {"remove", "unlink", "rename", "renames", "rmdir", "removedirs", "mkdir", "makedirs", "chmod", "lchmod", "chown", "lchown", "chflags", "lchflags", "symlink_to", "hardlink_to", "link_to", "utime", "exec", "eval", "compile", "__import__", "getattr", "setattr", "delattr", "globals", "locals", "vars", "breakpoint", "__builtins__", "builtins", "subprocess", "system", "popen", "Popen", "fork", "forkpty", "pty", "runpy", "importlib", "ctypes", "io", "codecs", "fileinput", "shutil", "fdopen", "write", "writelines", "write_text", "write_bytes", "pwrite", "writev", "sendfile", "truncate", "ftruncate", "link", "symlink", "mkfifo", "mknod", "touch", "startfile", "urlretrieve", "multiprocessing", "asyncio", "pickle", "marshal", "code", "codeop", "timeit", "pydoc", "pdb", "bdb", "cProfile", "profile", "trace", "doctest", "tkinter", "webbrowser", "methodcaller", "attrgetter", "FileType", "get_type_hints", "ForwardRef", "make_dataclass", "modules"}
READ_MODES = {"r", "rt", "tr", "rb", "br"}
SAFE_ROOTS = {"sys", "os", "re", "json", "shlex", "math", "statistics", "string", "textwrap", "difflib", "datetime", "time", "glob", "fnmatch", "hashlib", "base64", "collections", "itertools", "functools", "operator", "copy", "pprint", "typing", "dataclasses", "enum", "decimal", "fractions", "random", "heapq", "bisect", "unicodedata", "ast", "tokenize", "keyword", "csv", "struct", "zlib", "binascii", "uuid", "ipaddress", "locale", "platform", "tomllib", "configparser", "argparse", "contextlib", "html", "pathlib"}
CODE_PATH_PATTERN = re.compile(r"\.(py|js|ts|jsx|tsx|sh|sql|html|css|go|rb|java|rs|c|cpp|php)\b")


def read_proven(code):
    try:
        # Rule 1
        if not isinstance(code, str) or code.strip() == "":
            return False

        # Rule 2
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            tree = ast.parse(code)

        # Collect import-bound names (for rule 3e)
        import_bound_names = set()
        has_import_replace = False
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                for alias in node.names:
                    if alias.name == "replace":
                        has_import_replace = True
                    if alias.asname:
                        import_bound_names.add(alias.asname)
                    else:
                        import_bound_names.add(alias.name.split(".")[0])

        # Build parent map for 3e
        parent_map = {}
        for parent in ast.walk(tree):
            for child in ast.iter_child_nodes(parent):
                parent_map[id(child)] = parent

        # Rule 3
        for node in ast.walk(tree):
            # 3a
            if isinstance(node, ast.Name):
                if node.id in FORBIDDEN_NAMES:
                    return False
                if node.id.startswith("__") and node.id.endswith("__") and node.id not in {"__name__", "__file__", "__doc__"}:
                    return False
            # 3b
            elif isinstance(node, ast.Attribute):
                a = node.attr
                if a in FORBIDDEN_NAMES:
                    return False
                if a == "open":
                    return False
                if a.startswith("exec") or a.startswith("spawn") or a.startswith("posix_spawn") or a.startswith("fork"):
                    return False
                if a.startswith("_"):
                    return False
            # 3c
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    for part in alias.name.split("."):
                        if part in FORBIDDEN_NAMES or part == "open" or part.startswith("_"):
                            return False
                    if alias.asname and (alias.asname in FORBIDDEN_NAMES or alias.asname == "open" or alias.asname.startswith("_")):
                        return False
            elif isinstance(node, ast.ImportFrom):
                if node.level > 0:
                    return False
                if node.module:
                    for part in node.module.split("."):
                        if part in FORBIDDEN_NAMES or part == "open" or part.startswith("_"):
                            return False
                for alias in node.names:
                    if alias.name == "*":
                        return False
                    for part in alias.name.split("."):
                        if part in FORBIDDEN_NAMES or part == "open" or part.startswith("_"):
                            return False
                    if alias.asname and (alias.asname in FORBIDDEN_NAMES or alias.asname == "open" or alias.asname.startswith("_")):
                        return False
            # 3d
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                if node.name == "open":
                    return False
            elif isinstance(node, ast.arg):
                if node.arg == "open":
                    return False
            elif isinstance(node, ast.alias):
                if node.asname == "open":
                    return False

        # 3e: handle "replace" attributes
        if has_import_replace:
            return False
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "replace":
                parent = parent_map.get(id(node))
                if not (isinstance(parent, ast.Call) and parent.func is node):
                    return False
                if len(parent.args) < 2:
                    return False
                receiver = node.value
                if isinstance(receiver, ast.Name) and receiver.id in import_bound_names:
                    return False

        # Rule 4
        call_func_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                call_func_ids.add(id(node.func))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "open":
                if id(node) not in call_func_ids:
                    return False

        # Rule 5
        READ_PATHS = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "open":
                for arg in node.args:
                    if isinstance(arg, ast.Starred):
                        return False
                for kw in node.keywords:
                    if kw.arg is None:
                        return False
                for kw in node.keywords:
                    if kw.arg == "opener":
                        return False
                mode_node = None
                if len(node.args) >= 2:
                    mode_node = node.args[1]
                else:
                    for kw in node.keywords:
                        if kw.arg == "mode":
                            mode_node = kw.value
                            break
                if mode_node is not None:
                    if not isinstance(mode_node, ast.Constant) or not isinstance(mode_node.value, str) or mode_node.value not in READ_MODES:
                        return False
                path_node = None
                if len(node.args) >= 1:
                    path_node = node.args[0]
                else:
                    for kw in node.keywords:
                        if kw.arg == "file":
                            path_node = kw.value
                            break
                if path_node is not None:
                    READ_PATHS.add(id(path_node))

        # Rule 6
        roots = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    roots.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    roots.append(node.module.split(".")[0])
        if not roots or all(r in SAFE_ROOTS for r in roots):
            return True

        # Rule 7
        PRINTED_STRINGS = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "print":
                has_file_kw = any(kw.arg == "file" for kw in node.keywords)
                if not has_file_kw:
                    for arg in node.args:
                        if isinstance(arg, ast.Constant):
                            PRINTED_STRINGS.add(id(arg))
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, str):
                if CODE_PATH_PATTERN.search(node.value):
                    if id(node) not in READ_PATHS and id(node) not in PRINTED_STRINGS:
                        return False
        return True

    except Exception:
        return False


def _autotest():
    READS = [
        "print(open('x.py').read())",
        "open('x.py', 'r')",
        "import shlex\nfor s in ['echo x 2>&1 >out.py', 'tee -a lib/u.py', 'sed -i s/a/b/ f.py']:\n    print(shlex.split(s))",
        "import mymod\nprint(mymod.f(open('../bin/a.py').read()))",
        "import json\nd = json.load(open('c.json', encoding='utf-8'))\nprint(len(d) > 3)",
        "import mymod\nprint('a.py', mymod.ok(open('a.py').read()))",
    ]
    MODES = [
        "open('x.py', 'w')",
        "open('x.py', 'a')",
        "open('x.py', mode='w')",
        "open('x.py', 'r+')",
        "open('x.py', 'wb')",
        "open(file='x.py', mode='w')",
        "m = 'w'\nopen('x.py', m)",
        "o = open\no('x.py', 'w')",
        "a = ['x.py', 'w']\nopen(*a)",
        "open('x.py', opener=f)",
    ]
    FORBIDDEN = [
        "import os\nos.system('echo x > a.py')",
        "import os\nos.remove('a.py')",
        "import os as o\no.replace('t', 'a.py')",
        "import subprocess\nsubprocess.run(['tee', 'out.py'])",
        "import io\nio.open('x.py', 'w')",
        "import codecs\ncodecs.open('x.py', 'w')",
        "import os\nos.popen('tee a.py')",
        "exec(\"open('x.py', 'w')\")",
        "from pathlib import Path\nPath('x.py').write_text('')",
        "getattr(__builtins__, 'open')('x.py', 'w')",
        "__import__('os').system('x')",
        "print(().__class__.__base__.__subclasses__())",
        "import os, operator\noperator.methodcaller('system', 'tee a.py')(os)",
        "import argparse\nargparse.FileType('w')('x.py')",
        "import uuid\nuuid._get_command_stdout('tee', 'a.py')",
    ]
    THIRD_PARTY = [
        "import mytool\nmytool.run('tee a.py')",
        "import mytool\nmytool.save('x.py')",
        "from mytool import go\ngo('echo a > b.sh')",
        "from . import m\nprint(m)",
        "import mymod\nprint('a.py', file=mymod.out)",
    ]
    INVALID = [
        "open('x.py'",
        "",
        "   ",
    ]

    all_pass = True

    # Proof 1: READS all True
    expected = len(READS)
    got = sum(1 for c in READS if read_proven(c) is True)
    if expected == 0:
        print("FAIL proof 1: expected 0, got 0, first: (empty list)")
        all_pass = False
    elif got == expected:
        print("PASS proof 1: expected %d, got %d" % (expected, got))
    else:
        first_bad = next(c for c in READS if read_proven(c) is not True)
        print("FAIL proof 1: expected %d, got %d, first: %r" % (expected, got, first_bad))
        all_pass = False

    # Proof 2: MODES all False
    expected = len(MODES)
    got = sum(1 for c in MODES if read_proven(c) is False)
    if expected == 0:
        print("FAIL proof 2: expected 0, got 0, first: (empty list)")
        all_pass = False
    elif got == expected:
        print("PASS proof 2: expected %d, got %d" % (expected, got))
    else:
        first_bad = next(c for c in MODES if read_proven(c) is not False)
        print("FAIL proof 2: expected %d, got %d, first: %r" % (expected, got, first_bad))
        all_pass = False

    # Proof 3: FORBIDDEN all False
    expected = len(FORBIDDEN)
    got = sum(1 for c in FORBIDDEN if read_proven(c) is False)
    if expected == 0:
        print("FAIL proof 3: expected 0, got 0, first: (empty list)")
        all_pass = False
    elif got == expected:
        print("PASS proof 3: expected %d, got %d" % (expected, got))
    else:
        first_bad = next(c for c in FORBIDDEN if read_proven(c) is not False)
        print("FAIL proof 3: expected %d, got %d, first: %r" % (expected, got, first_bad))
        all_pass = False

    # Proof 4: THIRD_PARTY all False
    expected = len(THIRD_PARTY)
    got = sum(1 for c in THIRD_PARTY if read_proven(c) is False)
    if expected == 0:
        print("FAIL proof 4: expected 0, got 0, first: (empty list)")
        all_pass = False
    elif got == expected:
        print("PASS proof 4: expected %d, got %d" % (expected, got))
    else:
        first_bad = next(c for c in THIRD_PARTY if read_proven(c) is not False)
        print("FAIL proof 4: expected %d, got %d, first: %r" % (expected, got, first_bad))
        all_pass = False

    # Proof 5: INVALID all False + None + 42
    expected = len(INVALID) + 2
    got = sum(1 for c in INVALID if read_proven(c) is False)
    got += 1 if read_proven(None) is False else 0
    got += 1 if read_proven(42) is False else 0
    if expected == 0:
        print("FAIL proof 5: expected 0, got 0, first: (empty list)")
        all_pass = False
    elif got == expected:
        print("PASS proof 5: expected %d, got %d" % (expected, got))
    else:
        first_bad = next(c for c in INVALID if read_proven(c) is not False)
        print("FAIL proof 5: expected %d, got %d, first: %r" % (expected, got, first_bad))
        all_pass = False

    # Self-relaunch checks
    if os.environ.get("PRP_CHILD") != "1":
        r = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True, env=dict(os.environ, PRP_CHILD="1"))
        if r.returncode == 0:
            print("PASS relaunch --notice: expected 0, got %d" % r.returncode)
        else:
            print("FAIL relaunch --notice: expected 0, got %d" % r.returncode)
            all_pass = False

        r = subprocess.run([sys.executable, __file__, "--unknown"], capture_output=True, text=True, env=dict(os.environ, PRP_CHILD="1"))
        if r.returncode == 2:
            print("PASS relaunch --unknown: expected 2, got %d" % r.returncode)
        else:
            print("FAIL relaunch --unknown: expected 2, got %d" % r.returncode)
            all_pass = False

    return 0 if all_pass else 1


def _notice():
    print("NAME      python_read_proof.py - proves from the syntax tree that inline Python code only reads; any doubt answers False.")
    print("READS     nothing: pure module; it works on the code text only and never runs it.")
    print("WRITES    nothing: read_proven() returns True or False and never raises.")
    print("EXAMPLE   python3 python_read_proof.py --autotest")
    print("PITFALLS  2026-09-27 a third party import is trusted only when no code path string appears outside an open() read or a plain print().")


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    elif len(sys.argv) == 2 and sys.argv[1] == "--notice":
        _notice()
        sys.exit(0)
    else:
        print("usage: python3 python_read_proof.py [--autotest | --notice]")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "python_read_proof", sys.argv[1:])
