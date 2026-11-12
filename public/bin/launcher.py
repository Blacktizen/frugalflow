import os
import shlex
import shutil
import subprocess
import sys


NOTICE = (
    "NAME      launcher.py - builds the shell command that runs a FrugalFlow tool from a hook, and recognizes such a command.\n"
    "READS     nothing from disk: the bin folder and the python path it is given, and the PATH through shutil.which.\n"
    "WRITES    nothing: command() returns text, names_tool() returns true or false.\n"
    "EXAMPLE   python3 launcher.py --notice\n"
    "PITFALLS  2026-10-25 hooks held the absolute path of the clone, so moving or deleting it broke every hook without a word; the command name or the installed package is used first.\n"
    "          2026-11-12 a hook command without -I let python run a .pth file planted in the user site-packages before the guard; every command now carries -I right after the interpreter.\n"
)


def installed(bin_dir):
    parts = os.path.normpath(bin_dir).split(os.sep)
    for part in parts:
        if part == "site-packages" or part == "dist-packages":
            return True
    return False


def shebang_python(script_path):
    """Return the interpreter named on the shebang line of an installed script, or None."""
    try:
        with open(script_path, "r", encoding="utf-8", errors="replace") as handle:
            first = handle.readline()
    except OSError:
        return None
    if not first.startswith("#!"):
        return None
    fields = first[2:].strip().split()
    if not fields:
        return None
    head = fields[0]
    if os.path.basename(head) == "env" and len(fields) > 1:
        head = fields[1]  # shebang form: /usr/bin/env python3
    if os.sep in head:
        return head
    return shutil.which(head)


def command(bin_dir, python, tool, which=None):
    name = tool
    if name.endswith(".py"):
        name = name[:-3]
    if which is None:
        which = shutil.which
    found = which("frugalflow")
    if found:
        # -I right after the interpreter: python must not run a .pth file or a
        # usercustomize.py planted in the user site-packages before the guard.
        # The console script runs with its own shebang interpreter, so an
        # install inside a virtualenv keeps working under -I.
        interp = shebang_python(found) or python
        return shlex.quote(interp) + " -I " + shlex.quote(found) + " run " + name
    if installed(bin_dir):
        return shlex.quote(python) + " -I -m frugalflow_app.bin.frugalflow run " + name
    return shlex.quote(python) + " -I " + shlex.quote(os.path.join(bin_dir, name + ".py"))


def _tool_index(parts):
    """Return the index of the token naming the script or the console script,
    past the interpreter options (-I, -u, ...) but not past -m or -c."""
    idx = 0
    if "python" in os.path.basename(parts[0]).casefold():
        idx = 1
        while idx < len(parts) and parts[idx].startswith("-") and parts[idx] not in ("-m", "-c"):
            idx += 1
    return idx


def names_tool(command_text, tool, bin_dir):
    name = tool
    if name.endswith(".py"):
        name = name[:-3]
    try:
        parts = shlex.split(command_text)
    except ValueError:
        return False
    if len(parts) < 2:
        return False
    idx = _tool_index(parts)
    if idx >= len(parts):
        return False
    # Console script form, old (bare name) and new (interpreter, -I, path).
    if os.path.basename(parts[idx]) == "frugalflow" and parts[idx + 1:idx + 3] == ["run", name]:
        return True
    if parts[idx] == "-m" and parts[idx + 1:idx + 4] == ["frugalflow_app.bin.frugalflow", "run", name]:
        return True
    target = os.path.normpath(os.path.join(bin_dir, name + ".py"))
    if os.path.normpath(parts[idx]) == target:
        return True
    return False


def is_frugalflow_command(command_text, bin_dir):
    """Return True when this command runs a FrugalFlow tool, whatever its name."""
    try:
        parts = shlex.split(command_text)
    except ValueError:
        return False
    if len(parts) < 2:
        return False
    idx = _tool_index(parts)
    if idx >= len(parts):
        return False
    if os.path.basename(parts[idx]) == "frugalflow" and idx + 1 < len(parts) and parts[idx + 1] == "run":
        return True
    if parts[idx] == "-m" and idx + 1 < len(parts) and parts[idx + 1] == "frugalflow_app.bin.frugalflow":
        return True
    if parts[idx].endswith(".py") and os.path.dirname(os.path.normpath(parts[idx])) == os.path.normpath(bin_dir):
        return True
    return False


def entry_point_hint():
    return "frugalflow run <tool>"


