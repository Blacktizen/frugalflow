#!/usr/bin/env python3
"""Check cross-cutting conventions of a kata project by AST analysis."""

import argparse
import ast
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT = os.path.abspath(__file__)


def is_noise(stmt):
    """True if the statement is only blank-like content: pass, ellipsis, docstring, stub def."""
    if isinstance(stmt, ast.Pass):
        return True
    if isinstance(stmt, ast.Expr):
        value = stmt.value
        if isinstance(value, ast.Constant):
            if value.value is Ellipsis or isinstance(value.value, str):
                return True
        return False
    if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return all(is_noise(s) for s in stmt.body)
    return False


def raises_value_error(node):
    exc = node.exc
    if isinstance(exc, ast.Name) and exc.id == "ValueError":
        return True
    if isinstance(exc, ast.Call) and isinstance(exc.func, ast.Name) and exc.func.id == "ValueError":
        return True
    return False


def check_t1(tree):
    uses_fail = False
    imports_fail = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Raise) and raises_value_error(node):
            return False
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id == "fail":
            uses_fail = True
        if isinstance(node, ast.ImportFrom) and any(a.name == "fail" for a in node.names):
            if node.module == "kata.common" or (node.module == "common" and node.level >= 1):
                imports_fail = True
    if uses_fail and not imports_fail:
        return False
    return True


