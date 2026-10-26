import sys
import os
import subprocess

TRUST = ["private", "trusted_third_party", "untrusted_third_party"]

MODES = ("observe", "active", "silent")

KEYS = [
    ("verbosity", "final_answer_words", "count"),
    ("verbosity", "step_message_words", "count"),
    ("ceilings", "max_trust", "trust"),
    ("ceilings", "max_tries", "count"),
    ("ceilings", "max_output_tokens", "count"),
    ("splitting", "max_proofs_per_task", "count"),
    ("splitting", "max_brief_lines", "count"),
    ("grouping", "independent_calls_same_turn", "flag"),
]

SECTIONS = ["verbosity", "ceilings", "splitting", "grouping"]


def _check_value(path, kind, value):
    if kind == "count":
        if not isinstance(value, int) or isinstance(value, bool) or value <= 0:
            return path + " must be an integer above 0"
    elif kind == "trust":
        if value not in TRUST:
            return path + " must be one of private, trusted_third_party, untrusted_third_party"
    elif kind == "flag":
        if not isinstance(value, bool):
            return path + " must be true or false"
    return None


def _section_keys(section):
    return {k for (s, k, t) in KEYS if s == section}


def _check_switch(doc):
    if "switch" not in doc:
        return []
    switch = doc["switch"]
    errors = []
    if not isinstance(switch, dict):
        errors.append("switch must be an object")
        return errors
    for k in switch:
        if k not in ("enabled", "mode"):
            errors.append("unknown key switch." + k)
    if "enabled" not in switch:
        errors.append("switch.enabled is missing")
    elif not isinstance(switch["enabled"], bool):
        errors.append("switch.enabled must be true or false")
    if "mode" not in switch:
        errors.append("switch.mode is missing")
    elif switch["mode"] not in MODES:
        errors.append("switch.mode must be one of observe, active, silent")
    return errors


def _check_display(doc):
    if "display" not in doc:
        return []
    display = doc["display"]
    errors = []
    if not isinstance(display, dict):
        errors.append("display must be an object")
        return errors
    for k in display:
        if k not in ("statusline", "turn_line", "summary"):
            errors.append("unknown key display." + k)
    for k in ("statusline", "turn_line", "summary"):
        if k not in display:
            errors.append("display." + k + " is missing")
        elif not isinstance(display[k], bool):
            errors.append("display." + k + " must be true or false")
    return errors


def validate_preferences(doc):
    if not isinstance(doc, dict):
        return ["document must be an object"]
    errors = []
    if doc.get("schema_version") != "1":
        errors.append("schema_version must be 1")
    for key in doc:
        if key == "schema_version" or key == "switch" or key == "display" or key in SECTIONS:
            continue
        errors.append("unknown key " + key)
    for section in SECTIONS:
        if section not in doc:
            continue
        if not isinstance(doc[section], dict):
            errors.append(section + " must be an object")
        else:
            valid = _section_keys(section)
            for k in doc[section]:
                if k not in valid:
                    errors.append("unknown key " + section + "." + k)
    for (section, key, kind) in KEYS:
        if section not in doc:
            errors.append(section + "." + key + " is missing")
        elif not isinstance(doc[section], dict):
            pass
        elif key not in doc[section]:
            errors.append(section + "." + key + " is missing")
        else:
            msg = _check_value(section + "." + key, kind, doc[section][key])
            if msg:
                errors.append(msg)
    errors.extend(_check_switch(doc))
    errors.extend(_check_display(doc))
    return errors


def validate_project(doc):
    if not isinstance(doc, dict):
        return ["document must be an object"]
    errors = []
    if doc.get("schema_version") != "1":
        errors.append("schema_version must be 1")
    for key in doc:
        if key == "grouping":
            errors.append("a project may not set grouping")
        elif key == "switch":
            errors.append("a project may not set switch")
        elif key == "display":
            errors.append("a project may not set display")
        elif key == "schema_version" or key in SECTIONS:
            continue
        else:
            errors.append("unknown key " + key)
    for section in SECTIONS:
        if section == "grouping":
            continue
        if section not in doc:
            continue
        if not isinstance(doc[section], dict):
            errors.append(section + " must be an object")
        else:
            valid = _section_keys(section)
            for k in doc[section]:
                if k not in valid:
                    errors.append("unknown key " + section + "." + k)
    for (section, key, kind) in KEYS:
        if section == "grouping":
            continue
        if section not in doc:
            continue
        elif not isinstance(doc[section], dict):
            pass
        elif key not in doc[section]:
            continue
        else:
            msg = _check_value(section + "." + key, kind, doc[section][key])
            if msg:
                errors.append(msg)
    return errors


def switch_state(doc):
    switch = doc.get("switch")
    if switch is None:
        return (True, "active")
    return (switch["enabled"], switch["mode"])


def display_state(doc):
    display = doc.get("display")
    if display is None:
        return {"statusline": True, "turn_line": True, "summary": True}
    return {k: display[k] for k in ("statusline", "turn_line", "summary")}


