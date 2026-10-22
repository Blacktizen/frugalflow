"""List harmless string literals in Python source code."""
import ast
import os
import subprocess
import sys
import warnings

RUN_FUNCS = ("run", "call", "check_call", "check_output", "Popen")
TEMP_FUNCS = ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile", "mkstemp", "mkdtemp", "TemporaryDirectory")
TEMP_FILE_FUNCS = ("NamedTemporaryFile", "TemporaryFile", "SpooledTemporaryFile")


def _tempfile_call(node, attrs):
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Attribute)
        and node.func.attr in attrs
        and isinstance(node.func.value, ast.Name)
        and node.func.value.id == "tempfile"
    )


def _const_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _safe_join_component(value):
    # a path component joined under a directory: it must not be absolute nor climb up
    return value != "" and not value.startswith("/") and ".." not in value.split("/")


def _safe_add_component(value):
    # a suffix appended verbatim to a path: it must not climb up a directory level
    return value != "" and ".." not in value.split("/")


def _is_os_path(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "path"
        and isinstance(node.value, ast.Name)
        and node.value.id == "os"
    )


def _is_pathlib_path(node):
    return (
        isinstance(node, ast.Attribute)
        and node.attr == "Path"
        and isinstance(node.value, ast.Name)
        and node.value.id == "pathlib"
    )


def trusted_tempfile(tree):
    """The name tempfile means the module, not a rebound name."""
    has_import = False
    rebound = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == "tempfile":
                    has_import = True
        elif isinstance(node, ast.Name) and node.id == "tempfile" and isinstance(node.ctx, (ast.Store, ast.Del)):
            rebound = True
    return has_import and not rebound


def safe_temp_path(node, names, trusted=False):
    """True when node is a path that provably stays inside the temporary zone."""
    if isinstance(node, ast.Name):
        return node.id in names
    # the path of a file returned by tempfile (f.name) is the returned file itself
    if isinstance(node, ast.Attribute) and node.attr == "name" and isinstance(node.value, ast.Name) and node.value.id in names:
        return True
    if isinstance(node, ast.Call):
        func = node.func
        if trusted and _tempfile_call(node, ("mkdtemp", "TemporaryDirectory")):
            return True
        if isinstance(func, ast.Attribute) and func.attr == "join" and _is_os_path(func.value):
            base, rest = (node.args[0], node.args[1:]) if node.args else (None, [])
            if base is None or not safe_temp_path(base, names, trusted):
                return False
            for arg in rest:
                value = _const_str(arg)
                if value is None or not _safe_join_component(value):
                    return False
            return True
        if isinstance(func, ast.Attribute) and func.attr == "joinpath":
            base, rest = func.value, node.args
            if not safe_temp_path(base, names, trusted):
                return False
            for arg in rest:
                value = _const_str(arg)
                if value is None or not _safe_join_component(value):
                    return False
            return True
        if (isinstance(func, ast.Name) and func.id == "Path") or _is_pathlib_path(func):
            if not node.args or not safe_temp_path(node.args[0], names, trusted):
                return False
            for arg in node.args[1:]:
                value = _const_str(arg)
                if value is None or not _safe_join_component(value):
                    return False
            return True
    if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Add, ast.Div)):
        if not safe_temp_path(node.left, names, trusted):
            return False
        value = _const_str(node.right)
        if value is None:
            return False
        if isinstance(node.op, ast.Add):
            return _safe_add_component(value)
        return _safe_join_component(value)
    if isinstance(node, ast.JoinedStr):
        if not node.values:
            return False
        first = node.values[0]
        if not (isinstance(first, ast.FormattedValue) and safe_temp_path(first.value, names, trusted)):
            return False
        for part in node.values[1:]:
            value = _const_str(part)
            if value is None or not _safe_add_component(value):
                return False
        return True
    return False


