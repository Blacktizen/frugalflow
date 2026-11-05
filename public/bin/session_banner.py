import sys
import os
import json
import tempfile
import subprocess


BANNER_TEMPLATE = (
    "FrugalFlow is {status} (mode: {mode}). Settings: "
    "`frugalflow config` · health check: `frugalflow doctor`"
)

PROJECT_SUFFIXES = frozenset(
    {".py", ".js", ".ts", ".go", ".rs", ".java", ".c", ".cpp", ".swift", ".rb", ".kt", ".sh"}
)

REPEAT_SENTENCE = " Repeat that line to the user in one sentence in your first reply."

NOT_WIRED_MESSAGE = (
    "FrugalFlow banner only: the guard is NOT wired (no guard.json in the FrugalFlow home, "
    "or no guard hook in ~/.claude/settings.json). Nothing is blocked. Check: `frugalflow doctor`."
)


def resolve_home(args_home=None):
    if args_home is not None:
        return os.path.abspath(args_home)
    env_val = os.environ.get("FRUGALFLOW_HOME")
    if env_val:
        return os.path.abspath(env_val)
    return os.path.abspath(os.path.expanduser(os.path.join("~", ".frugalflow")))


def read_preferences(home_dir):
    defaults = {
        "switch": {"enabled": True, "mode": "active"},
        "display": {"statusline": True, "turn_line": True, "summary": True, "banner": True},
    }
    path = os.path.join(home_dir, "preferences.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return defaults
        result = {}
        for key in defaults:
            merged = dict(defaults[key])
            raw = data.get(key)
            if isinstance(raw, dict):
                merged.update(raw)
            result[key] = merged
        return result
    except Exception:
        return defaults


def is_project(cwd):
    personal = os.path.abspath(os.path.expanduser("~"))
    abs_cwd = os.path.abspath(cwd)
    if abs_cwd == personal:
        return False
    if abs_cwd == "/":
        return False
    if os.path.exists(os.path.join(cwd, ".git")):
        return True
    try:
        for entry in os.listdir(cwd):
            full = os.path.join(cwd, entry)
            if os.path.isfile(full):
                _, ext = os.path.splitext(entry)
                if ext in PROJECT_SUFFIXES:
                    return True
    except OSError:
        pass
    return False


def has_memory(cwd):
    vault = os.path.join(cwd, "vault")
    if not os.path.isdir(vault):
        return False
    try:
        return len(os.listdir(vault)) > 0
    except OSError:
        return False


def is_declined(cwd, home_dir):
    path = os.path.join(home_dir, "memory_declined.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return False
        declined = data.get("declined")
        if not isinstance(declined, list):
            return False
        return os.path.abspath(cwd) in declined
    except Exception:
        return False


def guard_wired(home_dir):
    """Return True if both guard.json exists in FrugalFlow home AND
    ~/.claude/settings.json contains a PreToolUse hook with guard_hook --hook."""
    # Check guard.json exists in FrugalFlow home
    guard_path = os.path.join(home_dir, "guard.json")
    if not os.path.isfile(guard_path):
        return False

    # Check ~/.claude/settings.json for the hook
    settings_path = os.path.join(os.path.expanduser("~"), ".claude", "settings.json")
    try:
        with open(settings_path, "r", encoding="utf-8") as fh:
            settings = json.load(fh)
    except Exception:
        return False

    if not isinstance(settings, dict):
        return False

    hooks = settings.get("hooks")
    if not isinstance(hooks, dict):
        return False

    pre_tool_use = hooks.get("PreToolUse")
    if not isinstance(pre_tool_use, list):
        return False

    for group in pre_tool_use:
        if not isinstance(group, dict):
            continue
        hook_list = group.get("hooks")
        if not isinstance(hook_list, list):
            continue
        for hook in hook_list:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command")
            if isinstance(command, str) and "guard_hook" in command and "--hook" in command:
                return True

    return False


def run_hook():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return
        cwd = data.get("cwd")
        if not isinstance(cwd, str):
            return
        if not os.path.isdir(cwd):
            return

        home_dir = resolve_home()
        prefs = read_preferences(home_dir)

        display = prefs.get("display", {})
        if not display.get("banner", True):
            return

        switch = prefs.get("switch", {})
        enabled = switch.get("enabled", True)
        mode = switch.get("mode", "active")
        status = "active" if enabled else "off"

        wired = guard_wired(home_dir)
        if wired:
            banner_line = BANNER_TEMPLATE.format(status=status, mode=mode)
        else:
            banner_line = NOT_WIRED_MESSAGE

        project = is_project(cwd)
        memory = has_memory(cwd)
        declined = is_declined(cwd, home_dir)

        ask_question = project and (not memory) and (not declined)

        context = banner_line + REPEAT_SENTENCE
        if ask_question:
            abs_cwd = os.path.abspath(cwd)
            parent_folder = os.path.dirname(abs_cwd)
            base_name = os.path.basename(abs_cwd)
            question_text = (
                "This folder is a project without a FrugalFlow memory. "
                "Ask the user once, in one short question, whether to build "
                "the project memory now, and give this exact command: "
                "frugalflow new-project {name} --root {parent}. "
                "If the user refuses, run: frugalflow memory decline {cwd}, "
                "and never ask again for this folder."
            ).format(name=base_name, parent=parent_folder, cwd=abs_cwd)
            context = context + " " + question_text

        output_obj = {
            "systemMessage": banner_line,
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            },
        }
        sys.stdout.write(json.dumps(output_obj))
    except Exception:
        pass


def run_decline(args):
    try:
        target_path = None
        args_home = None
        idx = 0
        while idx < len(args):
            if args[idx] == "--home":
                if idx + 1 >= len(args):
                    sys.exit(2)
                args_home = args[idx + 1]
                idx += 2
            elif args[idx].startswith("--"):
                sys.exit(2)
            else:
                if target_path is not None:
                    sys.exit(2)
                target_path = args[idx]
                idx += 1

        if target_path is None:
            target_path = os.getcwd()
        abs_path = os.path.abspath(target_path)
        home_dir = resolve_home(args_home)

        declined_file = os.path.join(home_dir, "memory_declined.json")
        try:
            with open(declined_file, "r", encoding="utf-8") as fh:
                existing = json.load(fh)
            if not isinstance(existing, dict):
                existing = {"declined": []}
        except Exception:
            existing = {"declined": []}

        declined_list = existing.get("declined")
        if not isinstance(declined_list, list):
            declined_list = []

        if abs_path not in declined_list:
            declined_list.append(abs_path)
        existing["declined"] = declined_list

        os.makedirs(home_dir, exist_ok=True)
        with open(declined_file, "w", encoding="utf-8") as fh:
            json.dump(existing, fh)

        sys.stdout.write("DECLINED " + abs_path + "\n")
    except SystemExit:
        raise
    except Exception:
        sys.exit(2)


def run_notice():
    sys.stdout.write("NAME: FrugalFlow SessionStart banner hook\n")
    sys.stdout.write("READS: stdin hook JSON, home/preferences.json, home/memory_declined.json\n")
    sys.stdout.write("WRITES: nothing in hook mode; home/memory_declined.json in decline mode\n")
    sys.stdout.write("EXAMPLE: echo '{\"cwd\": \"projects/demo\"}' | python3 session_banner.py\n")
    sys.stdout.write("PITFALLS: missing or broken preferences.json uses defaults; broken memory_declined.json counts as empty\n")


def run_autotest():
    script = os.path.abspath(__file__)
    base = tempfile.mkdtemp()
    all_ok = True

    def report(ok, label, expected, obtained):
        nonlocal all_ok
        if not ok:
            all_ok = False
        tag = "PASS" if ok else "FAIL"
        sys.stdout.write(
            "{}: {} | expected: {} | obtained: {}\n".format(tag, label, expected, obtained)
        )

    ff_home = os.path.join(base, "FF_HOME")
    os.makedirs(ff_home)
    with open(os.path.join(ff_home, "preferences.json"), "w", encoding="utf-8") as fh:
        fh.write(
            '{"switch": {"enabled": true, "mode": "active"}, '
            '"display": {"statusline": true, "turn_line": true, "summary": true, "banner": true}}'
        )
    # Create guard.json for wired tests
    with open(os.path.join(ff_home, "guard.json"), "w", encoding="utf-8") as fh:
        fh.write('{}')

    # Set up fake HOME with settings.json containing the guard hook
    home_tmp = os.path.join(base, "HOME_TMP")
    os.makedirs(os.path.join(home_tmp, ".git"))
    with open(os.path.join(home_tmp, "main.py"), "w", encoding="utf-8") as fh:
        fh.write('print("hi")')
    claude_dir = os.path.join(home_tmp, ".claude")
    os.makedirs(claude_dir)
    settings_json = {
        "hooks": {
            "PreToolUse": [
                {
                    "hooks": [
                        {"command": "python3 -m frugalflow.guard_hook --hook pre_tool_use"}
                    ]
                }
            ]
        }
    }
    with open(os.path.join(claude_dir, "settings.json"), "w", encoding="utf-8") as fh:
        json.dump(settings_json, fh)

    p_vault = os.path.join(base, "P_VAULT")
    os.makedirs(os.path.join(p_vault, "vault"))
    with open(os.path.join(p_vault, "main.py"), "w", encoding="utf-8") as fh:
        fh.write('print("hi")')
    with open(os.path.join(p_vault, "vault", "overview.md"), "w", encoding="utf-8") as fh:
        fh.write("# overview")

    parent_tmp = os.path.join(base, "PARENT_TMP")
    p_new = os.path.join(parent_tmp, "project-new")
    os.makedirs(os.path.join(p_new, ".git"))

    def make_env(extra=None):
        env = dict(os.environ)
        env["HOME"] = home_tmp
        for k in list(env):
            if k.startswith("GIT_"):
                del env[k]
        env["FRUGALFLOW_HOME"] = ff_home
        if extra:
            env.update(extra)
        return env

    def stdin_json(cwd):
        return json.dumps(
            {"session_id": "t", "cwd": cwd, "hook_event_name": "SessionStart", "source": "startup"}
        )

    def run_hook_proc(stdin_text, extra_env=None):
        proc = subprocess.run(
            [sys.executable, script],
            input=stdin_text,
            capture_output=True,
            text=True,
            env=make_env(extra_env),
            timeout=15,
        )
        return proc.returncode, proc.stdout

    # P1: P_VAULT with active home, has memory so no question
    rc, out = run_hook_proc(stdin_json(p_vault))
    ok = rc == 0 and out != ""
    if ok:
        try:
            obj = json.loads(out)
            ok = "FrugalFlow is active (mode: active)" in obj.get("systemMessage", "")
            ok = ok and "new-project" not in out
        except Exception:
            ok = False
    report(ok, "P1 project with memory suppresses question",
           "exit 0, JSON banner present, no new-project",
           "exit {} out {}".format(rc, out[:200]))

    # P2: P_NEW project without memory, question asked
    rc, out = run_hook_proc(stdin_json(p_new))
    ok = rc == 0 and out != ""
    if ok:
        try:
            obj = json.loads(out)
            ctx = obj.get("hookSpecificOutput", {}).get("additionalContext", "")
            needle = "frugalflow new-project project-new --root " + parent_tmp
            ok = needle in ctx
            ok = ok and "memory decline" in ctx
        except Exception:
            ok = False
    report(ok, "P2 project without memory asks question",
           "exit 0, additionalContext contains new-project command",
           "exit {} out {}".format(rc, out[:300]))

    # P3: decline P_NEW then hook shows no question
    proc_decl = subprocess.run(
        [sys.executable, script, "decline", p_new, "--home", ff_home],
        capture_output=True, text=True, env=make_env(), timeout=15,
    )
    d_ok = proc_decl.returncode == 0
    expected_line = "DECLINED " + os.path.abspath(p_new)
    d_ok = d_ok and expected_line in proc_decl.stdout

    rc3, out3 = run_hook_proc(stdin_json(p_new))
    h_ok = rc3 == 0 and out3 != ""
    if h_ok:
        try:
            obj3 = json.loads(out3)
            h_ok = "FrugalFlow is active" in obj3.get("systemMessage", "")
            h_ok = h_ok and "new-project" not in out3
        except Exception:
            h_ok = False
    p3_ok = d_ok and h_ok
    report(p3_ok, "P3 decline removes question",
           "decline exit 0 with DECLINED line, hook exit 0 no new-project",
           "decline {} {} hook {} {}".format(
               proc_decl.returncode, proc_decl.stdout[:80], rc3, out3[:80]))

    # P4: HOME_TMP is personal folder no question; banner=false gives empty
    rc4a, out4a = run_hook_proc(stdin_json(home_tmp))
    a_ok = rc4a == 0 and out4a != ""
    if a_ok:
        try:
            obj4 = json.loads(out4a)
            a_ok = "FrugalFlow is active" in obj4.get("systemMessage", "")
            a_ok = a_ok and "new-project" not in out4a
        except Exception:
            a_ok = False

    ff_nb = os.path.join(base, "FF_HOME_NB")
    os.makedirs(ff_nb)
    with open(os.path.join(ff_nb, "preferences.json"), "w", encoding="utf-8") as fh:
        fh.write(
            '{"switch": {"enabled": true, "mode": "active"}, '
            '"display": {"statusline": true, "turn_line": true, "summary": true, "banner": false}}'
        )
    rc4b, out4b = run_hook_proc(stdin_json(p_new), {"FRUGALFLOW_HOME": ff_nb})
    b_ok = rc4b == 0 and out4b == ""

    p4_ok = a_ok and b_ok
    report(p4_ok, "P4 personal folder no question, banner off empty",
           "home exit 0 banner no new-project; nobanner exit 0 empty",
           "home {} {} nobanner {} {}".format(
               rc4a, out4a[:80], rc4b, repr(out4b)))

    # P5: broken JSON and non-existent folder both give empty output
    rc5a, out5a = run_hook_proc("{not json")
    a5 = rc5a == 0 and out5a == ""
    fake = os.path.join(base, "DOES_NOT_EXIST_xyz")
    rc5b, out5b = run_hook_proc(stdin_json(fake))
    b5 = rc5b == 0 and out5b == ""
    p5_ok = a5 and b5
    report(p5_ok, "P5 broken input and missing folder give empty output",
           "exit 0 empty stdout for both",
           "broken {} {} missing {} {}".format(
               rc5a, repr(out5a), rc5b, repr(out5b)))

    # P6: no guard.json -> banner contains NOT wired, no "active"
    ff_home_no_guard = os.path.join(base, "FF_HOME_NO_GUARD")
    os.makedirs(ff_home_no_guard)
    with open(os.path.join(ff_home_no_guard, "preferences.json"), "w", encoding="utf-8") as fh:
        fh.write(
            '{"switch": {"enabled": true, "mode": "active"}, '
            '"display": {"statusline": true, "turn_line": true, "summary": true, "banner": true}}'
        )
    # No guard.json created
    rc6, out6 = run_hook_proc(stdin_json(p_vault), {"FRUGALFLOW_HOME": ff_home_no_guard})
    ok6 = rc6 == 0 and out6 != ""
    if ok6:
        try:
            obj6 = json.loads(out6)
            sysmsg = obj6.get("systemMessage", "")
            ok6 = ("active" not in sysmsg) and ("NOT wired" in sysmsg)
        except Exception:
            ok6 = False
    report(ok6, "P6 no guard.json -> NOT wired banner",
           "exit 0, systemMessage contains NOT wired, no 'active'",
           "exit {} out {}".format(rc6, out6[:200]))

    # P7: guard.json present, settings.json absent or without hook -> NOT wired
    ff_home_guard_only = os.path.join(base, "FF_HOME_GUARD_ONLY")
    os.makedirs(ff_home_guard_only)
    with open(os.path.join(ff_home_guard_only, "preferences.json"), "w", encoding="utf-8") as fh:
        fh.write(
            '{"switch": {"enabled": true, "mode": "active"}, '
            '"display": {"statusline": true, "turn_line": true, "summary": true, "banner": true}}'
        )
    with open(os.path.join(ff_home_guard_only, "guard.json"), "w", encoding="utf-8") as fh:
        fh.write('{}')
    # Use a HOME without .claude/settings.json
    home_no_settings = os.path.join(base, "HOME_NO_SETTINGS")
    os.makedirs(os.path.join(home_no_settings, ".git"))
    with open(os.path.join(home_no_settings, "main.py"), "w", encoding="utf-8") as fh:
        fh.write('print("hi")')
    # No .claude directory
    rc7, out7 = run_hook_proc(stdin_json(p_vault), {"FRUGALFLOW_HOME": ff_home_guard_only, "HOME": home_no_settings})
    ok7 = rc7 == 0 and out7 != ""
    if ok7:
        try:
            obj7 = json.loads(out7)
            sysmsg = obj7.get("systemMessage", "")
            ok7 = ("active" not in sysmsg) and ("NOT wired" in sysmsg)
        except Exception:
            ok7 = False
    report(ok7, "P7 guard.json but no settings.json hook -> NOT wired",
           "exit 0, systemMessage contains NOT wired, no 'active'",
           "exit {} out {}".format(rc7, out7[:200]))

    # P8: guard.json present AND settings.json with guard_hook --hook -> "FrugalFlow is active"
    # This is already covered by P1/P3/P4a but let's make it explicit
    rc8, out8 = run_hook_proc(stdin_json(p_vault))
    ok8 = rc8 == 0 and out8 != ""
    if ok8:
        try:
            obj8 = json.loads(out8)
            ok8 = "FrugalFlow is active (mode: active)" in obj8.get("systemMessage", "")
        except Exception:
            ok8 = False
    report(ok8, "P8 guard.json + settings.json with hook -> active banner",
           "exit 0, systemMessage contains 'FrugalFlow is active'",
           "exit {} out {}".format(rc8, out8[:200]))

    sys.exit(0 if all_ok else 1)


def main():
    argv = sys.argv[1:]
    if not argv:
        run_hook()
        sys.exit(0)
    first = argv[0]
    if first == "decline":
        run_decline(argv[1:])
        sys.exit(0)
    elif first == "--notice":
        run_notice()
        sys.exit(0)
    elif first == "--autotest":
        run_autotest()
    else:
        sys.exit(2)


if __name__ == "__main__":
    main()