def tighten(prefs, project):
    effective = []
    violations = []
    for (section, key, kind) in KEYS:
        path = section + "." + key
        pref_val = prefs[section][key]
        if project is None:
            effective.append((path, pref_val, "preferences"))
            continue
        if section not in project or not isinstance(project.get(section), dict) or key not in project[section]:
            effective.append((path, pref_val, "preferences"))
            continue
        proj_val = project[section][key]
        if kind == "count":
            if proj_val <= pref_val:
                effective.append((path, proj_val, "project"))
            else:
                violations.append("project loosens " + path + ": " + str(proj_val) + " > " + str(pref_val))
                effective.append((path, pref_val, "preferences"))
        elif kind == "trust":
            if TRUST.index(proj_val) <= TRUST.index(pref_val):
                effective.append((path, proj_val, "project"))
            else:
                violations.append("project loosens " + path + ": " + str(proj_val) + " > " + str(pref_val))
                effective.append((path, pref_val, "preferences"))
        elif kind == "flag":
            effective.append((path, pref_val, "preferences"))
    return (effective, violations)


NOTICE = (
    "NAME      ceilings.py - validates preferences.json and .frugalflow.json, and computes the effective ceilings.\n"
    "READS     nothing: pure module; it reads the decoded JSON it is given.\n"
    "WRITES    nothing: tighten() returns each effective value with its source, and the list of violations.\n"
    "EXAMPLE   python3 ceilings.py --notice\n"
    "PITFALLS  2026-09-23 a project file may only tighten: a loosened ceiling is a violation, never silently clamped.\n"
    "          2026-10-03 preferences had no switch, so an install could not turn delegation off; switch (enabled + mode) now lives only in preferences.json.\n"
    "          2026-10-04 display is optional and refused in a project, like switch: absent means everything is shown.\n"
)


