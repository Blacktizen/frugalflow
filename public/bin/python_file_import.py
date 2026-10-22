"""python_file_import.py - rewrites Python code that loads a local module by its path into a form the read proof can judge."""

import ast
import os
import subprocess
import sys
import warnings


def rewrite(code):
    """Rewrite importlib-based module loading into open() and file_imports calls."""
    try:
        if not isinstance(code, str):
            return code

        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            try:
                tree = ast.parse(code)
            except SyntaxError:
                return code

        parents = {}
        for node in ast.walk(tree):
            for child in ast.iter_child_nodes(node):
                parents[id(child)] = node

        # Control a: reject any ast.ImportFrom for importlib
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and isinstance(node.module, str):
                if node.module == "importlib" or node.module.startswith("importlib."):
                    return code

        # Control b: import importlib aliases must have asname None
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "importlib" or alias.name.startswith("importlib."):
                        if alias.asname is not None:
                            return code

        # Control c: every Name "importlib" must sit in the expected chain
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "importlib":
                a = parents.get(id(node))
                b = parents.get(id(a)) if a is not None else None
                c = parents.get(id(b)) if b is not None else None
                if not (isinstance(a, ast.Attribute) and a.value is node and a.attr == "util"):
                    return code
                if not (isinstance(b, ast.Attribute) and b.value is a and b.attr in ("spec_from_file_location", "module_from_spec")):
                    return code
                if not (isinstance(c, ast.Call) and c.func is b):
                    return code

        # Control d: spec_from_file_location calls must have 2 args, no keywords, string path, non-stdlib stem
        has_spec_call = False
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "importlib":
                a = parents.get(id(node))
                b = parents.get(id(a)) if a is not None else None
                c = parents.get(id(b)) if b is not None else None
                if (isinstance(a, ast.Attribute) and a.value is node and a.attr == "util"
                        and isinstance(b, ast.Attribute) and b.value is a and b.attr == "spec_from_file_location"
                        and isinstance(c, ast.Call) and c.func is b):
                    if len(c.args) != 2 or len(c.keywords) != 0:
                        return code
                    if not (isinstance(c.args[1], ast.Constant) and isinstance(c.args[1].value, str)):
                        return code
                    stem = os.path.splitext(os.path.basename(c.args[1].value))[0]
                    if stem in sys.stdlib_module_names:
                        return code
                    has_spec_call = True

        # Control e: module_from_spec calls must have 1 arg, no keywords
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and node.id == "importlib":
                a = parents.get(id(node))
                b = parents.get(id(a)) if a is not None else None
                c = parents.get(id(b)) if b is not None else None
                if (isinstance(a, ast.Attribute) and a.value is node and a.attr == "util"
                        and isinstance(b, ast.Attribute) and b.value is a and b.attr == "module_from_spec"
                        and isinstance(c, ast.Call) and c.func is b):
                    if len(c.args) != 1 or len(c.keywords) != 0:
                        return code

        # Control f: every exec_module attribute must be a valid call
        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and node.attr == "exec_module":
                call = parents.get(id(node))
                if not (isinstance(call, ast.Call) and call.func is node):
                    return code
                if len(call.args) != 1 or len(call.keywords) != 0:
                    return code
                if not (isinstance(node.value, ast.Attribute) and node.value.attr == "loader"):
                    return code
                if not isinstance(node.value.value, ast.Name):
                    return code

        # Control g: at least one spec_from_file_location must be present
        if not has_spec_call:
            return code

        # Rewrite via NodeTransformer
        class Transformer(ast.NodeTransformer):
            def visit_Import(self, node):
                kept = [a for a in node.names if a.name != "importlib" and not a.name.startswith("importlib.")]
                if not kept:
                    return ast.Pass()
                node.names = kept
                return node

            def visit_Call(self, node):
                self.generic_visit(node)
                if (isinstance(node.func, ast.Attribute) and node.func.attr == "spec_from_file_location"
                        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "util"
                        and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "importlib"):
                    path = node.args[1].value
                    return ast.Call(
                        func=ast.Name(id="open", ctx=ast.Load()),
                        args=[ast.Constant(value=path)],
                        keywords=[])
                if (isinstance(node.func, ast.Attribute) and node.func.attr == "module_from_spec"
                        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "util"
                        and isinstance(node.func.value.value, ast.Name) and node.func.value.value.id == "importlib"):
                    return ast.Call(
                        func=ast.Attribute(value=ast.Name(id="file_imports", ctx=ast.Load()), attr="module", ctx=ast.Load()),
                        args=node.args,
                        keywords=[])
                if isinstance(node.func, ast.Attribute) and node.func.attr == "exec_module":
                    return ast.Call(
                        func=ast.Attribute(value=ast.Name(id="file_imports", ctx=ast.Load()), attr="run", ctx=ast.Load()),
                        args=node.args,
                        keywords=[])
                return node

        tree = Transformer().visit(tree)

        # Insert import file_imports after leading __future__ imports
        k = 0
        while k < len(tree.body) and isinstance(tree.body[k], ast.ImportFrom) and tree.body[k].module == "__future__":
            k += 1
        tree.body.insert(k, ast.Import(names=[ast.alias(name="file_imports")]))

        return ast.unparse(ast.fix_missing_locations(tree))
    except Exception:
        return code


