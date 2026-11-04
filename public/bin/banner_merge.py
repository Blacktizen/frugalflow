#!/usr/bin/env python3
"""banner_merge.py - internal module for Claude Code settings management."""

import copy
import json
import subprocess
import sys


class BannerError(ValueError):
    pass


_CMD = "python3 /opt/ff/bin/session_banner.py"

_OTHER = json.loads(
    '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", '
    '"command": "other-start"}]}], "Stop": [{"hooks": [{"type": '
    '"command", "command": "other-stop"}]}]}, "statusLine": {"type": '
    '"command", "command": "sl"}}'
)

_WITH = json.loads(
    '{"hooks": {"SessionStart": [{"hooks": [{"type": "command", '
    '"command": "other-start"}]}, {"hooks": [{"type": "command", '
    '"command": "python3 /opt/ff/bin/session_banner.py"}]}], "Stop": '
    '[{"hooks": [{"type": "command", "command": "other-stop"}]}]}, '
    '"statusLine": {"type": "command", "command": "sl"}}'
)


def _validate_shape(settings):
    if not isinstance(settings, dict):
        raise BannerError("settings must be a dict")
    if "hooks" in settings and not isinstance(settings["hooks"], dict):
        raise BannerError("settings.hooks must be a dict")
    hooks = settings.get("hooks", {})
    if "SessionStart" in hooks and not isinstance(hooks["SessionStart"], list):
        raise BannerError("settings.hooks.SessionStart must be a list")
    for entry in hooks.get("SessionStart", []):
        if not isinstance(entry, dict):
            raise BannerError("each SessionStart entry must be a dict")
        if "hooks" in entry and not isinstance(entry["hooks"], list):
            raise BannerError("each SessionStart entry hooks must be a list")


def add_banner(settings, command):
    new_settings = copy.deepcopy(settings)
    _validate_shape(new_settings)
    hooks = new_settings.setdefault("hooks", {})
    session_start = hooks.setdefault("SessionStart", [])
    for group in session_start:
        for hook_entry in group.get("hooks", []):
            if hook_entry.get("command") == command:
                return (new_settings, False)
    new_group = {"hooks": [{"type": "command", "command": command}]}
    session_start.append(new_group)
    return (new_settings, True)


def remove_banner(settings, command):
    new_settings = copy.deepcopy(settings)
    _validate_shape(new_settings)
    hooks = new_settings.get("hooks", {})
    session_start = hooks.get("SessionStart", [])
    changed = False
    new_session_start = []
    for group in session_start:
        new_hooks = []
        for hook_entry in group.get("hooks", []):
            if hook_entry.get("command") == command:
                changed = True
            else:
                new_hooks.append(hook_entry)
        if new_hooks:
            new_group = dict(group)
            new_group["hooks"] = new_hooks
            new_session_start.append(new_group)
    if changed:
        if new_session_start:
            new_settings["hooks"]["SessionStart"] = new_session_start
        else:
            del new_settings["hooks"]["SessionStart"]
        if not new_settings["hooks"]:
            del new_settings["hooks"]
    return (new_settings, changed)


def _run_proofs():
    all_pass = True

    # P1
    expected = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": _CMD}]}]}}
    got, changed = add_banner({}, _CMD)
    ok = (got == expected) and changed is True
    if not ok:
        all_pass = False
    status = "PASS" if ok else "FAIL"
    print(status + ": P1 expected=" + repr(expected) + " changed=" + repr(True)
          + " got=" + repr(got) + " changed=" + repr(changed))

    # P2
    other_copy = copy.deepcopy(_OTHER)
    got, changed = add_banner(other_copy, _CMD)
    ok = (got == _WITH) and changed is True and (other_copy == _OTHER)
    if not ok:
        all_pass = False
    status = "PASS" if ok else "FAIL"
    print(status + ": P2 expected=" + repr(_WITH) + " changed=" + repr(True)
          + " got=" + repr(got) + " changed=" + repr(changed)
          + " original_unchanged=" + repr(other_copy == _OTHER))

    # P3
    got, changed = add_banner(_WITH, _CMD)
    ok = (got == _WITH) and changed is False
    if not ok:
        all_pass = False
    status = "PASS" if ok else "FAIL"
    print(status + ": P3 expected=" + repr(_WITH) + " changed=" + repr(False)
          + " got=" + repr(got) + " changed=" + repr(changed))

    # P4
    got_a, ch_a = remove_banner(_WITH, _CMD)
    got_b, ch_b = remove_banner(_OTHER, _CMD)
    p1_result = {"hooks": {"SessionStart": [{"hooks": [{"type": "command", "command": _CMD}]}]}}
    got_c, ch_c = remove_banner(p1_result, _CMD)
    ok = (got_a == _OTHER and ch_a is True
          and got_b == _OTHER and ch_b is False
          and got_c == {} and ch_c is True)
    if not ok:
        all_pass = False
    status = "PASS" if ok else "FAIL"
    print(status + ": P4 remove_with expected=" + repr(_OTHER) + " changed=" + repr(True)
          + " got=" + repr(got_a) + " changed=" + repr(ch_a)
          + " remove_other expected=" + repr(_OTHER) + " changed=" + repr(False)
          + " got=" + repr(got_b) + " changed=" + repr(ch_b)
          + " remove_p1 expected=" + repr({}) + " changed=" + repr(True)
          + " got=" + repr(got_c) + " changed=" + repr(ch_c))

    # P5: shape errors + exit code 2
    err_ok_1 = False
    err_ok_2 = False
    try:
        add_banner({"hooks": []}, _CMD)
    except BannerError as e:
        err_ok_1 = str(e) == "settings.hooks must be a dict"
    try:
        add_banner({"hooks": {"SessionStart": [3]}}, _CMD)
    except BannerError as e:
        err_ok_2 = str(e) == "each SessionStart entry must be a dict"
    proc_exit2 = subprocess.run(
        [sys.executable, __file__], capture_output=True, text=True
    )
    exit_ok = proc_exit2.returncode == 2
    ok = err_ok_1 and err_ok_2 and exit_ok
    if not ok:
        all_pass = False
    status = "PASS" if ok else "FAIL"
    msg1 = "BannerError(settings.hooks must be a dict)"
    msg2 = "BannerError(each SessionStart entry must be a dict)"
    print(status + ": P5 expected=" + repr(msg1) + " " + repr(msg2) + " exit2"
          + " got=" + repr(err_ok_1) + " " + repr(err_ok_2) + " exit=" + repr(proc_exit2.returncode))

    return 0 if all_pass else 1


def _print_notice():
    print("NAME: banner_merge - add or remove a SessionStart hook in a Claude Code settings dict")
    print("READS: a settings dict and a command string")
    print("WRITES: a new settings dict (deep copy); never mutates the input")
    print("EXAMPLE: add_banner({}, \"python3 /opt/ff/bin/session_banner.py\") adds a hooks entry and returns changed=True")
    print("PITFALLS: cascade removal - empty SessionStart list deletes the key; empty hooks deletes the key")


def _handle_autotest():
    proc = subprocess.run(
        [sys.executable, __file__, "--run-proofs"],
        capture_output=True,
        text=True
    )
    sys.stdout.write(proc.stdout)
    sys.stdout.write(proc.stderr)
    sys.stdout.flush()
    sys.exit(0 if proc.returncode == 0 else 1)


def main():
    args = sys.argv[1:]
    if args == ["--notice"]:
        _print_notice()
        sys.exit(0)
    elif args == ["--autotest"]:
        _handle_autotest()
    elif args == ["--run-proofs"]:
        sys.exit(_run_proofs())
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()
