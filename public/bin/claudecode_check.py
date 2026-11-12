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