NOTICE = (
    "NAME      python_file_import.py - rewrites Python code that loads a local module by its path (importlib spec_from_file_location) into a form the read proof can judge: the load becomes open(path), the module a third party import.\n"
    "READS     nothing: pure module; it works on the code text only and never runs it.\n"
    "WRITES    nothing: rewrite() returns the new code, or the code unchanged at the least doubt; --rewrite prints it.\n"
    "EXAMPLE   python3 python_file_import.py --rewrite \"import importlib.util\"\n"
    "PITFALLS  2026-09-27 a heredoc that loaded bounded_output.py to print its verdicts was refused as a write; a module of the standard library loaded by path is never rewritten."
)


def main():
    if len(sys.argv) < 2:
        print("usage: python_file_import.py --rewrite CODE | --notice | --autotest")
        sys.exit(2)

    cmd = sys.argv[1]

    if cmd == "--notice":
        print(NOTICE)
        sys.exit(0)

    elif cmd == "--rewrite":
        if len(sys.argv) < 3:
            print("usage: python_file_import.py --rewrite CODE | --notice | --autotest")
            sys.exit(2)
        code = sys.argv[2]
        new = rewrite(code)
        print(new)
        sys.exit(0 if new != code else 1)

    elif cmd == "--autotest":
        L = "import importlib.util\ns = importlib.util.spec_from_file_location('b', '%s')\nm = importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\n"
        F1 = L % "tool.py" + "print(m.judge('ls'))"
        O1 = "import file_imports\npass\ns = open('tool.py')\nm = file_imports.module(s)\nfile_imports.run(m)\nprint(m.judge('ls'))"
        F2 = L % "/usr/lib/python3.12/shutil.py" + "m.copyfile('x', 'y')"
        O2 = F2
        F3 = "import importlib.util as u\ns = u.spec_from_file_location('b', 'tool.py')"
        O3 = F3
        F4 = "import json, importlib.util\ns = importlib.util.spec_from_file_location('b', 'bin/x.py')\nm = importlib.util.module_from_spec(s)\ns.loader.exec_module(m)\nprint(json.dumps(m.f()))"
        O4 = "import file_imports\nimport json\ns = open('bin/x.py')\nm = file_imports.module(s)\nfile_imports.run(m)\nprint(json.dumps(m.f()))"
        F5 = "import importlib\nimportlib.import_module('os')"
        O5 = F5

        tests = [
            (F1, O1, 0),
            (F2, O2, 1),
            (F3, O3, 1),
            (F4, O4, 0),
            (F5, O5, 1),
        ]

        all_pass = True
        for i, (fi, oi, expected_rc) in enumerate(tests, 1):
            result = subprocess.run(
                [sys.executable, __file__, "--rewrite", fi],
                capture_output=True, text=True
            )
            stdout = result.stdout.rstrip("\n")
            rc = result.returncode
            if stdout == oi and rc == expected_rc:
                print("PASS %d expected rc=%d got rc=%d" % (i, expected_rc, rc))
            else:
                print("FAIL %d expected rc=%d got rc=%d" % (i, expected_rc, rc))
                all_pass = False

        sys.exit(0 if all_pass else 1)

    else:
        print("usage: python_file_import.py --rewrite CODE | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "python_file_import", sys.argv[1:])