def temp_names(tree):
    """Names bound to a path inside the temporary zone, including paths built under one."""
    trusted = trusted_tempfile(tree)
    site_nodes = set()
    binding_sites = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    site_nodes.add(id(target))
                    binding_sites.setdefault(target.id, []).append(node.value)
                elif isinstance(target, (ast.Tuple, ast.List)) and trusted and _tempfile_call(node.value, ("mkstemp",)):
                    for el in target.elts:
                        if isinstance(el, ast.Name):
                            site_nodes.add(id(el))
                            binding_sites.setdefault(el.id, []).append(("__mkstemp__",))
        elif isinstance(node, (ast.With, ast.AsyncWith)):
            for item in node.items:
                if isinstance(item.optional_vars, ast.Name):
                    site_nodes.add(id(item.optional_vars))
                    binding_sites.setdefault(item.optional_vars.id, []).append(item.context_expr)

    conflicts = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, (ast.Store, ast.Del)) and id(node) not in site_nodes:
            conflicts.add(node.id)
        if isinstance(node, ast.alias):
            conflicts.add(node.asname or node.name.split(".")[0])
        if isinstance(node, ast.arg):
            conflicts.add(node.arg)

    def is_temp_value(value):
        if isinstance(value, tuple) and value and value[0] == "__mkstemp__":
            return True
        if trusted and _tempfile_call(value, ("mkdtemp", "TemporaryDirectory")):
            return True
        # a file object returned by tempfile is itself in the temporary zone (f, and its path f.name)
        if trusted and _tempfile_call(value, TEMP_FILE_FUNCS):
            return True
        return safe_temp_path(value, names, trusted)

    names = set()
    changed = True
    while changed:
        changed = False
        for name, values in binding_sites.items():
            if name in conflicts or name in names:
                continue
            if values and all(is_temp_value(v) for v in values):
                names.add(name)
                changed = True
    return names


def benign_literals(code):
    if not isinstance(code, str):
        return set()
    try:
        # judged code holding an invalid escape makes ast.parse emit a
        # SyntaxWarning; the silence is local to this parse, nothing else changes.
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", SyntaxWarning)
            tree = ast.parse(code)
    except Exception:
        return set()

    benign = set()

    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            func_name = ""
            if isinstance(node.func, ast.Attribute):
                func_name = node.func.attr
            elif isinstance(node.func, ast.Name):
                func_name = node.func.id

            if func_name in RUN_FUNCS and node.args:
                head = node.args[0]
                while isinstance(head, ast.BinOp) and isinstance(head.op, ast.Add):
                    head = head.left

                if isinstance(head, (ast.List, ast.Tuple)) and len(head.elts) >= 2:
                    first = head.elts[0]
                    second = head.elts[1]

                    first_ok = False
                    if isinstance(first, ast.Attribute) and first.attr == "executable" and isinstance(first.value, ast.Name) and first.value.id == "sys":
                        first_ok = True
                    elif isinstance(first, ast.Constant) and isinstance(first.value, str):
                        if os.path.basename(first.value).startswith("python"):
                            first_ok = True

                    if first_ok and isinstance(second, ast.Constant) and isinstance(second.value, str) and not second.value.startswith("-"):
                        benign.add(id(second))

            if func_name in TEMP_FUNCS:
                for kw in node.keywords:
                    if kw.arg in ("suffix", "prefix") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                        benign.add(id(kw.value))

    # a path joined under a temporary directory (mkdtemp/TemporaryDirectory)
    # or the file returned by mkstemp is outside the project: its string parts are harmless.
    temp = temp_names(tree)
    if temp:
        trusted = trusted_tempfile(tree)
        for node in ast.walk(tree):
            if safe_temp_path(node, temp, trusted):
                for sub in ast.walk(node):
                    if isinstance(sub, ast.Constant) and isinstance(sub.value, str):
                        benign.add(id(sub))

    total = {}
    good = {}

    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            value = node.value
            total[value] = total.get(value, 0) + 1
            if id(node) in benign:
                good[value] = good.get(value, 0) + 1

    result = set()
    for value, count_total in total.items():
        if good.get(value, 0) == count_total and code.count(value) == count_total and value != "":
            result.add(value)

    return result


def _print_usage():
    print("usage: python_literal_roles.py --notice | --autotest")


def _print_notice():
    script_name = os.path.basename(__file__)
    sys.stdout.write(
        "NAME      python_literal_roles.py - lists the string literals of Python code whose every use is harmless: the script path run by the Python interpreter, the suffix or prefix of a temporary file, a path joined under a temporary directory, or a path built on the name of a returned temporary file (f.name).\n"
        "READS     the Python code it is given; nothing on disk.\n"
        "WRITES    nothing: benign_literals() returns a set of strings.\n"
        f"EXAMPLE   python3 {script_name} --autotest\n"
        "PITFALLS  2026-10-03 a literal is harmless only if ALL its uses are: the same name opened for writing, passed as a later argument, or hidden inside another string keeps it suspect; a tempfile path is harmless only while no component climbs out of it.\n"
        "          2026-10-14 a judged code holding an invalid escape made ast.parse print a SyntaxWarning on every call: warnings are silenced around the parse only.\n"
    )