def _autotest():
    PREFS = {"schema_version": "1",
             "verbosity": {"final_answer_words": 120, "step_message_words": 30},
             "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 50000},
             "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
             "grouping": {"independent_calls_same_turn": True}}

    PROJECT = {"schema_version": "1", "ceilings": {"max_trust": "private", "max_tries": 2}}

    LOOSE = {"schema_version": "1", "ceilings": {"max_trust": "untrusted_third_party", "max_tries": 9}, "splitting": {"max_brief_lines": 100}}

    BAD_PREFS = {"schema_version": "1",
                 "verbosity": {"final_answer_words": 0, "step_message_words": 35, "colour": "red"},
                 "ceilings": {"max_trust": "friends", "max_tries": 3},
                 "splitting": "all",
                 "grouping": {"independent_calls_same_turn": "yes"},
                 "extra": 1}

    BAD_PROJECT = {"schema_version": "1", "grouping": {"independent_calls_same_turn": False}, "ceilings": {"max_tries": True, "max_budget": 3}}

    all_pass = True

    # Test 1
    r1 = (validate_preferences(PREFS) == [] and validate_project(PROJECT) == [] and validate_project(LOOSE) == [])
    if r1:
        print("PASS test1: valid docs return []")
    else:
        print("FAIL test1: got prefs=" + str(validate_preferences(PREFS)) + " project=" + str(validate_project(PROJECT)) + " loose=" + str(validate_project(LOOSE)))
        all_pass = False

    # Test 2
    expected2 = ["unknown key extra", "unknown key verbosity.colour", "splitting must be an object", "verbosity.final_answer_words must be an integer above 0", "ceilings.max_trust must be one of private, trusted_third_party, untrusted_third_party", "ceilings.max_output_tokens is missing", "grouping.independent_calls_same_turn must be true or false"]
    got2 = validate_preferences(BAD_PREFS)
    if got2 == expected2:
        print("PASS test2: BAD_PREFS returns 7 expected errors")
    else:
        print("FAIL test2: expected " + str(expected2) + " got " + str(got2))
        all_pass = False

    # Test 3
    expected3 = ["a project may not set grouping", "unknown key ceilings.max_budget", "ceilings.max_tries must be an integer above 0"]
    got3 = validate_project(BAD_PROJECT)
    if got3 == expected3:
        print("PASS test3: BAD_PROJECT returns 3 expected errors")
    else:
        print("FAIL test3: expected " + str(expected3) + " got " + str(got3))
        all_pass = False

    # Test 4
    expected_eff = [("verbosity.final_answer_words", 120, "preferences"), ("verbosity.step_message_words", 30, "preferences"), ("ceilings.max_trust", "private", "project"), ("ceilings.max_tries", 2, "project"), ("ceilings.max_output_tokens", 50000, "preferences"), ("splitting.max_proofs_per_task", 4, "preferences"), ("splitting.max_brief_lines", 100, "preferences"), ("grouping.independent_calls_same_turn", True, "preferences")]
    eff4, viol4 = tighten(PREFS, PROJECT)
    r4a = (eff4, viol4) == (expected_eff, [])
    eff5, viol5 = tighten(PREFS, LOOSE)
    expected_viol5 = ["project loosens ceilings.max_trust: untrusted_third_party > trusted_third_party", "project loosens ceilings.max_tries: 9 > 3"]
    r4b = viol5 == expected_viol5
    r4c = eff5[2] == ("ceilings.max_trust", "trusted_third_party", "preferences")
    r4d = eff5[6] == ("splitting.max_brief_lines", 100, "project")
    if r4a and r4b and r4c and r4d:
        print("PASS test4: tighten produces correct effective values and violations")
    else:
        print("FAIL test4: eff_project=" + str(eff4) + " viol_project=" + str(viol4) + " viol_loose=" + str(viol5) + " eff_loose[2]=" + str(eff5[2]) + " eff_loose[6]=" + str(eff5[6]))
        all_pass = False

    # Test 5
    result = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    r5 = result.returncode == 0 and result.stdout.startswith("NAME      ceilings.py")
    if r5:
        print("PASS test5: subprocess --notice exits 0 and prints notice")
    else:
        print("FAIL test5: returncode=" + str(result.returncode) + " stdout=" + repr(result.stdout))
        all_pass = False

    # Test 6
    PREFS_SWITCH = dict(PREFS)
    PREFS_SWITCH["switch"] = {"enabled": False, "mode": "silent"}
    BAD_SWITCH = dict(PREFS)
    BAD_SWITCH["switch"] = {"enabled": "yes", "mode": "loud", "extra": 1}
    BAD_SWITCH2 = dict(PREFS)
    BAD_SWITCH2["switch"] = {"enabled": False}
    BAD_SWITCH3 = dict(PREFS)
    BAD_SWITCH3["switch"] = None
    PROJECT_SWITCH = {"schema_version": "1", "switch": {"enabled": False, "mode": "silent"}}
    expected6a = ["unknown key switch.extra", "switch.enabled must be true or false", "switch.mode must be one of observe, active, silent"]
    got6a = validate_preferences(BAD_SWITCH)
    r6 = (validate_preferences(PREFS_SWITCH) == []
          and got6a == expected6a
          and validate_preferences(BAD_SWITCH2) == ["switch.mode is missing"]
          and validate_preferences(BAD_SWITCH3) == ["switch must be an object"]
          and validate_project(PROJECT_SWITCH) == ["a project may not set switch"]
          and switch_state(PREFS) == (True, "active")
          and switch_state(PREFS_SWITCH) == (False, "silent"))
    if r6:
        print("PASS test6: switch optional, exact keys, refused in project, switch_state defaults")
    else:
        print("FAIL test6: got6a=" + str(got6a) + " prefs_switch=" + str(validate_preferences(PREFS_SWITCH)) + " bad2=" + str(validate_preferences(BAD_SWITCH2)) + " project_switch=" + str(validate_project(PROJECT_SWITCH)) + " state0=" + str(switch_state(PREFS)) + " state1=" + str(switch_state(PREFS_SWITCH)))
        all_pass = False

    # Test 7
    PREFS_DISPLAY = dict(PREFS)
    PREFS_DISPLAY["display"] = {"statusline": False, "turn_line": True, "summary": False}
    BAD_DISPLAY = dict(PREFS)
    BAD_DISPLAY["display"] = {"statusline": "yes", "turn_line": 1, "extra": True}
    BAD_DISPLAY2 = dict(PREFS)
    BAD_DISPLAY2["display"] = {"statusline": True}
    BAD_DISPLAY3 = dict(PREFS)
    BAD_DISPLAY3["display"] = None
    PROJECT_DISPLAY = {"schema_version": "1", "display": {"statusline": False, "turn_line": True, "summary": True}}
    expected7a = ["unknown key display.extra", "display.statusline must be true or false", "display.turn_line must be true or false", "display.summary is missing"]
    got7a = validate_preferences(BAD_DISPLAY)
    r7 = (validate_preferences(PREFS_DISPLAY) == []
          and got7a == expected7a
          and validate_preferences(BAD_DISPLAY2) == ["display.turn_line is missing", "display.summary is missing"]
          and validate_preferences(BAD_DISPLAY3) == ["display must be an object"]
          and validate_project(PROJECT_DISPLAY) == ["a project may not set display"]
          and display_state(PREFS) == {"statusline": True, "turn_line": True, "summary": True}
          and display_state(PREFS_DISPLAY) == {"statusline": False, "turn_line": True, "summary": False})
    if r7:
        print("PASS test7: display optional, exact keys, refused in project, display_state defaults")
    else:
        print("FAIL test7: got7a=" + str(got7a) + " prefs_display=" + str(validate_preferences(PREFS_DISPLAY)) + " bad2=" + str(validate_preferences(BAD_DISPLAY2)) + " project_display=" + str(validate_project(PROJECT_DISPLAY)))
        all_pass = False

    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) < 2:
        print("usage: ceilings.py --notice | --autotest")
        sys.exit(2)
    if sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: ceilings.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "ceilings", sys.argv[1:])
