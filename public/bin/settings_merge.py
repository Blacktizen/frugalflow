import sys
import os
import shlex
import copy
import subprocess


class SettingsError(ValueError):
    pass


def guard_command(python, bin_dir):
    return shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "guard_hook.py")) + " --hook"


def is_ours(command, guard_path):
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) < 3:
        return False
    if os.path.normpath(parts[1]) != os.path.normpath(guard_path):
        return False
    return "--hook" in parts


def _check_shape(settings):
    if not isinstance(settings, dict):
        raise SettingsError("settings must be a dict")
    hooks = settings.get("hooks")
    if hooks is None:
        return
    if not isinstance(hooks, dict):
        raise SettingsError("settings.hooks must be a dict")
    pre = hooks.get("PreToolUse")
    if pre is None:
        return
    if not isinstance(pre, list):
        raise SettingsError("settings.hooks.PreToolUse must be a list")
    for group in pre:
        if not isinstance(group, dict):
            raise SettingsError("each PreToolUse entry must be a dict")
        gh = group.get("hooks")
        if gh is None:
            continue
        if not isinstance(gh, list):
            raise SettingsError("each PreToolUse entry hooks must be a list")
        for entry in gh:
            if not isinstance(entry, dict):
                raise SettingsError("each hook entry must be a dict")


def add_hooks(settings, command):
    _check_shape(settings)
    new = copy.deepcopy(settings)
    hooks = new.setdefault("hooks", {})
    pre = hooks.setdefault("PreToolUse", [])
    for group in pre:
        for entry in group.get("hooks", []):
            if entry.get("command") == command:
                return new, False
    pre.append({"matcher": "*", "hooks": [{"type": "command", "command": command}]})
    return new, True


def remove_hooks(settings, guard_path):
    _check_shape(settings)
    new = copy.deepcopy(settings)
    hooks = new.get("hooks")
    if not isinstance(hooks, dict):
        return new, False
    pre = hooks.get("PreToolUse")
    if not isinstance(pre, list):
        return new, False
    changed = False
    kept_groups = []
    for group in pre:
        gh = group.get("hooks")
        if not isinstance(gh, list):
            kept_groups.append(group)
            continue
        kept = [e for e in gh if not is_ours(e.get("command", ""), guard_path)]
        if len(kept) != len(gh):
            changed = True
            if kept:
                group["hooks"] = kept
                kept_groups.append(group)
        else:
            kept_groups.append(group)
    if not changed:
        return new, False
    if kept_groups:
        hooks["PreToolUse"] = kept_groups
    else:
        del hooks["PreToolUse"]
        if not hooks:
            del new["hooks"]
    return new, True


def statusline_command(python, bin_dir, inner=None):
    cmd = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "statusline.py"))
    if inner is not None:
        cmd = cmd + " --inner " + shlex.quote(inner)
    return cmd


def is_our_statusline(command, bin_dir):
    try:
        parts = shlex.split(command)
    except ValueError:
        return False
    if len(parts) < 2:
        return False
    if os.path.normpath(parts[1]) != os.path.normpath(os.path.join(bin_dir, "statusline.py")):
        return False
    return True


def _statusline_shape(settings):
    if not isinstance(settings, dict):
        raise SettingsError("settings must be a dict")
    sl = settings.get("statusLine")
    if sl is None:
        return None
    if not isinstance(sl, dict):
        raise SettingsError("statusLine must be a dict")
    if sl.get("type") != "command":
        raise SettingsError("statusLine.type must be command")
    command = sl.get("command")
    if not isinstance(command, str):
        raise SettingsError("statusLine.command must be a string")
    return command


def add_statusline(settings, python, bin_dir):
    command = _statusline_shape(settings)
    if command is None:
        new = copy.deepcopy(settings)
        new["statusLine"] = {"type": "command", "command": statusline_command(python, bin_dir)}
        return new, True
    if is_our_statusline(command, bin_dir):
        return copy.deepcopy(settings), False
    new = copy.deepcopy(settings)
    new["statusLine"]["command"] = statusline_command(python, bin_dir, inner=command)
    return new, True


def remove_statusline(settings, bin_dir):
    if not isinstance(settings, dict):
        return copy.deepcopy(settings), False
    sl = settings.get("statusLine")
    if not isinstance(sl, dict) or sl.get("type") != "command":
        return copy.deepcopy(settings), False
    command = sl.get("command")
    if not isinstance(command, str) or not is_our_statusline(command, bin_dir):
        return copy.deepcopy(settings), False
    try:
        parts = shlex.split(command)
    except ValueError:
        return copy.deepcopy(settings), False
    inner = None
    if "--inner" in parts:
        i = parts.index("--inner")
        if i + 1 < len(parts):
            inner = parts[i + 1]
    new = copy.deepcopy(settings)
    if inner is None:
        del new["statusLine"]
    else:
        new["statusLine"]["command"] = inner
    return new, True


NOTICE = (
    "NAME      settings_merge.py - adds and removes the FrugalFlow PreToolUse hook and the FrugalFlow status line in a settings dict.\n"
    "READS     nothing: pure module; it reads the dict it is given.\n"
    "WRITES    nothing: every function returns a deep copy, the given dict is never touched; the user's status line is wrapped, never replaced.\n"
    "EXAMPLE   python3 settings_merge.py --notice\n"
    "PITFALLS  2026-10-03 a hook was appended to the caller's dict in place; every function now returns a deep copy so the caller stays pure.\n"
    "          2026-10-04 a foreign status line was replaced wholesale; add_statusline now wraps it with --inner and remove_statusline hands it back unchanged.\n"
)


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    print("usage: settings_merge.py --notice | --autotest")
    return 2