CASES = [
    ("import subprocess, sys\nsubprocess.run([sys.executable, 'bin/tool.py', '--autotest'])\n", {'bin/tool.py'}),
    ("import tempfile\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\n", {'.py'}),
    ("import subprocess, sys\nsubprocess.run([sys.executable, 'gen.py', '--out', 'src/new.py'])\n", {'gen.py'}),
    ("import subprocess, sys\nopen('tool.py', 'w')\nsubprocess.run([sys.executable, 'tool.py'])\n", set()),
    ("import subprocess, sys\nsubprocess.run([sys.executable, '-c', 'open(\"x.py\", \"w\")'])\nsubprocess.run([sys.executable, 'x.py'])\n", set()),
    ("import subprocess\nsubprocess.run(['python3', 'a.py'])\n", {'a.py'}),
    ("import subprocess\nsubprocess.run(['bash', 'a.py'])\n", set()),
    ("import os\nos.system('python3 a.py')\n", set()),
    ("def (", set()),
    ("import subprocess, sys\nsubprocess.run([sys.executable, 'r.py'] + ['-x'] + more)\n", {'r.py'}),
]


def _call_benign(source):
    try:
        return benign_literals(source)
    except Exception as exc:
        return f"<exception {exc!r}>"


def _run_test_group(test_number, case_indices, extra_cases=()):
    expected = []
    got = []

    for case_index in case_indices:
        source, expected_result = CASES[case_index]
        result = _call_benign(source)
        expected.append(expected_result)
        got.append(result)

    for source, expected_result in extra_cases:
        result = _call_benign(source)
        expected.append(expected_result)
        got.append(result)

    ok = True
    for result in got:
        if not isinstance(result, set):
            ok = False
            break

    if ok:
        ok = all(result == expected_item for result, expected_item in zip(got, expected))

    status = "PASS" if ok else "FAIL"
    print(f"{status} test {test_number} expected={expected!r} got={got!r}")
    return ok


def _run_test_5():
    expected_desc = "returncode=0 and stdout starts with 'NAME      python_literal_roles.py'"
    try:
        completed = subprocess.run(
            [sys.executable, __file__, "--notice"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        got_stdout = completed.stdout
        got_desc = f"returncode={completed.returncode} stdout_prefix={got_stdout[:len('NAME      python_literal_roles.py')]!r}"
        ok = completed.returncode == 0 and got_stdout.startswith("NAME      python_literal_roles.py")
    except Exception as exc:
        got_desc = f"exception={exc!r}"
        ok = False

    status = "PASS" if ok else "FAIL"
    print(f"{status} test 5 expected={expected_desc} got={got_desc}")
    return ok


def _run_test_6():
    extra = [
        ("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, 'a.py'), 'w')", {'a.py'}),
        ("import tempfile, os\nwith tempfile.TemporaryDirectory() as d:\n    open(os.path.join(d, 'a.py'), 'w')", {'a.py'}),
        ("import tempfile, os\nd = tempfile.mkdtemp()\nopen(os.path.join(d, '..', 'x.py'), 'w')", set()),
        ("import tempfile\nfrom pathlib import Path\nd = tempfile.mkdtemp()\n(Path(d) / 'a.py').write_text('x')", {'a.py'}),
        ("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nopen(os.path.join(f.name, 'a.py'), 'w')", {'a.py'}),
        ("import tempfile, os\nf = tempfile.NamedTemporaryFile('w', suffix='.py', delete=False)\nopen(os.path.join(f.name, '..', 'x.py'), 'w')", set()),
    ]
    return _run_test_group(6, [], extra)


def _run_self_test():
    ok = _run_test_group(1, [0, 1])
    ok = _run_test_group(2, [2, 3]) and ok
    ok = _run_test_group(3, [4, 5]) and ok
    ok = _run_test_group(4, [6, 7, 8, 9], [(None, set())]) and ok
    ok = _run_test_5() and ok
    ok = _run_test_6() and ok
    return ok


def main(argv):
    if argv == ["--notice"]:
        _print_notice()
        return 0
    if argv == ["--autotest"]:
        return 0 if _run_self_test() else 1
    _print_usage()
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "python_literal_roles", sys.argv[1:])
