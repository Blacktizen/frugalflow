import os
import sys
import json
import subprocess
import shutil
import shlex

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_block
import settings_merge
import env_detect
import ceilings
import launcher

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE = (
    "usage: doctor_cmd.py [--home DIR] [--claude-dir DIR] "
    "[--ollama-url URL] [--lmstudio-url URL] | --notice | --autotest"
)

NOTICE = (
    "NAME      doctor_cmd.py - the frugalflow doctor subcommand: one line per check of the installed FrugalFlow, including the status line.\n"
    "READS     the settings files in --home, else FRUGALFLOW_HOME, else ~/.frugalflow; CLAUDE.md and settings.json in --claude-dir, else ~/.claude; the local engine endpoints.\n"
    "WRITES    nothing: one OK, WARN, INFO or FAIL line per check, then exits 0 when clean or 1 when a FAIL is found.\n"
    "EXAMPLE   python3 doctor_cmd.py --home ~/.frugalflow --claude-dir ~/.claude\n"
    "PITFALLS  2026-10-03 an engine that does not answer is a WARN, never a FAIL: a missing local model must not block a doctor run for something else.\n"
    "          2026-11-12 a hook command without -I let a planted .pth file run before the guard; the doctor fails when a FrugalFlow hook command lost -I.\n"
)


def _hook_commands(doc):
    """Return every command string in the hooks of a settings dict."""
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return []
    out = []
    for event in hooks.values():
        if not isinstance(event, list):
            continue
        for group in event:
            if not isinstance(group, dict):
                continue
            entries = group.get("hooks")
            if not isinstance(entries, list):
                continue
            for entry in entries:
                if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                    out.append(entry["command"])
    return out


def _read_json_object(path):
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
        return isinstance(doc, dict)
    except (OSError, ValueError):
        return False


def _guard_ok(home):
    path = os.path.join(home, "guard.json")
    if not _read_json_object(path):
        return False
    with open(path, encoding="utf-8") as f:
        doc = json.load(f)
    for key in ("code_extensions", "delegation_logs", "audit_log"):
        if key not in doc:
            return False
    return True


def _claude_block_ok(claude_dir):
    path = os.path.join(claude_dir, "CLAUDE.md")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8", newline="") as f:
            text = f.read()
        return claude_block.find_block(text) is not None
    except (OSError, claude_block.BlockError):
        return False


def _hook_ok(claude_dir):
    path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return False
    pre = hooks.get("PreToolUse")
    if not isinstance(pre, list):
        return False
    guard_path = os.path.join(BIN, "guard_hook.py")
    for group in pre:
        if not isinstance(group, dict):
            continue
        entries = group.get("hooks")
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            if settings_merge.is_ours(entry.get("command", ""), guard_path):
                return True
    return False


def _status_line_ok(claude_dir):
    path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(path):
        return False
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return False
    if not isinstance(doc, dict):
        return False
    sl = doc.get("statusLine")
    if not isinstance(sl, dict):
        return False
    command = sl.get("command")
    if not isinstance(command, str):
        return False
    return settings_merge.is_our_statusline(command, BIN)


def _read_switch(home):
    path = os.path.join(home, "preferences.json")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return (True, "active")
    if not isinstance(doc, dict):
        return (True, "active")
    try:
        return ceilings.switch_state(doc)
    except (KeyError, TypeError):
        return (True, "active")


