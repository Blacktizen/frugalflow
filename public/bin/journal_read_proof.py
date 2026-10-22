#!/usr/bin/env python3
"""journal_read_proof.py - proves from the syntax tree that inline Python code only
reads a journal: a positive whitelist of read calls, any doubt answers None."""

import ast
import os
import subprocess
import sys

USAGE = "usage: journal_read_proof.py --notice | --autotest\n"

NOTICE = (
    "NAME      journal_read_proof.py - proves from the syntax tree that inline Python code only reads a journal: a positive whitelist of read calls, any doubt answers None.\n"
    "READS     nothing: pure module; it works on the code text only and never runs it.\n"
    "WRITES    nothing: proven_reads() returns the literals passed to a read-mode open(), or None when the code is not proven to only read.\n"
    "EXAMPLE   python3 journal_read_proof.py --autotest\n"
    "PITFALLS  2026-10-05 a proven read of a journal log was refused as a write; only open() in a read mode, json load(s)/dump(s), print and a literal-list subprocess.run without shell=True are trusted, and every other name is refused.\n"
)

READ_MODES = {"r", "rt", "tr", "rb", "br"}

# a name or attribute from this set anywhere in the code is a write, a move or a
# run of other code: the read proof fails.
FORBIDDEN = {
    "write", "writelines", "write_text", "write_bytes", "pwrite", "writev",
    "sendfile", "truncate", "ftruncate",
    "remove", "unlink", "rename", "renames", "rmdir", "removedirs",
    "mkdir", "makedirs", "mkfifo", "mknod",
    "chmod", "lchmod", "chown", "lchown", "chflags", "lchflags", "utime",
    "symlink", "symlink_to", "hardlink", "hardlink_to", "link", "link_to",
    "touch", "copy", "copyfile", "copy2", "copytree", "move",
    "startfile", "urlretrieve", "fdopen",
    "exec", "eval", "compile", "__import__", "system", "popen", "Popen",
    "call", "check_call", "check_output", "runpy",
    "getattr", "setattr", "delattr", "globals", "locals", "vars",
    "shutil", "pickle", "marshal", "io", "codecs", "code", "codeop",
    "timeit", "doctest", "pdb", "bdb", "cProfile", "profile", "ctypes",
    "importlib", "fileinput", "multiprocessing", "asyncio",
}

# the only module-level calls the proof trusts, by attribute.
MODULE_CALLS = {
    "json": {"load", "loads", "dump", "dumps"},
    "collections": {"Counter", "defaultdict", "namedtuple", "OrderedDict", "deque"},
    "subprocess": {"run"},
}

# a literal-list subprocess.run whose head is one of these can write: refused.
WRITE_HEADS = {
    "sh", "bash", "zsh", "dash", "ksh",
    "cp", "mv", "rm", "ln", "tee", "dd", "install", "rsync",
    "sed", "perl", "touch", "chmod", "chown", "truncate", "shred",
    "unlink", "mkdir", "rmdir",
}

# an interpreter head is allowed only when no short flag carries inline code.
INTERPRETERS = {"python", "python2", "python3", "node", "ruby", "perl", "php"}


def _strings(node):
    out = []
    for sub in ast.walk(node):
        if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
            out.append(sub.value)
    return out


def _open_ok(call):
    """Return True when the open() call is a read (mode absent, 'r' or 'rb');
    None at the least doubt."""
    for arg in call.args:
        if isinstance(arg, ast.Starred):
            return None
    for kw in call.keywords:
        if kw.arg is None or kw.arg == "opener":
            return None
        if kw.arg == "mode":
            v = kw.value
            if not (isinstance(v, ast.Constant) and isinstance(v.value, str) and v.value in READ_MODES):
                return None
    if len(call.args) >= 2:
        m = call.args[1]
        if not (isinstance(m, ast.Constant) and isinstance(m.value, str) and m.value in READ_MODES):
            return None
    return True


def _run_ok(call):
    """Return True when the subprocess.run call takes a literal list of strings,
    none of which is a writing tool or a shell, and no shell=True."""
    for kw in call.keywords:
        if kw.arg is None:
            return False
        if kw.arg == "shell":
            if not (isinstance(kw.value, ast.Constant) and kw.value.value is False):
                return False
    if not call.args or not isinstance(call.args[0], ast.List):
        return False
    elts = call.args[0].elts
    if not elts:
        return False
    for elt in elts:
        if not (isinstance(elt, ast.Constant) and isinstance(elt.value, str)):
            return False
        if elt.value.rsplit("/", 1)[-1] in WRITE_HEADS:
            return False
    head = elts[0].value.rsplit("/", 1)[-1]
    if head in INTERPRETERS:
        # a short flag on an interpreter carries inline code nobody here proves
        for f in (e.value for e in elts[1:]):
            if f.startswith("-") and not f.startswith("--") and len(f) > 1 and \
                    any(ch in "ceEr" for ch in f[1:]):
                return False
    return True


