import os
import sys
import json
import copy
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ceilings

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE = (
    "usage: config_cmd.py config [set KEY VALUE] | on | off | mode MODE | display NAME on|off [--home DIR] | --notice | --autotest"
)

NOTICE = (
    "NAME      config_cmd.py - the frugalflow config/on/off/mode/display subcommand: shows and sets preferences.json.\n"
    "READS     preferences.json in --home, else FRUGALFLOW_HOME, else ~/.frugalflow.\n"
    "WRITES    preferences.json only when a setting changes; a refused value leaves the file byte for byte as it was.\n"
    "EXAMPLE   python3 config_cmd.py config --home ~/.frugalflow\n"
    "PITFALLS  2026-10-03 a value is parsed as JSON first and kept as a string when that fails, so a trust level can be set without quotes.\n"
    "          2026-10-04 display takes the on screen names (statusline, turn-line, summary), which map to the display.* keys of preferences.json.\n"
)

MEANING = {
    "verbosity.final_answer_words": "ceiling on the final answer",
    "verbosity.step_message_words": "ceiling on a progress message",
    "ceilings.max_trust": "the least trusted model content may be sent to",
    "ceilings.max_tries": "attempts before a delegation gives up",
    "ceilings.max_output_tokens": "ceiling on one delegated answer",
    "splitting.max_proofs_per_task": "a task needing more proofs is split",
    "splitting.max_brief_lines": "a longer brief is the sign of a task too big",
    "grouping.independent_calls_same_turn": "send independent tool calls together",
    "switch.enabled": "on (true) or off (false); off lets every call pass the economy barrier, security checks stay on",
    "switch.mode": "observe: nothing is blocked, avoidable calls are counted; active: the barrier blocks; silent: active, one line at session start only",
    "display.statusline": "show the FrugalFlow segment in the status line",
    "display.turn_line": "one short line when a call would have been avoided (observe mode)",
    "display.summary": "the session summary",
}

KNOWN = set()
for (_section, _key, _kind) in ceilings.KEYS:
    KNOWN.add(_section + "." + _key)
KNOWN.add("switch.enabled")
KNOWN.add("switch.mode")
KNOWN.add("display.statusline")
KNOWN.add("display.turn_line")
KNOWN.add("display.summary")

DISPLAY_NAMES = {
    "statusline": "display.statusline",
    "turn-line": "display.turn_line",
    "summary": "display.summary",
}


def _split(argv):
    home = None
    pos = []
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            if i + 1 >= len(argv):
                return None, None
            home = argv[i + 1]
            i += 2
        else:
            pos.append(a)
            i += 1
    return pos, home