def run_autotest():
    fixture_run_hook = "frugalflow run guard_hook --hook"
    fixture_run_other = "frugalflow run other_tool"
    fixture_runner = "frugalflow runner guard_hook"

    bin_dir_1 = "/opt/ff/bin"
    expected_1 = "/usr/bin/python3 -I /usr/local/bin/frugalflow run guard_hook"
    got_1 = command(bin_dir_1, "/usr/bin/python3", "guard_hook.py", which=lambda n: "/usr/local/bin/frugalflow")
    pass_1 = got_1 == expected_1
    if pass_1:
        print("PASS 1 AUTOTEST 5/5 expected=" + expected_1 + " got=" + got_1)
    else:
        print("FAIL 1 AUTOTEST 5/5 expected=" + expected_1 + " got=" + got_1)

    bin_dir_2 = "/opt/pipx/venvs/frugalflow/lib/python3.12/site-packages/frugalflow_app/bin"
    expected_2 = "/opt/venv/bin/python -I -m frugalflow_app.bin.frugalflow run statusline"
    got_2 = command(bin_dir_2, "/opt/venv/bin/python", "statusline", which=lambda n: None)
    pass_2 = got_2 == expected_2
    if pass_2:
        print("PASS 2 AUTOTEST 5/5 expected=" + expected_2 + " got=" + got_2)
    else:
        print("FAIL 2 AUTOTEST 5/5 expected=" + expected_2 + " got=" + got_2)

    bin_dir_3 = "/tmp/my clone/bin"
    expected_3 = "/usr/bin/python3 -I '/tmp/my clone/bin/session_log.py'"
    got_3 = command(bin_dir_3, "/usr/bin/python3", "session_log.py", which=lambda n: None)
    pass_3 = got_3 == expected_3
    if pass_3:
        print("PASS 3 AUTOTEST 5/5 expected=" + expected_3 + " got=" + got_3)
    else:
        print("FAIL 3 AUTOTEST 5/5 expected=" + expected_3 + " got=" + got_3)

    checks_4 = []
    checks_4.append(names_tool(got_1, "guard_hook", bin_dir_1) is True)
    checks_4.append(names_tool(got_2, "statusline", bin_dir_2) is True)
    checks_4.append(names_tool(got_3, "session_log", bin_dir_3) is True)
    checks_4.append(names_tool(fixture_run_hook, "guard_hook", bin_dir_1) is True)
    checks_4.append(names_tool(fixture_run_other, "guard_hook", bin_dir_1) is False)
    checks_4.append(names_tool(fixture_runner, "guard_hook", bin_dir_1) is False)
    checks_4.append(names_tool(got_3, "session_log", "/elsewhere/bin") is False)
    checks_4.append(names_tool("", "guard_hook", bin_dir_1) is False)
    checks_4.append(names_tool('echo "unterminated', "guard_hook", bin_dir_1) is False)
    # Every command form is a FrugalFlow command; an ordinary command is not.
    checks_4.append(is_frugalflow_command(got_1, bin_dir_1) is True)
    checks_4.append(is_frugalflow_command(got_2, bin_dir_2) is True)
    checks_4.append(is_frugalflow_command(got_3, bin_dir_3) is True)
    checks_4.append(is_frugalflow_command(fixture_run_hook, bin_dir_1) is True)
    checks_4.append(is_frugalflow_command("echo hello", bin_dir_1) is False)
    checks_4.append(is_frugalflow_command("python3 -I /elsewhere/other.py", bin_dir_1) is False)
    pass_4 = all(checks_4)
    if pass_4:
        print("PASS 4 AUTOTEST 5/5 expected=all checks correct got=all checks correct")
    else:
        print("FAIL 4 AUTOTEST 5/5 expected=all checks correct got=some mismatch")

    script = sys.argv[0]
    proc_notice = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    proc_noargs = subprocess.run([sys.executable, script], capture_output=True, text=True)
    pass_5 = (proc_notice.returncode == 0 and proc_notice.stdout.startswith("NAME      launcher.py") and proc_noargs.returncode == 2)
    if pass_5:
        print("PASS 5 AUTOTEST 5/5 expected=notice exit 0 noargs exit 2 got=notice exit " + str(proc_notice.returncode) + " noargs exit " + str(proc_noargs.returncode))
    else:
        print("FAIL 5 AUTOTEST 5/5 expected=notice exit 0 noargs exit 2 got=notice exit " + str(proc_notice.returncode) + " noargs exit " + str(proc_noargs.returncode))

    results = [pass_1, pass_2, pass_3, pass_4, pass_5]
    if all(results):
        return 0
    return 1


def main(args):
    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if args == ["--autotest"]:
        return run_autotest()
    sys.stderr.write("usage: launcher.py --notice | --autotest\n")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
