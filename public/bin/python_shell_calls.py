import ast
import sys

# 2026-11-12 (I1): python3 -c "import subprocess; subprocess.run(['git','reset','--hard'])"
# ran a destructive git command inside a vault while the guard judged the segment
# as code: a shell call made by literal arguments is a Bash command of its own.

SHELL_FUNCS = {
    "run", "call", "Popen", "check_call", "check_output", "system", "popen",
}
MODULE_OF = {
    "run": "subprocess", "call": "subprocess", "Popen": "subprocess",
    "check_call": "subprocess", "check_output": "subprocess",
    "system": "os", "popen": "os",
}


def _literal_str(node):
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    return None


def _literal_command(node):
    """Return the command text of a literal call argument: a literal string as
    it stands, a literal list of strings joined by spaces; None otherwise."""
    s = _literal_str(node)
    if s is not None:
        return s
    if isinstance(node, ast.List) and node.elts:
        words = []
        for el in node.elts:
            w = _literal_str(el)
            if w is None:
                return None
            words.append(w)
        return " ".join(words)
    return None


def _imports(tree):
    """Return (modules imported, names imported) of the code."""
    mods = set()
    names = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                mods.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                mods.add(node.module.split(".")[0])
            for a in node.names:
                names.add(a.name)
    return mods, names


def _call_name(node):
    """Return the function name a Call node runs, and its module when written
    dotted (subprocess.run -> ("run", "subprocess"); run -> ("run", None))."""
    if not isinstance(node, ast.Call):
        return None, None
    f = node.func
    if isinstance(f, ast.Name):
        return f.id, None
    if isinstance(f, ast.Attribute) and isinstance(f.value, ast.Name):
        return f.attr, f.value.id
    return None, None


def shell_calls(code):
    """Read Python code and return (commands, hidden).
    commands: the shell commands the code runs through subprocess.run/call/Popen/
    check_call/check_output, os.system, os.popen, when the argument is a literal
    string or a literal list of strings (the list joined by spaces).
    hidden: the number of such calls whose argument is not a literal - the
    command they run cannot be read. Unreadable code counts as one hidden call."""
    try:
        tree = ast.parse(code)
    except (SyntaxError, ValueError):
        return [], 1
    mods, names = _imports(tree)
    commands = []
    hidden = 0
    for node in ast.walk(tree):
        fname, mod = _call_name(node)
        if fname is None or fname not in SHELL_FUNCS:
            continue
        if mod is not None:
            if mod != MODULE_OF[fname]:
                continue
        else:
            # a bare name counts when the module it belongs to is imported
            if MODULE_OF[fname] not in mods and fname not in names:
                continue
        if not node.args:
            continue
        cmd = _literal_command(node.args[0])
        if cmd is None:
            hidden += 1
        else:
            commands.append(cmd)
    return commands, hidden


NOTICE = (
    "NAME      python_shell_calls.py - reads the shell commands a piece of Python code runs.\n"
    "READS     nothing: pure module; the caller passes the code text.\n"
    "WRITES    nothing: shell_calls() returns (literal commands, count of hidden calls).\n"
    "EXAMPLE   python3 python_shell_calls.py --notice\n"
    "PITFALLS  2026-11-12 (I1) subprocess.run(['git','reset','--hard']) in python -c ran a\n"
    "          destructive git command the guard never judged as a command.\n"
    "          2026-11-12 (I1) a call written with a bare name (from subprocess import run)\n"
    "          counts when the module is imported in the same code.\n"
)

if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--notice":
    sys.stdout.write(NOTICE)
    sys.exit(0)

if __name__ == "__main__" and "--autotest" in sys.argv:
    ok = True

    cmds, hidden = shell_calls("import subprocess; subprocess.run(['git','reset','--hard'])")
    if cmds != ["git reset --hard"] or hidden != 0:
        ok = False
    cmds, hidden = shell_calls("import subprocess; subprocess.call('git reset --hard', shell=True)")
    if cmds != ["git reset --hard"] or hidden != 0:
        ok = False
    cmds, hidden = shell_calls("import os; os.system('git reset --hard')")
    if cmds != ["git reset --hard"] or hidden != 0:
        ok = False
    cmds, hidden = shell_calls("import os; os.popen('git reset --hard')")
    if cmds != ["git reset --hard"] or hidden != 0:
        ok = False
    cmds, hidden = shell_calls("import subprocess; subprocess.Popen(['frugalflow','off'])")
    if cmds != ["frugalflow off"] or hidden != 0:
        ok = False
    cmds, hidden = shell_calls(
        "import subprocess\nsubprocess.check_call(['git','reset','--hard'])\n"
        "subprocess.check_output(['git','status'])\n")
    if cmds != ["git reset --hard", "git status"] or hidden != 0:
        ok = False
    # a non-literal argument is a hidden call
    cmds, hidden = shell_calls("import subprocess; subprocess.run(cmd)")
    if cmds != [] or hidden != 1:
        ok = False
    cmds, hidden = shell_calls("import subprocess; subprocess.run([x,'reset','--hard'])")
    if cmds != [] or hidden != 1:
        ok = False
    # a bare name counts when the module is imported
    cmds, hidden = shell_calls("from subprocess import run; run(['git','clean','-fdx'])")
    if cmds != ["git clean -fdx"] or hidden != 0:
        ok = False
    # a name that is not a shell call stays invisible
    cmds, hidden = shell_calls("def run(x):\n    return x\nrun(['git','reset','--hard'])")
    if cmds != [] or hidden != 0:
        ok = False
    # os.open is not os.system
    cmds, hidden = shell_calls("import os; os.open('f', 0)")
    if cmds != [] or hidden != 0:
        ok = False
    # plain code runs no shell command
    cmds, hidden = shell_calls("print(1)")
    if cmds != [] or hidden != 0:
        ok = False
    # unreadable code is one hidden call
    cmds, hidden = shell_calls("def (")
    if cmds != [] or hidden != 1:
        ok = False

    if ok:
        print("PASS python_shell_calls autotest")
        sys.exit(0)
    print("FAIL python_shell_calls autotest")
    sys.exit(1)

if __name__ == "__main__":
    sys.stdout.write("usage: python_shell_calls.py --notice | --autotest\n")
    sys.exit(2)
