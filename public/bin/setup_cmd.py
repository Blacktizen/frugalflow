import os
import sys
import json
import copy
import shutil
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import layers
import config_rules
import env_detect

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE = "usage: setup_cmd.py [--home DIR] [--answer ROLE=MODEL_ID]... [--ollama-url URL] [--lmstudio-url URL] | --notice | --autotest"

NOTICE = (
    "NAME      setup_cmd.py - the frugalflow setup subcommand: walks the layers of models.json and sets which model does each role.\n"
    "READS     models.json in --home, else FRUGALFLOW_HOME, else ~/.frugalflow; probes the local engines and the *_API_KEY variables to propose the detected models first.\n"
    "WRITES    models.json only when a role changes, atomically; a refused answer leaves the file byte for byte as it was.\n"
    "EXAMPLE   python3 setup_cmd.py --home ~/.frugalflow --answer code=local-reader\n"
    "PITFALLS  2026-10-09 a role of a kept layer is never given a model: the answer is refused before anything is written.\n"
    "          2026-10-09 a model is proposed first only when its endpoint or its key was really found; the file order is kept otherwise.\n"
)


def _read_models(path):
    """Return (doc, problem): doc is the decoded models.json, or None with the reason it failed."""
    if not os.path.isfile(path):
        return None, "not found"
    try:
        with open(path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError) as error:
        return None, "cannot be read: " + str(error)
    if not isinstance(doc, dict):
        return None, "cannot be read: document must be an object"
    return doc, ""


def _role_map(doc):
    roles = {}
    entries = doc.get("roles")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                roles[entry["name"]] = entry
    return roles


def _model_ids(doc):
    ids = []
    entries = doc.get("models")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and "id" in entry:
                ids.append(entry["id"])
    return ids


def _layer_delegable(doc):
    delegable = {}
    entries = doc.get("layers")
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                delegable[entry["name"]] = entry.get("delegable")
    return delegable


def _check_answers(doc, answers):
    """Refuse the first bad answer, in order: unknown role, unknown model, kept layer. Return "" when all pass."""
    roles = _role_map(doc)
    known_models = set(_model_ids(doc))
    delegable = _layer_delegable(doc)
    for role_name, model_id in answers:
        role = roles.get(role_name)
        if role is None:
            return "REFUSED unknown role " + role_name
        if model_id not in known_models:
            return "REFUSED unknown model " + model_id
        layer_name = role.get("layer")
        if delegable.get(layer_name) is False:
            return "REFUSED role " + role_name + " is in kept layer " + str(layer_name) + ": it is never delegated"
    return ""


def _finding_for_model(model, findings):
    """Return the first finding, in list order, that matches this model, or None."""
    endpoint = model.get("endpoint")
    key_env = model.get("key_env")
    for finding in findings:
        kind = finding.get("kind")
        where = finding.get("where")
        if not isinstance(where, str):
            continue
        if kind in ("ollama", "lmstudio"):
            if isinstance(endpoint, str):
                base = where[:-1] if where.endswith("/") else where
                if endpoint == base or endpoint.startswith(base + "/"):
                    return finding
        elif kind == "key":
            if isinstance(key_env, str) and key_env != "" and key_env == where:
                return finding
    return None


def _detect_models(doc, findings):
    """Print the DETECTED lines then the PROPOSED line; return the proposed id order."""
    detected_ids = []
    other_ids = []
    for entry in doc.get("models", []):
        if not isinstance(entry, dict) or "id" not in entry:
            continue
        finding = _finding_for_model(entry, findings)
        if finding is None:
            other_ids.append(entry["id"])
        else:
            detected_ids.append(entry["id"])
            print("DETECTED " + str(entry["id"]) + " " + str(finding.get("kind")) + " " + str(finding.get("where")))
    if not detected_ids:
        print("DETECTED none: no model of models.json matches a running engine or a set key")
    print("PROPOSED " + ", ".join(str(model_id) for model_id in detected_ids + other_ids))
    return detected_ids + other_ids


