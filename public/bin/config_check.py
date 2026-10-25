import sys
import os
import json
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from config_rules import validate_models, secret_errors
from layers import verify, route
from ceilings import validate_preferences, validate_project, tighten

NOTICE = ("NAME      config_check.py - refuses a configuration that breaks the contract, and shows where each ceiling came from.\n"
"READS     models.json and preferences.json in --home, else FRUGALFLOW_HOME, else ~/.frugalflow;\n"
"          the project file named by --project, else .frugalflow.json in the current directory if present.\n"
"          A missing models.json or preferences.json stops with exit 2.\n"
"WRITES    nothing: one OK or NO line per file, the effective ceilings with their source, then CONFIG OK or CONFIG REFUSED.\n"
"EXAMPLE   python3 config_check.py --home ~/.frugalflow --role code\n"
"PITFALLS  2026-09-23 a project file that loosens a ceiling is refused, never clamped: a silently ignored setting is believed in force.")

USAGE = "usage: config_check.py [--home DIR] [--project FILE] [--role NAME] | --notice | --autotest"


def _fmt_val(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    return str(v)


def main(argv):
    home_val = None
    project_val = None
    role_val = None
    do_notice = False
    do_autotest = False

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            home_val = argv[i + 1]
            i += 2
        elif a == "--project":
            if i + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            project_val = argv[i + 1]
            i += 2
        elif a == "--role":
            if i + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            role_val = argv[i + 1]
            i += 2
        elif a == "--notice":
            do_notice = True
            i += 1
        elif a == "--autotest":
            do_autotest = True
            i += 1
        else:
            print(USAGE)
            sys.exit(2)

    if do_notice:
        print(NOTICE)
        sys.exit(0)

    if do_autotest:
        _autotest()
        return

    # Determine home
    if home_val is None:
        home_val = os.environ.get("FRUGALFLOW_HOME")
    if home_val is None:
        home_val = os.path.expanduser("~/.frugalflow")

    models_path = os.path.join(home_val, "models.json")
    prefs_path = os.path.join(home_val, "preferences.json")

    if project_val is not None:
        project_path = project_val
    else:
        cand = ".frugalflow.json"
        if os.path.isfile(cand):
            project_path = cand
        else:
            project_path = None

    # Check existence
    for p in [models_path, prefs_path]:
        if not os.path.isfile(p):
            print("missing file: " + p)
            sys.exit(2)
    if project_path is not None:
        if not os.path.isfile(project_path):
            print("missing file: " + project_path)
            sys.exit(2)

    print("CONFIG " + home_val)

    total_errors = []

    # --- models ---
    models_doc = None
    try:
        with open(models_path, encoding="utf-8") as f:
            models_doc = json.load(f)
        errs = validate_models(models_doc) + secret_errors(models_doc) + verify(models_doc)
    except json.JSONDecodeError:
        errs = ["not valid JSON"]
    lbl = os.path.basename(models_path)
    if not errs:
        print("  OK " + lbl)
    else:
        for e in errs:
            print("  NO " + lbl + ": " + e)
        total_errors.extend(errs)

    # --- preferences ---
    prefs_doc = None
    try:
        with open(prefs_path, encoding="utf-8") as f:
            prefs_doc = json.load(f)
        errs = validate_preferences(prefs_doc) + secret_errors(prefs_doc)
    except json.JSONDecodeError:
        errs = ["not valid JSON"]
    lbl = os.path.basename(prefs_path)
    if not errs:
        print("  OK " + lbl)
    else:
        for e in errs:
            print("  NO " + lbl + ": " + e)
        total_errors.extend(errs)

    # --- project ---
    project_doc = None
    project_lbl = ""
    if project_path is not None:
        try:
            with open(project_path, encoding="utf-8") as f:
                project_doc = json.load(f)
            errs = validate_project(project_doc) + secret_errors(project_doc)
        except json.JSONDecodeError:
            errs = ["not valid JSON"]
        project_lbl = os.path.basename(project_path)
        if not errs:
            print("  OK " + project_lbl)
        else:
            for e in errs:
                print("  NO " + project_lbl + ": " + e)
            total_errors.extend(errs)
    else:
        print("  -- no project file")

    # Step 5: if any error from step 4, skip to step 8
    if total_errors:
        print("CONFIG REFUSED " + str(len(total_errors)))
        sys.exit(8)

    # Step 6: tighten
    effective, violations = tighten(prefs_doc, project_doc)
    for v in violations:
        print("  NO " + project_lbl + ": " + v)
    total_errors.extend(violations)

    print("EFFECTIVE")
    for fpath, value, source in effective:
        print("  " + fpath + " = " + _fmt_val(value) + "  (" + source + ")")

    # Step 7: route
    if role_val is not None and not violations:
        max_trust = None
        for fpath, value, source in effective:
            if fpath == "ceilings.max_trust":
                max_trust = value
                break
        model, reason = route(models_doc, role_val, max_trust)
        if model is not None:
            print("ROUTE " + role_val + " -> " + model["id"] + " (" + model["name"] + ", " + model["trust"] + ")")
        else:
            print("ROUTE " + role_val + " REFUSED: " + reason)
            total_errors.append(reason)

    # Step 8
    if not total_errors:
        print("CONFIG OK")
        sys.exit(0)
    else:
        print("CONFIG REFUSED " + str(len(total_errors)))
        sys.exit(8)


def _autotest():
    D = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(D, "good"), exist_ok=True)
        os.makedirs(os.path.join(D, "leaky"), exist_ok=True)

        models_good = {"schema_version": "1",
            "models": [{"id": "a", "name": "m", "location": "local", "endpoint": "http://127.0.0.1:9000/v1", "context_window": 65536, "paid": False, "trust": "private", "key_env": ""},
                        {"id": "r", "name": "n", "location": "remote", "endpoint": "https://api.example.com/v1", "context_window": 131072, "paid": True, "trust": "untrusted_third_party", "key_env": "REMOTE_KEY"}],
            "layers": [{"name": "reading", "delegable": True}, {"name": "kept", "delegable": False}],
            "roles": [{"name": "code", "layer": "reading", "model": "a"},
                      {"name": "remote", "layer": "reading", "model": "r"},
                      {"name": "judgment", "layer": "kept", "model": ""}]}

        models_leaky = json.loads(json.dumps(models_good))
        models_leaky["models"][0]["api_key"] = "abc123"

        prefs = {"schema_version": "1",
            "verbosity": {"final_answer_words": 120, "step_message_words": 30},
            "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 50000},
            "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
            "grouping": {"independent_calls_same_turn": True}}

        project = {"schema_version": "1", "ceilings": {"max_trust": "private", "max_tries": 2}}
        loose = {"schema_version": "1", "ceilings": {"max_tries": 9}}

        with open(os.path.join(D, "good", "models.json"), "w", encoding="utf-8") as f:
            json.dump(models_good, f)
        with open(os.path.join(D, "good", "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        with open(os.path.join(D, "leaky", "models.json"), "w", encoding="utf-8") as f:
            json.dump(models_leaky, f)
        with open(os.path.join(D, "leaky", "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        with open(os.path.join(D, "project.json"), "w", encoding="utf-8") as f:
            json.dump(project, f)
        with open(os.path.join(D, "loose.json"), "w", encoding="utf-8") as f:
            json.dump(loose, f)

        script = os.path.abspath(__file__)
        all_pass = True

        # Test 1
        r = subprocess.run(
            [sys.executable, script, "--home", os.path.join(D, "good"),
             "--project", os.path.join(D, "project.json"), "--role", "code"],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok1 = (r.returncode == 0
               and (lines and lines[-1] == "CONFIG OK")
               and ("  ceilings.max_trust = private  (project)" in lines)
               and ("ROUTE code -> a (m, private)" in lines))
        if ok1:
            print("PASS 1: code=0, CONFIG OK, ceiling private (project), route ok")
        else:
            print("FAIL 1: expected code=0+CONFIG OK+ceiling+route | got code={} last={}".format(r.returncode, lines[-1] if lines else ""))
            all_pass = False

        # Test 2
        r = subprocess.run(
            [sys.executable, script, "--home", os.path.join(D, "good"),
             "--project", os.path.join(D, "loose.json")],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok2 = (r.returncode == 8
               and ("  NO loose.json: project loosens ceilings.max_tries: 9 > 3" in lines)
               and (lines and lines[-1] == "CONFIG REFUSED 1"))
        if ok2:
            print("PASS 2: code=8, loosening violation, CONFIG REFUSED 1")
        else:
            print("FAIL 2: expected code=8+violation+REFUSED 1 | got code={} last={}".format(r.returncode, lines[-1] if lines else ""))
            all_pass = False

        # Test 3
        r = subprocess.run(
            [sys.executable, script, "--home", os.path.join(D, "leaky")],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok3 = (r.returncode == 8
               and ("  NO models.json: secret value at models[0].api_key: name an environment variable in key_env instead" in lines)
               and ("  -- no project file" in lines))
        if ok3:
            print("PASS 3: code=8, secret in models, no project file")
        else:
            print("FAIL 3: expected code=8+secret+no project | got code={} last={}".format(r.returncode, lines[-1] if lines else ""))
            all_pass = False

        # Test 4
        r = subprocess.run(
            [sys.executable, script, "--home", os.path.join(D, "absent")],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok4 = (r.returncode == 2
               and (lines and lines[0].startswith("missing file: ")))
        if ok4:
            print("PASS 4: code=2, missing file")
        else:
            print("FAIL 4: expected code=2+missing file | got code={} first={}".format(r.returncode, lines[0] if lines else ""))
            all_pass = False

        # Test 5a
        r = subprocess.run(
            [sys.executable, script, "--home", os.path.join(D, "good"),
             "--project", os.path.join(D, "project.json"), "--role", "remote"],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok5a = (r.returncode == 8
                and ("ROUTE remote REFUSED: model r trust untrusted_third_party exceeds ceiling private" in lines))
        if ok5a:
            print("PASS 5a: code=8, route refused for remote")
        else:
            print("FAIL 5a: expected code=8+REFUSED | got code={} last={}".format(r.returncode, lines[-1] if lines else ""))
            all_pass = False

        # Test 5b
        r = subprocess.run(
            [sys.executable, script, "--notice"],
            capture_output=True, text=True, cwd=D)
        lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
        ok5b = (r.returncode == 0
                and (lines and lines[0].startswith("NAME      config_check.py")))
        if ok5b:
            print("PASS 5b: code=0, notice printed")
        else:
            print("FAIL 5b: expected code=0+notice | got code={} first={}".format(r.returncode, lines[0] if lines else ""))
            all_pass = False

        sys.exit(0 if all_pass else 1)
    finally:
        shutil.rmtree(D)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "config_check", sys.argv[1:])