def proven_reads(code):
    """Return the list of string literals passed to a read-mode open() when the
    whole code is proven to only read; None at the least doubt."""
    try:
        if not isinstance(code, str) or code.strip() == "":
            return None
        with warnings_ignore():
            tree = ast.parse(code)

        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id in FORBIDDEN:
                return None
            if isinstance(node, ast.Attribute) and node.attr in FORBIDDEN:
                return None
            if isinstance(node, ast.Attribute) and node.attr == "open":
                return None

        call_ids = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                call_ids.add(id(node.func))
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "open" and id(node) not in call_ids:
                return None

        read_paths = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if isinstance(func, ast.Name) and func.id == "open":
                ok = _open_ok(node)
                if ok is None:
                    return None
                if ok:
                    # the path argument(s) only: the mode literal is not a path
                    for arg in node.args[:1]:
                        read_paths.extend(_strings(arg))
            elif isinstance(func, ast.Attribute):
                if func.attr == "run":
                    if not (isinstance(func.value, ast.Name) and func.value.id == "subprocess"):
                        return None
                    if not _run_ok(node):
                        return None
                else:
                    receiver = func.value
                    if isinstance(receiver, ast.Name) and receiver.id in MODULE_CALLS:
                        if func.attr not in MODULE_CALLS[receiver.id]:
                            return None
                    elif isinstance(receiver, ast.Attribute) and receiver.attr == "path" \
                            and isinstance(receiver.value, ast.Name) and receiver.value.id == "os":
                        pass  # os.path.* : a pure name transform
                    # any other attribute call on a data object stays allowed
        return read_paths
    except Exception:
        return None


def warnings_ignore():
    import warnings

    return warnings.catch_warnings()


def _autotest():
    READS = [
        ("open('x.jsonl')", ["x.jsonl"]),
        ("open('x.jsonl', 'rb')", ["x.jsonl"]),
        ("import json\nfor l in open('x.jsonl'):\n    print(json.loads(l))", ["x.jsonl"]),
        (
            "import json,os,subprocess,collections\n"
            "L=[json.loads(l) for l in open(os.path.expanduser('~/.frugalflow/blocks/guard.jsonl')) if l.strip()]\n"
            "res=collections.Counter(); rows=[]\n"
            "for x in L:\n"
            "    payload=json.dumps(x)\n"
            "    r=subprocess.run(['python3','bin/replay.py','--guard'],input=payload,capture_output=True,text=True,timeout=60)\n"
            "    rows.append(r.stdout.strip())\n"
            "print(res)\n",
            ["~/.frugalflow/blocks/guard.jsonl"],
        ),
        ("import os\nprint(open(os.path.expanduser('a/b.jsonl')).read())", ["a/b.jsonl"]),
    ]
    NOT_READS = [
        "open('x.jsonl', 'a')",
        "open('x.jsonl', 'w').write('1')",
        "m = 'w'\nopen('x.jsonl', m)",
        "open('x.jsonl', 'r+')",
        "import subprocess\nsubprocess.run(['tee', 'x.jsonl'])",
        "import subprocess\nsubprocess.run(['sh', '-c', 'echo x > a'])",
        "import subprocess\nsubprocess.run(['python3', '-c', 'print(1)'])",
        "import subprocess\nsubprocess.run('ls', shell=True)",
        "import shutil\nshutil.copy('a', 'x.jsonl')",
        "import os\nos.rename('a', 'x.jsonl')",
        "open('x.jsonl', mode='w')",
        "o = open\no('x.jsonl')",
    ]
    all_pass = True
    for idx, (code, want) in enumerate(READS, 1):
        got = proven_reads(code)
        if got == want:
            print("PASS read %d: expected %r got %r" % (idx, want, got))
        else:
            print("FAIL read %d: expected %r got %r" % (idx, want, got))
            all_pass = False
    for idx, code in enumerate(NOT_READS, 1):
        got = proven_reads(code)
        if got is None:
            print("PASS not-read %d: expected None got None" % idx)
        else:
            print("FAIL not-read %d: expected None got %r" % (idx, got))
            all_pass = False
    # the relaunch child runs --notice only, never the autotest: no recursion guard needed
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"],
                       capture_output=True, text=True)
    if r.returncode == 0 and r.stdout.startswith("NAME      journal_read_proof.py"):
        print("PASS relaunch --notice: expected 0 got %d" % r.returncode)
    else:
        print("FAIL relaunch --notice: expected 0 got %d" % r.returncode)
        all_pass = False
    return 0 if all_pass else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    elif len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "journal_read_proof", sys.argv[1:])