def _autotest():
    bin_dir = "/frugalflow/bin"
    python = sys.executable
    cmd = guard_command(python, bin_dir)
    guard_path = os.path.join(bin_dir, "guard_hook.py")
    results = []

    # Test 1
    parts = shlex.split(cmd)
    ok = len(parts) == 3 and parts[2] == "--hook" and is_ours(cmd, guard_path) is True
    results.append(("1 guard_command builds [python, guard_hook.py, --hook] and is_ours accepts it", ok,
                    "cmd=%r parts=%r" % (cmd, parts) if not ok else ""))

    # Test 2
    settings = {"a": 1}
    new, changed = add_hooks(settings, cmd)
    expected = {"a": 1, "hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}}
    ok = changed is True and new == expected and settings == {"a": 1}
    results.append(("2 add_hooks appends the group and never mutates the input", ok, "new=%r" % new if not ok else ""))

    # Test 3
    again, changed2 = add_hooks(new, cmd)
    ok = changed2 is False and again == new
    results.append(("3 add_hooks is idempotent", ok, "changed2=%r again=%r" % (changed2, again) if not ok else ""))

    # Test 4
    back, changed3 = remove_hooks(new, guard_path)
    ok = changed3 is True and back == settings
    results.append(("4 remove_hooks undoes add_hooks", ok, "back=%r changed3=%r" % (back, changed3) if not ok else ""))

    # Test 5
    shared = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [
        {"type": "command", "command": "other"},
        {"type": "command", "command": cmd},
    ]}]}}
    kept, changed4 = remove_hooks(shared, guard_path)
    expected_kept = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": "other"}]}]}}
    ok = (changed4 is True and kept == expected_kept
          and shared["hooks"]["PreToolUse"][0]["hooks"][1]["command"] == cmd)
    results.append(("5 remove_hooks drops only our hook from a shared group", ok, "kept=%r" % kept if not ok else ""))

    # Test 6
    only_ours = {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [{"type": "command", "command": cmd}]}]}}
    cleaned, changed5 = remove_hooks(only_ours, guard_path)
    ok = changed5 is True and cleaned == {}
    results.append(("6 remove_hooks removes the emptied group, PreToolUse and hooks", ok,
                    "cleaned=%r" % cleaned if not ok else ""))

    # Test 7
    bad_cases = [
        "not a dict",
        {"hooks": "nope"},
        {"hooks": {"PreToolUse": "nope"}},
        {"hooks": {"PreToolUse": ["nope"]}},
        {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": "nope"}]}},
        {"hooks": {"PreToolUse": [{"matcher": "*", "hooks": [["nope"]]}]}},
    ]
    ok = True
    detail = ""
    for b in bad_cases:
        try:
            add_hooks(b, cmd)
        except SettingsError:
            continue
        ok = False
        detail = "add_hooks accepted %r" % b
        break
    results.append(("7 add_hooks refuses malformed shapes", ok, detail))

    # Test 8
    ok = (is_ours("bad 'quote", guard_path) is False
          and is_ours("python3 /elsewhere/hook.py --hook", guard_path) is False
          and is_ours("python3 " + guard_path + " --other", guard_path) is False)
    results.append(("8 is_ours rejects split errors, other paths and a missing --hook", ok, ""))

    # Test 9
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    ok = r.returncode == 0 and r.stdout.startswith("NAME      settings_merge.py")
    results.append(("9 --notice prints the notice", ok, "rc=%d stdout=%r" % (r.returncode, r.stdout) if not ok else ""))

    # Test 10: a foreign status line is wrapped with --inner and padding kept, then removed back to the exact original.
    fixture = {"model": "opus", "statusLine": {"type": "command", "command": "bash -c 'echo \"$PWD\"'", "padding": 0}}
    inner_cmd = "bash -c 'echo \"$PWD\"'"
    wrapped, changed10 = add_statusline(fixture, python, bin_dir)
    expected_wrapped = {"model": "opus", "statusLine": {"type": "command",
                                                         "command": statusline_command(python, bin_dir, inner=inner_cmd),
                                                         "padding": 0}}
    back10, changed10b = remove_statusline(wrapped, bin_dir)
    ok = (changed10 is True and wrapped == expected_wrapped
          and changed10b is True and back10 == fixture)
    results.append(("10 add_statusline wraps a foreign line (inner kept, padding kept) and remove_statusline restores it",
                    ok, "wrapped=%r back=%r" % (wrapped, back10) if not ok else ""))

    # Test 11: a settings dict without statusLine: add then remove yields the original; a second add is a no-op.
    bare = {"model": "opus"}
    added11, changed11 = add_statusline(bare, python, bin_dir)
    back11, changed11b = remove_statusline(added11, bin_dir)
    again11, changed11c = add_statusline(added11, python, bin_dir)
    ok = (changed11 is True
          and added11 == {"model": "opus", "statusLine": {"type": "command", "command": statusline_command(python, bin_dir)}}
          and changed11b is True and back11 == bare
          and changed11c is False and again11 == added11)
    results.append(("11 add then remove restores a bare dict and a second add is a no-op",
                    ok, "added=%r back=%r again=%r changed=%r/%r" % (added11, back11, again11, changed11, changed11c) if not ok else ""))

    # Test 12: a statusLine that is not a command dict is refused.
    try:
        add_statusline({"statusLine": "x"}, python, bin_dir)
        ok12 = False
        detail12 = "add_statusline accepted {'statusLine': 'x'}"
    except SettingsError:
        ok12 = True
        detail12 = ""
    results.append(("12 add_statusline refuses a non-dict statusLine", ok12, detail12))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + (" | " + detail if detail else ""))
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "settings_merge", sys.argv[1:])