def _write_prefs(path, doc):
    directory = os.path.dirname(path) or "."
    fd, tmp = tempfile.mkstemp(dir=directory, prefix=".preferences-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        os.replace(tmp, path)
    except BaseException:
        try:
            os.close(fd)
        except OSError:
            pass
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def _with_value(doc, key, value):
    new = copy.deepcopy(doc)
    if key.startswith("switch."):
        switch = new.get("switch")
        if not isinstance(switch, dict):
            enabled, mode = ceilings.switch_state(new)
            switch = {"enabled": enabled, "mode": mode}
        else:
            switch = dict(switch)
        if key == "switch.enabled":
            switch["enabled"] = value
        else:
            switch["mode"] = value
        new["switch"] = switch
    elif key.startswith("display."):
        display = new.get("display")
        if not isinstance(display, dict):
            display = dict(ceilings.display_state(new))
        else:
            display = dict(display)
        display[key.split(".", 1)[1]] = value
        new["display"] = display
    else:
        section, k = key.split(".", 1)
        if not isinstance(new.get(section), dict):
            new[section] = {}
        new[section][k] = value
    return new


def _show(doc):
    for (section, key, _kind) in ceilings.KEYS:
        path = section + "." + key
        print(path + " = " + json.dumps(doc[section][key], ensure_ascii=False) + "  # " + MEANING[path])
    enabled, mode = ceilings.switch_state(doc)
    print("switch.enabled = " + json.dumps(enabled, ensure_ascii=False) + "  # " + MEANING["switch.enabled"])
    print("switch.mode = " + json.dumps(mode, ensure_ascii=False) + "  # " + MEANING["switch.mode"])
    display = ceilings.display_state(doc)
    for key in ("display.statusline", "display.turn_line", "display.summary"):
        print(key + " = " + json.dumps(display[key.split(".", 1)[1]], ensure_ascii=False) + "  # " + MEANING[key])
    return 0


def _set(doc, key, value_str, prefs_path):
    if key not in KNOWN:
        print("REFUSED: unknown key " + key)
        return 2
    try:
        value = json.loads(value_str)
    except ValueError:
        value = value_str
    new = _with_value(doc, key, value)
    errors = ceilings.validate_preferences(new)
    if errors:
        print("REFUSED: " + "; ".join(errors))
        return 2
    _write_prefs(prefs_path, new)
    print("SET " + key + " = " + json.dumps(value, ensure_ascii=False))
    return 0


def _on_off(doc, prefs_path, enabled):
    new = _with_value(doc, "switch.enabled", enabled)
    _write_prefs(prefs_path, new)
    _enabled, mode = ceilings.switch_state(new)
    print("FrugalFlow " + ("on" if enabled else "off") + " (mode " + mode + ")")
    return 0


def _mode(doc, prefs_path, mode):
    new = _with_value(doc, "switch.mode", mode)
    _write_prefs(prefs_path, new)
    print("FrugalFlow mode " + mode)
    return 0


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    if not argv:
        print(USAGE)
        return 2
    cmd = argv[0]
    if cmd not in ("config", "on", "off", "mode", "display"):
        print(USAGE)
        return 2

    pos, home = _split(argv[1:])
    if pos is None:
        print(USAGE)
        return 2
    home = home or os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")

    prefs_path = os.path.join(home, "preferences.json")
    try:
        with open(prefs_path, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        print("cannot read preferences: " + prefs_path)
        return 2
    errors = ceilings.validate_preferences(doc)
    if errors:
        print("preferences invalid: " + "; ".join(errors))
        return 2

    if cmd == "config":
        if not pos:
            return _show(doc)
        if len(pos) == 3 and pos[0] == "set":
            return _set(doc, pos[1], pos[2], prefs_path)
        print(USAGE)
        return 2
    if cmd == "on":
        if pos:
            print(USAGE)
            return 2
        return _on_off(doc, prefs_path, True)
    if cmd == "off":
        if pos:
            print(USAGE)
            return 2
        return _on_off(doc, prefs_path, False)
    if cmd == "mode":
        if len(pos) != 1:
            print(USAGE)
            return 2
        mode = pos[0]
        if mode not in ceilings.MODES:
            print(USAGE)
            return 2
        return _mode(doc, prefs_path, mode)
    if cmd == "display":
        if len(pos) != 2:
            print(USAGE)
            return 2
        if pos[0] not in DISPLAY_NAMES or pos[1] not in ("on", "off"):
            print(USAGE)
            return 2
        new = _with_value(doc, DISPLAY_NAMES[pos[0]], pos[1] == "on")
        _write_prefs(prefs_path, new)
        print("FrugalFlow display " + pos[0] + " " + pos[1])
        return 0
    print(USAGE)
    return 2


def _autotest():
    import subprocess

    script = os.path.abspath(__file__)
    PREFS = {"schema_version": "1",
             "verbosity": {"final_answer_words": 150, "step_message_words": 35},
             "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 60000},
             "splitting": {"max_proofs_per_task": 5, "max_brief_lines": 140},
             "grouping": {"independent_calls_same_turn": True}}
    results = []

    def write(tmp, home, doc):
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)

    def run(tmp, *args):
        env = dict(os.environ)
        env["HOME"] = tmp
        return subprocess.run([sys.executable, script] + list(args),
                              capture_output=True, text=True, env=env, cwd=tmp)

    # Test 1: config lists every key with a meaning.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r = run(tmp, "config", "--home", home)
        ok = (r.returncode == 0
              and "verbosity.final_answer_words = 150" in r.stdout
              and 'ceilings.max_trust = "trusted_third_party"' in r.stdout
              and "switch.enabled = true" in r.stdout
              and 'switch.mode = "active"' in r.stdout
              and "display.statusline = true" in r.stdout
              and "display.turn_line = true" in r.stdout
              and "display.summary = true" in r.stdout)
        results.append(("1 config lists every key with its meaning", ok,
                        "rc=%d" % r.returncode if not ok else ""))

    # Test 2: config set stores a parsed value.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r = run(tmp, "config", "set", "ceilings.max_tries", "5", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc = json.load(f)
        ok = (r.returncode == 0
              and doc["ceilings"]["max_tries"] == 5
              and "SET ceilings.max_tries = 5" in r.stdout)
        results.append(("2 config set stores a parsed value", ok, "rc=%d" % r.returncode if not ok else ""))

    # Test 3: config set a string without quotes.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r = run(tmp, "config", "set", "ceilings.max_trust", "private", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc = json.load(f)
        ok = (r.returncode == 0
              and doc["ceilings"]["max_trust"] == "private"
              and 'SET ceilings.max_trust = "private"' in r.stdout)
        results.append(("3 config set keeps a string value without quotes", ok, "rc=%d" % r.returncode if not ok else ""))

    # Test 4: config set refused leaves the file byte for byte.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        prefs_path = os.path.join(home, "preferences.json")
        with open(prefs_path, "rb") as f:
            before = f.read()
        r = run(tmp, "config", "set", "verbosity.final_answer_words", "0", "--home", home)
        with open(prefs_path, "rb") as f:
            after = f.read()
        ok = r.returncode == 2 and "REFUSED" in r.stdout and before == after
        results.append(("4 config set refused leaves the file byte for byte", ok, "rc=%d" % r.returncode if not ok else ""))

    # Test 5: config set unknown key is refused 2.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r = run(tmp, "config", "set", "nope.key", "1", "--home", home)
        ok = r.returncode == 2 and "REFUSED" in r.stdout
        results.append(("5 config set unknown key is refused 2", ok, "rc=%d" % r.returncode if not ok else ""))

    # Test 6: on, off and mode keep the other half of the switch.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r_on = run(tmp, "on", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc_on = json.load(f)
        r_off = run(tmp, "off", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc_off = json.load(f)
        r_mode = run(tmp, "mode", "silent", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc_mode = json.load(f)
        ok = (r_on.returncode == 0 and doc_on["switch"]["enabled"] is True and doc_on["switch"]["mode"] == "active"
              and r_off.returncode == 0 and doc_off["switch"]["enabled"] is False and doc_off["switch"]["mode"] == "active"
              and r_mode.returncode == 0 and doc_mode["switch"]["mode"] == "silent" and doc_mode["switch"]["enabled"] is False)
        results.append(("6 on, off and mode keep the other half of the switch", ok,
                        "on=%d off=%d mode=%d" % (r_on.returncode, r_off.returncode, r_mode.returncode) if not ok else ""))

    # Test 7: bad mode is usage 2 and missing preferences is 2.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r_bad = run(tmp, "mode", "bogus", "--home", home)
        r_missing = run(tmp, "config", "--home", os.path.join(tmp, "nohome"))
        ok = r_bad.returncode == 2 and r_missing.returncode == 2
        results.append(("7 bad mode and missing preferences are both 2", ok,
                        "bad=%d missing=%d" % (r_bad.returncode, r_missing.returncode) if not ok else ""))

    # Test 8: --notice prints the notice.
    rn = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    ok = rn.returncode == 0 and rn.stdout.startswith("NAME      config_cmd.py")
    results.append(("8 --notice prints the notice", ok,
                    "rc=%d stdout=%r" % (rn.returncode, rn.stdout) if not ok else ""))

    # Test 9: display turns a setting off and on with exit 0.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        r_off = run(tmp, "display", "statusline", "off", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc_off = json.load(f)
        r_on = run(tmp, "display", "turn-line", "on", "--home", home)
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc_on = json.load(f)
        ok = (r_off.returncode == 0
              and "FrugalFlow display statusline off" in r_off.stdout
              and doc_off["display"]["statusline"] is False
              and doc_off["display"]["turn_line"] is True
              and r_on.returncode == 0
              and "FrugalFlow display turn-line on" in r_on.stdout
              and doc_on["display"]["turn_line"] is True
              and doc_on["display"]["statusline"] is False)
        results.append(("9 display turns a setting off and on with exit 0", ok,
                        "off=%d on=%d" % (r_off.returncode, r_on.returncode) if not ok else ""))

    # Test 10: a bad display name, a bad value and a non-boolean config set are refused 2.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write(tmp, home, PREFS)
        prefs_path = os.path.join(home, "preferences.json")
        with open(prefs_path, "rb") as f:
            before = f.read()
        r_badname = run(tmp, "display", "logo", "off", "--home", home)
        r_badvalue = run(tmp, "display", "summary", "now", "--home", home)
        r_notbool = run(tmp, "config", "set", "display.statusline", "yes", "--home", home)
        with open(prefs_path, "rb") as f:
            after = f.read()
        ok = (r_badname.returncode == 2
              and r_badvalue.returncode == 2
              and r_notbool.returncode == 2
              and "REFUSED" in r_notbool.stdout
              and before == after)
        results.append(("10 display name/value and non-boolean config set are refused 2", ok,
                        "badname=%d badvalue=%d notbool=%d" % (r_badname.returncode, r_badvalue.returncode, r_notbool.returncode) if not ok else ""))

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
    exit_log.run(main, "config_cmd", sys.argv[1:])