def public_functions(tree):
    funcs = []
    for stmt in tree.body:
        if isinstance(stmt, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not stmt.name.startswith("_"):
                funcs.append(stmt)
        elif isinstance(stmt, ast.ClassDef):
            for sub in stmt.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    if not sub.name.startswith("_"):
                        funcs.append(sub)
    return funcs


def fully_annotated(fn):
    args = fn.args
    params = list(args.posonlyargs) + list(args.args) + list(args.kwonlyargs)
    if args.vararg is not None:
        params.append(args.vararg)
    if args.kwarg is not None:
        params.append(args.kwarg)
    for p in params:
        if p.arg in ("self", "cls"):
            continue
        if p.annotation is None:
            return False
    return fn.returns is not None


def check_t2(tree):
    funcs = public_functions(tree)
    if not funcs:
        return True
    return all(fully_annotated(fn) for fn in funcs)


def check_t3(tree, slug):
    doc = ast.get_docstring(tree)
    if doc is None:
        return False
    lines = doc.splitlines()
    if not lines:
        return False
    return lines[0] == "Kata: " + slug


def check_t4(tree):
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.name.split(".")[0] in ("re", "regex"):
                    return False
        elif isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if module.split(".")[0] in ("re", "regex"):
                return False
    return True


def analyze_module(path, slug):
    res = {"delivered": False, "t1": False, "t2": False, "t3": False, "t4": False, "ok": False}
    if not os.path.isfile(path):
        return res
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return res
    res["delivered"] = any(not is_noise(s) for s in tree.body)
    if not res["delivered"]:
        return res
    res["t1"] = check_t1(tree)
    res["t2"] = check_t2(tree)
    res["t3"] = check_t3(tree, slug)
    res["t4"] = check_t4(tree)
    res["ok"] = res["t1"] and res["t2"] and res["t3"] and res["t4"]
    return res


def check_common_fail(project):
    path = os.path.join(project, "kata", "common.py")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (SyntaxError, UnicodeDecodeError, ValueError):
        return False
    for stmt in tree.body:
        if not isinstance(stmt, ast.FunctionDef) or stmt.name != "fail":
            continue
        args = stmt.args
        params = list(args.posonlyargs) + list(args.args)
        if len(params) != 1 or args.vararg or args.kwonlyargs or args.kwarg:
            continue
        p = params[0]
        if p.arg != "message":
            continue
        if not isinstance(p.annotation, ast.Name) or p.annotation.id != "str":
            continue
        if not isinstance(stmt.returns, ast.Name) or stmt.returns.id != "NoReturn":
            continue
        for node in ast.walk(stmt):
            if isinstance(node, ast.Raise) and raises_value_error(node):
                return True
        return False
    return False


def check_t5(project, hashes):
    tests_intact = True
    for rel, digest in hashes.items():
        path = os.path.join(project, rel)
        if not os.path.isfile(path):
            tests_intact = False
            continue
        with open(path, "rb") as fh:
            data = fh.read()
        if hashlib.sha256(data).hexdigest() != digest:
            tests_intact = False
    return {"common_fail_ok": check_common_fail(project), "tests_intact": tests_intact}


def analyze(project, slugs, hashes):
    kata_dir = os.path.join(project, "kata")
    if slugs is not None:
        names = sorted(slugs)
    else:
        names = []
        if os.path.isdir(kata_dir):
            for fname in sorted(os.listdir(kata_dir)):
                if fname.endswith(".py") and fname not in ("__init__.py", "common.py"):
                    names.append(fname[:-3])
    modules = {}
    for name in names:
        slug = slugs[name] if slugs is not None else name.replace("_", "-")
        modules[name] = analyze_module(os.path.join(kata_dir, name + ".py"), slug)
    delivered = sum(1 for m in modules.values() if m["delivered"])
    conformes = sum(1 for m in modules.values() if m["ok"])
    out = {"modules": modules, "summary": {"conformes": conformes, "delivered": delivered}}
    if hashes is not None:
        out["t5"] = check_t5(project, hashes)
    return out


OK_MODULE = (
    "\"\"\"Kata: x-y\n\n"
    "Solve the puzzle.\n"
    "\"\"\"\n"
    "from kata.common import fail\n"
    "\n"
    "\n"
    "def solve(n: int) -> int:\n"
    "    if n < 0:\n"
    "        fail(\"negative n\")\n"
    "    return n\n"
)

BAD_RAISE = (
    "\"\"\"Kata: a-b\n\"\"\"\n"
    "\n"
    "\n"
    "def boom(n: int) -> None:\n"
    "    raise ValueError(\"bad\")\n"
)

BAD_RE = (
    "\"\"\"Kata: c-d\n\"\"\"\n"
    "import re\n"
    "\n"
    "\n"
    "def loose(x):\n"
    "    return re.match(\"a\", x)\n"
)

STUB = "def f():\n    pass\n"


def write_project(files):
    root = tempfile.mkdtemp(prefix="kata_autotest_")
    for rel, content in files.items():
        path = os.path.join(root, rel)
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(content)
    return root


def run_check(root, extra=None):
    cmd = [sys.executable, "-I", SCRIPT, root]
    if extra:
        cmd.extend(extra)
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        data = json.loads(proc.stdout)
    except ValueError:
        data = None
    return proc.returncode, data


def test_1():
    root = write_project({"kata/x_y.py": OK_MODULE})
    try:
        code, data = run_check(root)
        got = data["modules"]["x_y"]["ok"] if data else None
        passed = code == 0 and got is True
        return ("epreuve1_conforme", "ok=True exit=0", "ok=%s exit=%s" % (got, code), passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_2():
    root = write_project({"kata/a_b.py": BAD_RAISE})
    try:
        code, data = run_check(root)
        got = data["modules"]["a_b"]["t1"] if data else None
        passed = code == 0 and got is False
        return ("epreuve2_raise_valueerror", "t1=False", "t1=%s exit=%s" % (got, code), passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_3():
    root = write_project({"kata/c_d.py": BAD_RE})
    try:
        code, data = run_check(root)
        t4 = data["modules"]["c_d"]["t4"] if data else None
        t2 = data["modules"]["c_d"]["t2"] if data else None
        passed = code == 0 and t4 is False and t2 is False
        return ("epreuve3_import_re_non_annote", "t4=False t2=False", "t4=%s t2=%s exit=%s" % (t4, t2, code), passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_4():
    root = write_project({"kata/s_t.py": STUB})
    try:
        code, data = run_check(root)
        got = data["modules"]["s_t"]["delivered"] if data else None
        passed = code == 0 and got is False
        return ("epreuve4_stub", "delivered=False", "delivered=%s exit=%s" % (got, code), passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_autotest():
    tests = [test_1(), test_2(), test_3(), test_4()]
    all_ok = True
    for name, expected, obtained, passed in tests:
        if not passed:
            all_ok = False
        tag = "PASS" if passed else "FAIL"
        print("%s %s attendu=%s obtenu=%s" % (tag, name, expected, obtained))
    return 0 if all_ok else 1


def main():
    parser = argparse.ArgumentParser(prog="check_rules.py")
    parser.add_argument("project", nargs="?")
    parser.add_argument("--hashes")
    parser.add_argument("--slugs-json")
    parser.add_argument("--autotest", action="store_true")
    args = parser.parse_args()
    if args.autotest:
        sys.exit(run_autotest())
    if args.project is None:
        parser.error("PROJECT requis")
    slugs = None
    if args.slugs_json:
        with open(args.slugs_json, encoding="utf-8") as fh:
            slugs = json.load(fh)
    hashes = None
    if args.hashes:
        with open(args.hashes, encoding="utf-8") as fh:
            hashes = json.load(fh)
    result = analyze(args.project, slugs, hashes)
    print(json.dumps(result, sort_keys=True, indent=1))


if __name__ == "__main__":
    main()
