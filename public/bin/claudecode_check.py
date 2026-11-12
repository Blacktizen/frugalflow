#!/usr/bin/env python3
"""claudecode_check.py -- the shared CLAUDECODE + TTY check for setting-changing commands.

frugalflow.py and the setting tools (config_cmd, init_cmd, setup_cmd, uninstall_cmd,
onboard_cmd) all call check_claudecode_tty before a setting changes: inside Claude
Code (CLAUDECODE=1) without a terminal, a setting change is refused with exit 3.
"""

import os
import sys

MESSAGE = "Refused: this command changes a FrugalFlow setting; run it yourself in a terminal.\n"


def is_setting_change_command(command, args):
    """Check if the command/subcommand changes a FrugalFlow setting."""
    if command in ("on", "off", "mode", "display", "init", "setup", "uninstall", "onboard"):
        return True
    if command == "config" and args and args[0] == "set":
        return True
    if command == "memory" and args and args[0] == "decline":
        return True
    if command == "notes" and args and args[0] in ("add-pitfall", "merge", "measure"):
        return True
    if command == "run" and args and args[0] in ("model_notes", "model_notes.py"):
        return True
    return False


def check_claudecode_tty(command, args):
    """Check CLAUDECODE env var and TTY status for setting-change commands."""
    if not is_setting_change_command(command, args):
        return
    if os.environ.get("CLAUDECODE") != "1":
        return
    if sys.stdin.isatty() and sys.stdout.isatty():
        return
    sys.stdout.write(MESSAGE)
    sys.exit(3)


NOTICE = (
    "NAME      claudecode_check.py - refuses a FrugalFlow setting change launched by Claude Code without a terminal.\n"
    "READS     the CLAUDECODE variable and whether stdin and stdout are terminals.\n"
    "WRITES    nothing; exit 3 with the refusal message when the change must be run by hand.\n"
    "EXAMPLE   python3 claudecode_check.py --notice\n"
    "PITFALLS  2026-11-12 config_cmd.py and the other sub-tools did not check CLAUDECODE themselves: launching them directly changed a setting.\n"
)


def _autotest():
    import subprocess

    bin_dir = os.path.dirname(os.path.abspath(__file__))
    base_env = dict(os.environ)
    base_env.pop("CLAUDECODE", None)
    probe = (
        "import sys; sys.path.insert(0, r" + repr(bin_dir) + "); "
        "import claudecode_check; claudecode_check.check_claudecode_tty('on', [])"
    )

    failures = 0

    # Test 1: CLAUDECODE=1, stdin and stdout piped (not terminals) -> refusal, exit 3
    env1 = dict(base_env)
    env1["CLAUDECODE"] = "1"
    proc1 = subprocess.run(
        [sys.executable, "-c", probe],
        env=env1,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc1.returncode == 3 and proc1.stdout == MESSAGE:
        print("PASS 1 refusal under CLAUDECODE: expected rc 3 + message, got rc "
              + str(proc1.returncode) + " + " + repr(proc1.stdout))
    else:
        print("FAIL 1 refusal under CLAUDECODE: expected rc 3 + message, got rc "
              + str(proc1.returncode) + " + " + repr(proc1.stdout))
        failures += 1

    # Test 2: no CLAUDECODE -> the check lets the command through
    proc2 = subprocess.run(
        [sys.executable, "-c", probe],
        env=base_env,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
    )
    if proc2.returncode == 0 and proc2.stdout == "":
        print("PASS 2 passthrough without CLAUDECODE: expected rc 0 + empty, got rc "
              + str(proc2.returncode) + " + " + repr(proc2.stdout))
    else:
        print("FAIL 2 passthrough without CLAUDECODE: expected rc 0 + empty, got rc "
              + str(proc2.returncode) + " + " + repr(proc2.stdout))
        failures += 1

    # Test 3: --notice exits 0 with the notice
    proc3 = subprocess.run(
        [sys.executable, __file__, "--notice"],
        env=base_env,
        capture_output=True,
        text=True,
    )
    if proc3.returncode == 0 and proc3.stdout.startswith("NAME      claudecode_check.py"):
        print("PASS 3 --notice: expected rc 0 + notice, got rc " + str(proc3.returncode))
    else:
        print("FAIL 3 --notice: expected rc 0 + notice, got rc "
              + str(proc3.returncode) + " + " + repr(proc3.stdout))
        failures += 1

    # Test 4: no argument -> usage, exit 2
    proc4 = subprocess.run(
        [sys.executable, __file__],
        env=base_env,
        capture_output=True,
        text=True,
    )
    if proc4.returncode == 2 and "usage: claudecode_check.py" in proc4.stdout:
        print("PASS 4 usage without argument: expected rc 2 + usage, got rc " + str(proc4.returncode))
    else:
        print("FAIL 4 usage without argument: expected rc 2 + usage, got rc "
              + str(proc4.returncode) + " + " + repr(proc4.stdout))
        failures += 1

    return 0 if failures == 0 else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write("usage: claudecode_check.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "claudecode_check", sys.argv[1:])