def _walk(doc, answers, proposed_ids):
    """Print one LAYER line per layer and one line per role, applying answers and asking when stdin is a terminal."""
    answer_map = {}
    for role_name, model_id in answers:
        answer_map[role_name] = model_id
    model_ids = _model_ids(doc)
    ids_text = ", ".join(str(model_id) for model_id in proposed_ids)
    role_entries = [entry for entry in doc.get("roles", []) if isinstance(entry, dict)]
    for layer in doc.get("layers", []):
        if not isinstance(layer, dict):
            continue
        layer_name = layer.get("name")
        print("LAYER " + str(layer_name))
        delegable = layer.get("delegable")
        for role in role_entries:
            if role.get("layer") != layer_name:
                continue
            role_name = role.get("name")
            current = role.get("model", "")
            if delegable is False:
                print("  KEPT " + str(role_name) + " judgment stays in session")
            elif role_name in answer_map:
                role["model"] = answer_map[role_name]
                print("  SET " + str(role_name) + " " + str(answer_map[role_name]))
            elif sys.stdin.isatty():
                while True:
                    sys.stdout.write(
                        "  " + str(role_name) + " (" + str(layer_name) + ") who does it? ["
                        + ids_text + "] Enter keeps " + str(current) + ": "
                    )
                    sys.stdout.flush()
                    choice = sys.stdin.readline().strip()
                    if choice == "":
                        break
                    if choice in model_ids:
                        role["model"] = choice
                        print("  SET " + str(role_name) + " " + choice)
                        break
            else:
                print("  KEPT " + str(role_name) + " " + str(current))