def _engines(home):
    path = os.path.join(home, "models.json")
    try:
        with open(path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return
    for m in doc.get("models", []):
        if not isinstance(m, dict) or m.get("location") != "local":
            continue
        mid = m.get("id", "?")
        endpoint = m.get("endpoint", "")
        if env_detect.probe(endpoint, "/models"):
            print("OK engine " + mid + " answers")
        else:
            print("WARN engine " + mid + " does not answer at " + endpoint)


def _doctor(home, claude_dir, ollama_url, lmstudio_url):
    fails = 0
    fix = "fix: python3 " + os.path.join(BIN, "frugalflow.py") + " init"

    # 1 home
    if os.path.isdir(home):
        print("OK home " + home)
    else:
        fails += 1
        print("FAIL home " + home + " is missing (" + fix + ")")

    # 2 settings files
    proc = subprocess.run([sys.executable, os.path.join(BIN, "config_check.py"), "--home", home],
                          capture_output=True, text=True)
    if proc.returncode == 0:
        print("OK settings files valid (models.json, preferences.json)")
    else:
        first = (proc.stdout.splitlines() or [""])[0]
        fails += 1
        print("FAIL settings files invalid: " + first + " (" + fix + ")")

    # 3 guard.json
    if _guard_ok(home):
        guard_path = os.path.join(home, "guard.json")
        try:
            with open(guard_path, encoding="utf-8") as f:
                guard_doc = json.load(f)
            checks = guard_doc.get("checks")
            if isinstance(checks, list) and "reading_gate" not in checks:
                fails += 1
                print("FAIL guard.json checks lack reading_gate: the reading gate is off (" + fix + ")")
            else:
                print("OK guard.json")
                if guard_doc.get("allow_env_disarm", False) is True:
                    print("INFO guard.json allow_env_disarm is true: FRUGALFLOW_GUARD=0 disarms the guard")
                else:
                    print("INFO guard.json allow_env_disarm is false: FRUGALFLOW_GUARD=0 is ignored")
        except (OSError, ValueError):
            fails += 1
            print("FAIL guard.json cannot be read (" + fix + ")")
    else:
        fails += 1
        print("FAIL guard.json is missing or incomplete (" + fix + ")")

    # 4 anonymization.json
    if _read_json_object(os.path.join(home, "anonymization.json")):
        print("OK anonymization.json")
    else:
        fails += 1
        print("FAIL anonymization.json is missing or not a JSON object (" + fix + ")")

    # 5 CLAUDE.md
    if _claude_block_ok(claude_dir):
        print("OK CLAUDE.md has the FrugalFlow block")
    else:
        fails += 1
        print("FAIL CLAUDE.md has no intact FrugalFlow block (" + fix + ")")

    # 6 settings.json
    if _hook_ok(claude_dir):
        print("OK settings.json has the FrugalFlow hook")
    else:
        fails += 1
        print("FAIL settings.json has no FrugalFlow hook (" + fix + ")")

    # 6b status line
    if _status_line_ok(claude_dir):
        print("OK status line: FrugalFlow segment in place")
    else:
        print("WARN status line: FrugalFlow segment missing (" + fix + ")")

    # 6c hook interpreter exists
    settings_path = os.path.join(claude_dir, "settings.json")
    if os.path.isfile(settings_path):
        try:
            with open(settings_path, encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            doc = None
        if isinstance(doc, dict):
            hooks = doc.get("hooks")
            if isinstance(hooks, dict):
                pre = hooks.get("PreToolUse")
                if isinstance(pre, list):
                    guard_path = os.path.join(BIN, "guard_hook.py")
                    for group in pre:
                        if not isinstance(group, dict):
                            continue
                        entries = group.get("hooks")
                        if not isinstance(entries, list):
                            continue
                        for entry in entries:
                            if not isinstance(entry, dict):
                                continue
                            if settings_merge.is_ours(entry.get("command", ""), guard_path):
                                cmd = entry.get("command", "")
                                try:
                                    parts = shlex.split(cmd)
                                except ValueError:
                                    parts = []
                                if parts:
                                    first = parts[0]
                                    if os.path.isabs(first):
                                        if not os.path.exists(first):
                                            fails += 1
                                            print("FAIL hook interpreter does not exist: " + first + " (" + fix + ")")
                                        else:
                                            print("OK hook interpreter exists: " + first)
                                    elif first == "frugalflow":
                                        if shutil.which("frugalflow") is None:
                                            fails += 1
                                            print("FAIL hook interpreter does not exist: frugalflow (" + fix + ")")
                                        else:
                                            print("OK hook interpreter exists: frugalflow")
                                    else:
                                        resolved = shutil.which(first)
                                        if resolved is None:
                                            fails += 1
                                            print("FAIL hook interpreter does not exist: " + first + " (" + fix + ")")
                                        else:
                                            print("OK hook interpreter exists: " + first)

            # 6d every FrugalFlow hook command runs python with -I: without it,
            # python executes a .pth file planted in the user site-packages
            # before the guard even starts.
            commands = _hook_commands(doc)
            status_line = doc.get("statusLine")
            if isinstance(status_line, dict) and isinstance(status_line.get("command"), str):
                commands.append(status_line["command"])
            isolated = 0
            for cmd in commands:
                if not launcher.is_frugalflow_command(cmd, BIN):
                    continue
                try:
                    tokens = shlex.split(cmd)
                except ValueError:
                    tokens = []
                if "-I" in tokens:
                    isolated += 1
                else:
                    fails += 1
                    print("FAIL hook command runs python without -I: " + cmd + " (" + fix + ")")
            if isolated:
                print("OK hook commands run python with -I (" + str(isolated) + ")")

    # 7 switch
    enabled, mode = _read_switch(home)
    if enabled:
        print("OK switch: FrugalFlow on, mode " + mode)
        if mode != "observe":
            print("OK guard mode: " + mode + " (a refused action is blocked)")
        else:
            print("WARN guard mode: OBSERVE - the guards log what they would refuse but do NOT block anything. "
                  "Turn enforcement on: python3 " + os.path.join(BIN, "frugalflow.py") + " mode active")
    else:
        print("WARN switch: FrugalFlow off, mode " + mode + " (turn it on: python3 " + os.path.join(BIN, "frugalflow.py") + " on)")

    # 8 engines
    for line in env_detect.describe(env_detect.detect(ollama_url, lmstudio_url, os.environ)):
        print("INFO " + line)
    _engines(home)

    return 1 if fails else 0


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    home = None
    claude_dir = None
    ollama_url = None
    lmstudio_url = None

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            home = argv[i + 1]
            i += 2
        elif a == "--claude-dir":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            claude_dir = argv[i + 1]
            i += 2
        elif a == "--ollama-url":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            ollama_url = argv[i + 1]
            i += 2
        elif a == "--lmstudio-url":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            lmstudio_url = argv[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2

    home = home or os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")
    claude_dir = claude_dir or os.path.expanduser("~/.claude")
    ollama_url = ollama_url or env_detect.OLLAMA_URL
    lmstudio_url = lmstudio_url or env_detect.LMSTUDIO_URL

    return _doctor(home, claude_dir, ollama_url, lmstudio_url)


def _autotest():
    import tempfile

    script = os.path.abspath(__file__)
    init_script = os.path.join(BIN, "init_cmd.py")
    results = []

    def init(tmp, home, claude):
        env = dict(os.environ)
        env["HOME"] = tmp
        return subprocess.run(
            [sys.executable, init_script, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env, cwd=tmp)

    def run(tmp, home, claude):
        env = dict(os.environ)
        env["HOME"] = tmp
        return subprocess.run(
            [sys.executable, script, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env, cwd=tmp)

    # Test 1: doctor exits 0 after a clean init.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r = init(tmp, home, claude)
        ok = r.returncode == 0
        got = "init_rc=%d" % r.returncode
        if ok:
            d = run(tmp, home, claude)
            ok = (d.returncode == 0 and "OK settings files valid" in d.stdout
                  and "OK guard.json" in d.stdout
                  and "OK status line: FrugalFlow segment in place" in d.stdout)
            got = "doctor_rc=%d" % d.returncode
        results.append(("1 doctor exits 0 after a clean init and reports the status line", ok, got))

    # Test 2: doctor exits 1 after guard.json is removed.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r = init(tmp, home, claude)
        ok = r.returncode == 0
        got = "init_rc=%d" % r.returncode
        if ok:
            os.remove(os.path.join(home, "guard.json"))
            d = run(tmp, home, claude)
            ok = d.returncode == 1 and "guard.json" in d.stdout
            got = "doctor_rc=%d" % d.returncode
        results.append(("2 doctor exits 1 after guard.json is removed", ok, got))

    # Test 3: doctor exits 1 with a missing home.
    with tempfile.TemporaryDirectory() as tmp:
        d = run(tmp, os.path.join(tmp, "missing"), os.path.join(tmp, "claude"))
        ok = d.returncode == 1 and "FAIL home" in d.stdout
        results.append(("3 doctor exits 1 with a missing home", ok, "rc=%d" % d.returncode))

    # Test 4: doctor warns when the switch is off.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r = init(tmp, home, claude)
        ok = r.returncode == 0
        got = "init_rc=%d" % r.returncode
        if ok:
            prefs_path = os.path.join(home, "preferences.json")
            with open(prefs_path, encoding="utf-8") as f:
                doc = json.load(f)
            doc["switch"]["enabled"] = False
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(doc, f)
            d = run(tmp, home, claude)
            ok = d.returncode == 0 and "WARN switch: FrugalFlow off" in d.stdout
            got = "doctor_rc=%d" % d.returncode
        results.append(("4 doctor warns when the switch is off", ok, got))

    # Test 5: --notice prints the notice.
    rn = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    ok = rn.returncode == 0 and rn.stdout.startswith("NAME      doctor_cmd.py")
    results.append(("5 --notice prints the notice", ok, "rc=%d stdout=%r" % (rn.returncode, rn.stdout) if not ok else ""))

    # Test 6: the effective guard mode is shown; observe gets a strong WARN, active an OK.
    with tempfile.TemporaryDirectory() as tmp:
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        ok = init(tmp, home, claude).returncode == 0
        d1 = run(tmp, home, claude)
        pp = os.path.join(home, "preferences.json")
        doc = json.load(open(pp, encoding="utf-8"))
        doc["switch"]["mode"] = "active"
        json.dump(doc, open(pp, "w", encoding="utf-8"))
        d2 = run(tmp, home, claude)
        ok = ok and "WARN guard mode: OBSERVE" in d1.stdout and "NOT block" in d1.stdout and "OK guard mode: active" in d2.stdout
        results.append(("6 doctor shows the guard mode: WARN in observe, OK in active", ok, ""))

    # Test 7: the allow_env_disarm line follows guard.json; an INFO line is never a fail.
    with tempfile.TemporaryDirectory() as tmp:
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        ok = init(tmp, home, claude).returncode == 0
        d1 = run(tmp, home, claude)
        ok = ok and d1.returncode == 0 and \
            "INFO guard.json allow_env_disarm is false: FRUGALFLOW_GUARD=0 is ignored" in d1.stdout
        gp = os.path.join(home, "guard.json")
        doc = json.load(open(gp, encoding="utf-8"))
        doc["allow_env_disarm"] = True
        json.dump(doc, open(gp, "w", encoding="utf-8"))
        d2 = run(tmp, home, claude)
        ok = ok and d2.returncode == 0 and \
            "INFO guard.json allow_env_disarm is true: FRUGALFLOW_GUARD=0 disarms the guard" in d2.stdout
        results.append(("7 doctor reports allow_env_disarm: false by default, true when set", ok, ""))

    # Test 8: a hook command that lost -I is a FAIL (a planted .pth file would run first).
    with tempfile.TemporaryDirectory() as tmp:
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        ok = init(tmp, home, claude).returncode == 0
        sp = os.path.join(claude, "settings.json")
        with open(sp, encoding="utf-8") as f:
            doc = json.load(f)
        stripped = 0
        for group in doc.get("hooks", {}).get("PreToolUse", []):
            for entry in group.get("hooks", []):
                if " -I " in entry.get("command", ""):
                    entry["command"] = entry["command"].replace(" -I ", " ")
                    stripped += 1
        with open(sp, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        d = run(tmp, home, claude)
        ok = ok and stripped > 0 and d.returncode == 1 and "without -I" in d.stdout
        results.append(("8 doctor fails when a hook command lost -I", ok,
                        "stripped=%d rc=%d" % (stripped, d.returncode)))

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
    exit_log.run(main, "doctor_cmd", sys.argv[1:])