def _write_atomic(path, doc):
    """Write the document through a temporary file in the same folder, then replace."""
    folder = os.path.dirname(path)
    handle_fd, temp_path = tempfile.mkstemp(dir=folder, prefix=".setup-", suffix=".json.tmp")
    try:
        with os.fdopen(handle_fd, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        os.replace(temp_path, path)
    except BaseException:
        if os.path.exists(temp_path):
            os.unlink(temp_path)
        raise


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    home = None
    answers = []
    ollama_url = None
    lmstudio_url = None
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            home = argv[i + 1]
            i += 2
        elif arg == "--answer":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            item = argv[i + 1]
            if "=" not in item:
                print(USAGE)
                return 2
            answers.append((item.split("=", 1)[0], item.split("=", 1)[1]))
            i += 2
        elif arg == "--ollama-url":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            ollama_url = argv[i + 1]
            i += 2
        elif arg == "--lmstudio-url":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            lmstudio_url = argv[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2

    ollama_url = ollama_url or env_detect.OLLAMA_URL
    lmstudio_url = lmstudio_url or env_detect.LMSTUDIO_URL
    home = home or os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")
    path = os.path.join(home, "models.json")

    doc, problem = _read_models(path)
    if doc is None:
        if problem == "not found":
            print("REFUSED " + path + " not found: run frugalflow.py init first")
        else:
            print("REFUSED " + path + " " + problem)
        return 1

    refusal = _check_answers(doc, answers)
    if refusal != "":
        print(refusal)
        return 1

    findings = env_detect.detect(ollama_url, lmstudio_url, os.environ)
    proposed_ids = _detect_models(doc, findings)

    original = copy.deepcopy(doc)
    _walk(doc, answers, proposed_ids)

    errors = layers.verify(doc) + config_rules.validate_models(doc)
    if errors:
        for error in errors:
            print("REFUSED " + error)
        return 1

    if doc == original:
        print("UNCHANGED " + path)
        return 0

    _write_atomic(path, doc)
    print("WROTE " + path)
    return 0


def _autotest():
    script = os.path.abspath(__file__)
    example_path = os.path.join(os.path.dirname(BIN), "config", "models.example.json")
    with open(example_path, "r", encoding="utf-8") as handle:
        example_text = handle.read()

    results = []
    tmp = tempfile.mkdtemp(prefix="setup-")
    try:
        def make_home(name, with_file=True):
            home = os.path.join(tmp, name)
            os.makedirs(home, exist_ok=True)
            path = os.path.join(home, "models.json")
            if with_file:
                with open(path, "w", encoding="utf-8") as handle:
                    handle.write(example_text)
            return home, path

        def run(home, *extra, env_extra=None):
            env = dict(os.environ)
            for name in list(env):
                if name.endswith("_API_KEY"):
                    env.pop(name)
            if env_extra:
                env.update(env_extra)
            return subprocess.run(
                [sys.executable, script, "--home", home,
                 "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"] + list(extra),
                capture_output=True, text=True, input="", cwd=tmp, env=env
            )

        def read_text(path):
            with open(path, "r", encoding="utf-8") as handle:
                return handle.read()

        # Proof 1: two answers set both roles, the walk lines match, the file is written and stays valid.
        home, path = make_home("t1")
        proc = run(home, "--answer", "code=remote-coder", "--answer", "documents=session")
        expected_lines = [
            "DETECTED none: no model of models.json matches a running engine or a set key",
            "PROPOSED local-reader, remote-coder, session",
            "LAYER bulk_reading",
            "  SET documents session",
            "LAYER code_writing",
            "  SET code remote-coder",
            "  KEPT code_remote remote-coder",
            "LAYER review",
            "  KEPT review session",
            "LAYER kept_judgment",
            "  KEPT judgment judgment stays in session",
            "WROTE " + path,
        ]
        got_lines = proc.stdout.splitlines()
        ok = proc.returncode == 0 and got_lines == expected_lines
        if ok:
            doc = json.loads(read_text(path))
            models = {}
            for entry in doc["roles"]:
                models[entry["name"]] = entry["model"]
            ok = (models.get("code") == "remote-coder" and models.get("documents") == "session"
                  and layers.verify(doc) == [] and config_rules.validate_models(doc) == [])
        expected = "exit 0, walk lines " + repr(expected_lines) + ", code=remote-coder documents=session, verify and validate empty"
        got = "exit %d lines=%r" % (proc.returncode, got_lines)
        results.append(("1 answers set roles and WROTE a valid file", ok, expected, got))

        # Proof 2: no answer on a non-interactive stdin keeps every role and leaves the file byte for byte.
        home, path = make_home("t2")
        proc = run(home)
        ok = (proc.returncode == 0
              and "DETECTED none: no model of models.json matches a running engine or a set key" in proc.stdout
              and "PROPOSED local-reader, remote-coder, session" in proc.stdout
              and "  KEPT code local-reader" in proc.stdout
              and "UNCHANGED " + path in proc.stdout
              and read_text(path) == example_text)
        expected = "exit 0, 'DETECTED none: no model of models.json matches a running engine or a set key', 'PROPOSED local-reader, remote-coder, session', '  KEPT code local-reader', 'UNCHANGED " + path + "', file byte for byte"
        got = "exit %d none=%s proposed=%s kept=%s unchanged=%s file_same=%s" % (
            proc.returncode,
            "DETECTED none: no model of models.json matches a running engine or a set key" in proc.stdout,
            "PROPOSED local-reader, remote-coder, session" in proc.stdout,
            "  KEPT code local-reader" in proc.stdout,
            "UNCHANGED " + path in proc.stdout,
            read_text(path) == example_text)
        results.append(("2 no answer keeps roles and prints UNCHANGED", ok, expected, got))

        # Proof 3a: a role of a kept layer is refused and the file is not touched.
        home, path = make_home("t3a")
        proc = run(home, "--answer", "judgment=local-reader")
        want = "REFUSED role judgment is in kept layer kept_judgment: it is never delegated"
        ok = proc.returncode == 1 and proc.stdout.strip() == want and read_text(path) == example_text
        results.append(("3a kept layer answer refuses", ok, "exit 1, " + repr(want) + ", file untouched",
                        "exit %d out=%r file_same=%s" % (proc.returncode, proc.stdout.strip(), read_text(path) == example_text)))

        # Proof 3b: an unknown model is refused.
        home, path = make_home("t3b")
        proc = run(home, "--answer", "code=nobody")
        want = "REFUSED unknown model nobody"
        ok = proc.returncode == 1 and proc.stdout.strip() == want and read_text(path) == example_text
        results.append(("3b unknown model refuses", ok, "exit 1, " + repr(want) + ", file untouched",
                        "exit %d out=%r file_same=%s" % (proc.returncode, proc.stdout.strip(), read_text(path) == example_text)))

        # Proof 3c: an unknown role is refused.
        home, path = make_home("t3c")
        proc = run(home, "--answer", "ghost=session")
        want = "REFUSED unknown role ghost"
        ok = proc.returncode == 1 and proc.stdout.strip() == want and read_text(path) == example_text
        results.append(("3c unknown role refuses", ok, "exit 1, " + repr(want) + ", file untouched",
                        "exit %d out=%r file_same=%s" % (proc.returncode, proc.stdout.strip(), read_text(path) == example_text)))

        # Proof 3d: a folder without models.json is refused with the init hint.
        home, path = make_home("t3d", with_file=False)
        proc = run(home)
        want = "REFUSED " + path + " not found: run frugalflow.py init first"
        ok = proc.returncode == 1 and proc.stdout.strip() == want and not os.path.exists(path)
        results.append(("3d missing models.json refuses with the init hint", ok, "exit 1, " + repr(want),
                        "exit %d out=%r" % (proc.returncode, proc.stdout.strip())))

        # Proof 4: an unknown option and an answer without = are usage 2.
        home, path = make_home("t4")
        proc_bad = run(home, "--unknown-option")
        proc_eq = run(home, "--answer", "code")
        ok = (proc_bad.returncode == 2 and "usage: setup_cmd.py" in proc_bad.stdout
              and proc_eq.returncode == 2 and "usage: setup_cmd.py" in proc_eq.stdout)
        results.append(("4 unknown option and answer without = are usage 2", ok,
                        "both exit 2 with the usage line",
                        "bad exit %d eq exit %d" % (proc_bad.returncode, proc_eq.returncode)))

        # Proof 5: --notice prints the five-section notice and exits 0.
        proc = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True, cwd=tmp)
        ok = (proc.returncode == 0 and proc.stdout.startswith("NAME      setup_cmd.py")
              and "PITFALLS  2026-10-09" in proc.stdout
              and "2026-10-09 a model is proposed first only when its endpoint or its key was really found; the file order is kept otherwise." in proc.stdout)
        results.append(("5 --notice prints the notice", ok, "exit 0 starting with NAME      setup_cmd.py",
                        "exit %d first=%r" % (proc.returncode, proc.stdout.splitlines()[0] if proc.stdout else "")))

        # Proof 6: a model whose key_env names a set variable is DETECTED and proposed first.
        home, path = make_home("t6")
        doc = json.loads(read_text(path))
        for entry in doc["models"]:
            if entry.get("id") == "remote-coder":
                entry["key_env"] = "ZZ_API_KEY"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")
        proc = run(home, env_extra={"ZZ_API_KEY": "x"})
        expected_lines = [
            "DETECTED remote-coder key ZZ_API_KEY",
            "PROPOSED remote-coder, local-reader, session",
            "LAYER bulk_reading",
            "  KEPT documents local-reader",
            "LAYER code_writing",
            "  KEPT code local-reader",
            "  KEPT code_remote remote-coder",
            "LAYER review",
            "  KEPT review session",
            "LAYER kept_judgment",
            "  KEPT judgment judgment stays in session",
            "UNCHANGED " + path,
        ]
        got_lines = proc.stdout.splitlines()
        ok = proc.returncode == 0 and got_lines == expected_lines
        expected = "exit 0, lines " + repr(expected_lines)
        results.append(("6 set key_env is DETECTED and proposed first", ok, expected,
                        "exit %d lines=%r" % (proc.returncode, got_lines)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    all_pass = True
    for desc, passed, expected, got in results:
        if passed:
            print("PASS " + desc + " | expected " + expected + " | got " + got)
        else:
            print("FAIL " + desc + " | expected " + expected + " | got " + got)
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "setup_cmd", sys.argv[1:])
