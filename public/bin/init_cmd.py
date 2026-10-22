import os
import sys
import json
import datetime
import subprocess
import tempfile
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claude_block
import settings_merge
import env_detect
import ceilings

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE = (
    "usage: init_cmd.py [--mode observe|active|silent] [--remove] "
    "[--home DIR] [--claude-dir DIR] [--ollama-url URL] [--lmstudio-url URL (any OpenAI-compatible server, with or without /v1)] | --notice | --autotest"
)

NOTICE = (
    "NAME      init_cmd.py - the frugalflow init subcommand: writes the CLAUDE.md block, the settings hook and status line, and the four settings files.\n"
    "READS     CLAUDE.md and settings.json in --claude-dir, else ~/.claude; the four config examples in ../config; the engine endpoints it probes.\n"
    "WRITES    the FrugalFlow block in CLAUDE.md, the guard hook and the FrugalFlow status line in settings.json, and models/preferences/guard/anonymization/model_notes.json in --home; a dated backup of every file it changes.\n"
    "EXAMPLE   python3 init_cmd.py --home ~/.frugalflow --claude-dir ~/.claude\n"
    "PITFALLS  2026-10-03 nothing is written until CLAUDE.md and settings.json are read clean: a broken block or a bad settings file refuses the whole install.\n"
    "          2026-10-04 init wraps the user's status line with --inner and never replaces it; --remove hands it back identical.\n"
    "          2026-10-05 a newcomer gave the server URL with /v1: nothing was found and models.json kept 127.0.0.1; the URL is now normalized and written.\n"
    "          2026-10-10 the refusal hint named bin/delegate.py, a relative path no user folder has; init now writes absolute paths.\n"
    "          2026-10-10 refused orchestrators read our sources to guess the brief rules; the hint now points to frugalflow.py lint.\n"
)

KEY_HELP = {
    "models.json": {
        "schema_version": "format version of this file",
        "models": "every model you can reach: where it runs, its context window, how far it is trusted",
        "layers": "kinds of work; a layer with delegable false is never delegated",
        "roles": "who does each job: a role points to a layer and a model",
    },
    "preferences.json": {
        "schema_version": "format version of this file",
        "verbosity": "word ceilings on the assistant's answers",
        "ceilings": "the most trust, tries and output tokens a delegation may use",
        "splitting": "when a task is too big and must be split",
        "grouping": "send independent tool calls in the same turn",
        "switch": "FrugalFlow on or off, and its mode: observe, active or silent",
    },
    "guard.json": {
        "code_extensions": "files treated as code: writing one needs a delegation receipt",
        "delegation_logs": "logs whose receipts let a code write pass",
        "audit_log": "where each decision of the guard is written",
        "line_threshold": "a code write of this many lines or fewer needs no receipt",
        "receipt_minutes": "how long a delegation receipt stays valid",
        "delegate_tools": "command names that write code legitimately (they leave the receipt)",
        "fix_hint": "appended to a refusal: how to delegate on this machine",
        "checks": "entry checks to run; an unknown name refuses every call",
    },
    "anonymization.json": {
        "anonymizable": "replaced by a stable label __TAG_N__, reversible",
        "irreducible": "never replaced: its presence refuses the file",
    },
    "model_notes.json": {
        "schema_version": "format version of this file",
        "models": "per model and engine: what the vendor prescribes, what was measured and the pitfalls met, each with its proof",
    },
}


def _choose_mode(mode):
    if mode is not None:
        return mode
    if sys.stdin.isatty():
        sys.stdout.write("Choose a mode: 1 observe, 2 active: ")
        sys.stdout.flush()
        line = sys.stdin.readline()
        if line.strip() == "2":
            return "active"
        return "observe"
    print("MODE observe (default; change it with: frugalflow.py mode active)")
    return "observe"


def _backup(path, raw):
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    candidate = path + ".before-frugalflow-" + stamp
    n = 2
    final = candidate
    while os.path.exists(final):
        final = candidate + "-" + str(n)
        n += 1
    with open(final, "w", encoding="utf-8", newline="") as f:
        f.write(raw)


def _read_claude(claude_dir):
    path = os.path.join(claude_dir, "CLAUDE.md")
    if not os.path.exists(path):
        return path, ""
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            return path, f.read()
    except OSError as e:
        raise claude_block.BlockError(str(e))


def _read_settings(claude_dir):
    path = os.path.join(claude_dir, "settings.json")
    if not os.path.exists(path):
        return path, None, {}
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
        doc = json.loads(raw)
    except (OSError, ValueError) as e:
        raise settings_merge.SettingsError(str(e))
    if not isinstance(doc, dict):
        raise settings_merge.SettingsError("settings must be a dict")
    return path, raw, doc


def _normalize_url(url):
    if url is None:
        return url
    if url.endswith("/"):
        url = url[:-1]
    if url.endswith("/v1"):
        url = url[:-3]
    if url.endswith("/"):
        url = url[:-1]
    return url


DEEPSEEK_KEY_ENV = "DEEPSEEK_API_KEY"
DEEPSEEK_ENDPOINT = "https://api.deepseek.com/v1"


def _fetch_local_model(lmstudio_url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(lmstudio_url + "/v1/models", timeout=2) as resp:
            if resp.getcode() != 200:
                return None
            data = json.loads(resp.read())
    except Exception:
        return None
    entries = data.get("data") if isinstance(data, dict) else None
    if not entries:
        return None
    first = entries[0]
    if isinstance(first, dict):
        model_id = first.get("id")
        if model_id:
            return model_id
    return None


def _fetch_ollama_model(ollama_url):
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(ollama_url + "/api/tags", timeout=2) as resp:
            if resp.getcode() != 200:
                return None
            data = json.loads(resp.read())
    except Exception:
        return None
    entries = data.get("models") if isinstance(data, dict) else None
    if not entries:
        return None
    first = entries[0]
    if isinstance(first, dict):
        model_name = first.get("name")
        if model_name:
            return model_name
    return None


def _init(mode, home, claude_dir, ollama_url, lmstudio_url):
    ollama_url = _normalize_url(ollama_url)
    lmstudio_url = _normalize_url(lmstudio_url)
    mode = _choose_mode(mode)

    # Step 1: read CLAUDE.md and compute the inserted block.
    try:
        claude_path, claude_raw = _read_claude(claude_dir)
        new_claude = claude_block.insert_block(claude_raw, claude_block.block_body(BIN))
    except claude_block.BlockError as e:
        print("REFUSED: " + os.path.join(claude_dir, "CLAUDE.md") + " has a broken FrugalFlow block (" + str(e) + "). Nothing was written.")
        return 5

    # Step 2: read settings.json and compute the added hook and status line.
    try:
        settings_path, settings_raw, settings_doc = _read_settings(claude_dir)
        new_settings, hook_changed = settings_merge.add_hooks(
            settings_doc, settings_merge.guard_command(sys.executable, BIN)
        )
        new_settings, sl_changed = settings_merge.add_statusline(new_settings, sys.executable, BIN)
        settings_changed = hook_changed or sl_changed
    except settings_merge.SettingsError as e:
        print("REFUSED: " + os.path.join(claude_dir, "settings.json") + " cannot be read as settings (" + str(e) + "). Nothing was written.")
        return 6

    # Step 3: detection.
    findings = env_detect.detect(ollama_url, lmstudio_url, os.environ)
    for line in env_detect.describe(findings):
        print(line)
    lmstudio_found = any(f["kind"] == "lmstudio" for f in findings)
    ollama_found = any(f["kind"] == "ollama" for f in findings)
    deepseek_found = any(f["kind"] == "key" and f["where"] == DEEPSEEK_KEY_ENV for f in findings)

    # Step 4: the five settings files in --home.
    config_dir = os.path.join(os.path.dirname(BIN), "config")
    for name in ("models", "preferences", "guard", "anonymization", "model_notes"):
        dest = os.path.join(home, name + ".json")
        if os.path.exists(dest):
            print("KEPT " + dest)
            continue
        example_path = os.path.join(config_dir, name + ".example.json")
        with open(example_path, "r", encoding="utf-8", newline="") as f:
            example_text = f.read()
        doc = json.loads(example_text)
        os.makedirs(home, exist_ok=True)
        if name == "models":
            if lmstudio_found:
                endpoint = lmstudio_url + "/v1"
                model_id = _fetch_local_model(lmstudio_url)
            elif ollama_found:
                endpoint = ollama_url + "/v1"
                model_id = _fetch_ollama_model(ollama_url)
            else:
                endpoint = None
                model_id = None
            lr_name = None
            for m in doc["models"]:
                if m.get("id") == "local-reader" and endpoint is not None:
                    m["endpoint"] = endpoint
                    if model_id is not None:
                        m["name"] = model_id
                    lr_name = m.get("name")
                elif m.get("id") == "remote-coder" and deepseek_found:
                    m["key_env"] = DEEPSEEK_KEY_ENV
                    m["endpoint"] = DEEPSEEK_ENDPOINT
            if endpoint is None and not deepseek_found:
                text = example_text
            else:
                text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
            with open(dest, "w", encoding="utf-8", newline="") as f:
                f.write(text)
            print("WROTE " + dest)
            if endpoint is not None:
                print("SET local-reader endpoint " + endpoint + " model " + lr_name)
            else:
                print("UNSET local-reader: no local engine answered, edit " + dest)
            if deepseek_found:
                print("SET remote-coder key " + DEEPSEEK_KEY_ENV + " endpoint " + DEEPSEEK_ENDPOINT)
            for key in doc:
                print("  " + key + ": " + KEY_HELP[name + ".json"][key])
            continue
        if name == "preferences":
            doc["switch"] = {"enabled": True, "mode": mode}
            text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        elif name == "guard":
            examples_dir = os.path.join(os.path.dirname(BIN), "examples")
            doc["fix_hint"] = (
                "Delegate it: copy " + examples_dir + "/brief_template.md to a task file, "
                "describe the code there, then run: python3 " + BIN + "/delegate.py --role code "
                "--file <task file> --out <file>. The delegation leaves the receipt that lets the write pass."
                " Check the task file first: python3 " + BIN + "/frugalflow.py lint <task file>; "
                "each refusal names the line to add. Never read FrugalFlow source code."
            )
            text = json.dumps(doc, indent=2, ensure_ascii=False) + "\n"
        else:
            text = example_text
        with open(dest, "w", encoding="utf-8", newline="") as f:
            f.write(text)
        print("WROTE " + dest)
        for key in doc:
            print("  " + key + ": " + KEY_HELP[name + ".json"][key])

    # Step 5: write the CLAUDE.md block.
    if new_claude == claude_raw:
        print("BLOCK " + claude_path + " (already in place)")
    else:
        if os.path.exists(claude_path):
            _backup(claude_path, claude_raw)
        os.makedirs(claude_dir, exist_ok=True)
        with open(claude_path, "w", encoding="utf-8", newline="") as f:
            f.write(new_claude)
        print("BLOCK " + claude_path)

    # Step 6: write the settings hook and status line.
    if not settings_changed:
        print("HOOKS " + settings_path + " (already in place)")
    else:
        if os.path.exists(settings_path):
            _backup(settings_path, settings_raw)
        os.makedirs(claude_dir, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(new_settings, indent=2, ensure_ascii=False) + "\n")
        print("HOOKS " + settings_path)

    print("READY. Check it any time: python3 " + os.path.join(BIN, "frugalflow.py") + " doctor")
    return 0


def _remove(home, claude_dir):
    try:
        claude_path, claude_raw = _read_claude(claude_dir)
        new_claude, claude_changed = claude_block.remove_block(claude_raw)
    except claude_block.BlockError as e:
        print("REFUSED: " + os.path.join(claude_dir, "CLAUDE.md") + " has a broken FrugalFlow block (" + str(e) + "). Nothing was written.")
        return 5

    try:
        settings_path, settings_raw, settings_doc = _read_settings(claude_dir)
        new_settings, settings_changed = settings_merge.remove_hooks(
            settings_doc, os.path.join(BIN, "guard_hook.py")
        )
        new_settings, sl_changed = settings_merge.remove_statusline(new_settings, BIN)
        settings_changed = settings_changed or sl_changed
    except settings_merge.SettingsError as e:
        print("REFUSED: " + os.path.join(claude_dir, "settings.json") + " cannot be read as settings (" + str(e) + "). Nothing was written.")
        return 6

    if not claude_changed and not settings_changed:
        print("NOTHING TO REMOVE")
        return 0

    if claude_changed:
        if os.path.exists(claude_path):
            _backup(claude_path, claude_raw)
        with open(claude_path, "w", encoding="utf-8", newline="") as f:
            f.write(new_claude)
        print("REMOVED " + claude_path)

    if settings_changed:
        if os.path.exists(settings_path):
            _backup(settings_path, settings_raw)
        os.makedirs(claude_dir, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8", newline="") as f:
            f.write(json.dumps(new_settings, indent=2, ensure_ascii=False) + "\n")
        print("REMOVED " + settings_path)

    print("KEPT " + home + " (your settings; delete it by hand if you want)")
    return 0


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    mode = None
    remove = False
    home = None
    claude_dir = None
    ollama_url = None
    lmstudio_url = None

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--mode":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            mode = argv[i + 1]
            i += 2
        elif a == "--remove":
            remove = True
            i += 1
        elif a == "--home":
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

    if mode is not None and mode not in ceilings.MODES:
        print(USAGE)
        return 2

    home = home or os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")
    claude_dir = claude_dir or os.path.expanduser("~/.claude")
    ollama_url = ollama_url or env_detect.OLLAMA_URL
    lmstudio_url = lmstudio_url or env_detect.LMSTUDIO_URL

    if remove:
        return _remove(home, claude_dir)
    return _init(mode, home, claude_dir, ollama_url, lmstudio_url)


def _autotest():
    script = os.path.abspath(__file__)
    config_dir = os.path.join(os.path.dirname(BIN), "config")
    results = []

    def run(tmp, home, claude, *extra):
        env = dict(os.environ)
        env["HOME"] = tmp
        cmd = [sys.executable, script, "--home", home, "--claude-dir", claude,
               "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"]
        cmd.extend(extra)
        return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp)

    # Test 1: KEY_HELP covers every first-level key of the four examples, plus switch.
    ok = True
    detail = ""
    mapping = {
        "models.example.json": "models.json",
        "preferences.example.json": "preferences.json",
        "guard.example.json": "guard.json",
        "anonymization.example.json": "anonymization.json",
    }
    for example, name in mapping.items():
        try:
            doc = json.load(open(os.path.join(config_dir, example), encoding="utf-8"))
        except (OSError, ValueError) as e:
            ok = False
            detail = "cannot read " + example + ": " + str(e)
            break
        for key in doc:
            if key not in KEY_HELP.get(name, {}):
                ok = False
                detail = example + " key " + key + " is missing from KEY_HELP"
                break
        if not ok:
            break
    if ok and "switch" not in KEY_HELP.get("preferences.json", {}):
        ok = False
        detail = "preferences.json switch key is missing from KEY_HELP"
    results.append(("1 KEY_HELP covers every example key plus switch", ok, detail))

    # Test 2: init twice leaves one block, one hook, four files; default mode observe.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r1 = run(tmp, home, claude)
        r2 = run(tmp, home, claude)
        claude_md = os.path.join(claude, "CLAUDE.md")
        settings_file = os.path.join(claude, "settings.json")
        prefs_file = os.path.join(home, "preferences.json")
        ok = (r1.returncode == 0 and r2.returncode == 0
              and "MODE observe (default" in r1.stdout
              and "READY." in r1.stdout)
        got = "r1=%d r2=%d" % (r1.returncode, r2.returncode)
        if ok:
            with open(claude_md, encoding="utf-8", newline="") as f:
                text = f.read()
            with open(settings_file, encoding="utf-8") as f:
                raw_settings = f.read()
            ok = (text.count(claude_block.BEGIN) == 1
                  and text.count(claude_block.END) == 1
                  and raw_settings.count("guard_hook.py") == 1
                  and raw_settings.count("statusline.py") == 1)
            got = "begin=%d end=%d hook=%d statusline=%d" % (
                text.count(claude_block.BEGIN), text.count(claude_block.END),
                raw_settings.count("guard_hook.py"), raw_settings.count("statusline.py"))
        if ok:
            for name in ("models", "preferences", "guard", "anonymization"):
                if not os.path.isfile(os.path.join(home, name + ".json")):
                    ok = False
                    got = "missing " + name + ".json"
                    break
        if ok:
            prefs = json.load(open(prefs_file, encoding="utf-8"))
            ok = prefs.get("switch") == {"enabled": True, "mode": "observe"}
            got = "switch=" + json.dumps(prefs.get("switch"))
        results.append(("2 init twice leaves one block, one hook and the four files", ok, got))

    # Test 3: a filled CLAUDE.md keeps its head byte for byte, and --remove restores it.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        os.makedirs(claude, exist_ok=True)
        original = "alpha\nbeta\n"
        claude_md = os.path.join(claude, "CLAUDE.md")
        with open(claude_md, "w", encoding="utf-8", newline="") as f:
            f.write(original)
        r1 = run(tmp, home, claude)
        with open(claude_md, encoding="utf-8", newline="") as f:
            after_init = f.read()
        ok = r1.returncode == 0 and after_init.startswith(original)
        got = "rc=%d head_kept=%s" % (r1.returncode, after_init.startswith(original))
        if ok:
            r2 = run(tmp, home, claude, "--remove")
            with open(claude_md, encoding="utf-8", newline="") as f:
                after_remove = f.read()
            settings_file = os.path.join(claude, "settings.json")
            with open(settings_file, encoding="utf-8") as f:
                after_settings = f.read()
            ok = (r2.returncode == 0 and after_remove == original
                  and '"statusLine"' not in after_settings and '"hooks"' not in after_settings)
            got = "rc=%d restored=%s" % (r2.returncode, after_remove == original)
        results.append(("3 head kept byte for byte and --remove restores it (hook and status line gone)", ok, got))

    # Test 4: refusals leave nothing written (broken block -> 5, bad settings -> 6).
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        os.makedirs(claude, exist_ok=True)
        broken = claude_block.BEGIN + "\nbody\n" + claude_block.END + "\n" + claude_block.BEGIN + "\n"
        claude_md = os.path.join(claude, "CLAUDE.md")
        with open(claude_md, "w", encoding="utf-8", newline="") as f:
            f.write(broken)
        r = run(tmp, home, claude)
        ok = (r.returncode == 5
              and "has a broken FrugalFlow block" in r.stdout
              and "Nothing was written" in r.stdout
              and not os.path.exists(home))
        got = "rc=%d home_created=%s" % (r.returncode, os.path.exists(home))
        if ok:
            with open(claude_md, encoding="utf-8", newline="") as f:
                ok = f.read() == broken
            got = "rc=%d claude_unchanged=%s" % (r.returncode, ok)
        results.append(("4a broken block refuses with 5 and writes nothing", ok, got))

    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        os.makedirs(claude, exist_ok=True)
        settings_file = os.path.join(claude, "settings.json")
        with open(settings_file, "w", encoding="utf-8") as f:
            f.write("{not json")
        r = run(tmp, home, claude)
        ok = (r.returncode == 6
              and "cannot be read as settings" in r.stdout
              and "Nothing was written" in r.stdout
              and not os.path.exists(home)
              and not os.path.exists(os.path.join(claude, "CLAUDE.md")))
        got = "rc=%d" % r.returncode
        results.append(("4b bad settings refuses with 6 and writes nothing", ok, got))

    # Test 5: bad --mode is usage 2; --notice prints the notice.
    with tempfile.TemporaryDirectory() as tmp:
        r = run(tmp, os.path.join(tmp, "h"), os.path.join(tmp, "c"), "--mode", "bogus")
        rn = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True, env={"HOME": tmp})
        ok = (r.returncode == 2
              and rn.returncode == 0
              and rn.stdout.startswith("NAME      init_cmd.py"))
        got = "mode_rc=%d notice_rc=%d" % (r.returncode, rn.returncode)
        results.append(("5 bad mode is 2 and --notice prints the notice", ok, got))

    # Test 6: an existing settings file is kept byte for byte.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        marker = '{"marker": "mine"}\n'
        models_file = os.path.join(home, "models.json")
        with open(models_file, "w", encoding="utf-8") as f:
            f.write(marker)
        r = run(tmp, home, claude)
        with open(models_file, encoding="utf-8") as f:
            kept = f.read()
        ok = (r.returncode == 0
              and "KEPT " + models_file in r.stdout
              and kept == marker)
        got = "rc=%d kept=%s" % (r.returncode, kept == marker)
        results.append(("6 an existing settings file is KEPT untouched", ok, got))

    # Test 7: a --lmstudio-url ending in /v1/ is probed without /v1 and written to models.json.
    import http.server
    import threading

    class _ModelsHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/v1/models":
                self._reply(200, b'{"object": "list", "data": [{"id": "m-test", "object": "model"}]}')
            else:
                self._reply(404, b"missing")

        def _reply(self, code, body):
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _ModelsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            claude = os.path.join(tmp, "claude")
            env = dict(os.environ)
            env["HOME"] = tmp
            cmd = [sys.executable, script, "--home", home, "--claude-dir", claude,
                   "--ollama-url", "http://127.0.0.1:1",
                   "--lmstudio-url", "http://127.0.0.1:%d/v1/" % port]
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp)
            setline = "SET local-reader endpoint http://127.0.0.1:%d/v1 model m-test" % port
            ok = False
            got = "rc=%d set=%s" % (r.returncode, setline in r.stdout)
            if r.returncode == 0 and setline in r.stdout:
                try:
                    doc = json.load(open(os.path.join(home, "models.json"), encoding="utf-8"))
                    lr = [m for m in doc["models"] if m.get("id") == "local-reader"]
                    ok = (len(lr) == 1
                          and lr[0]["endpoint"] == "http://127.0.0.1:%d/v1" % port
                          and lr[0]["name"] == "m-test")
                    got = "rc=0 endpoint=%s name=%s" % (
                        lr[0]["endpoint"] if lr else "?", lr[0]["name"] if lr else "?")
                except (OSError, ValueError, KeyError) as e:
                    ok = False
                    got = "rc=%d models_unreadable=%s" % (r.returncode, str(e))
            results.append(("7 a --lmstudio-url ending in /v1/ is probed without /v1 and written", ok, got))
    finally:
        server.shutdown()

    # Test 8: only Ollama answers: its /api/tags name and endpoint are written to models.json.
    class _TagsHandler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/api/tags":
                self._reply(200, b'{"models": [{"name": "o-test", "model": "o-test"}]}')
            else:
                self._reply(404, b"missing")

        def _reply(self, code, body):
            try:
                self.send_response(code)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
            except (BrokenPipeError, ConnectionResetError):
                pass

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), _TagsHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    port = server.server_address[1]
    try:
        with tempfile.TemporaryDirectory() as tmp:
            home = os.path.join(tmp, "home")
            claude = os.path.join(tmp, "claude")
            env = dict(os.environ)
            env["HOME"] = tmp
            for name in list(env):
                if name.endswith("_API_KEY"):
                    env.pop(name)
            cmd = [sys.executable, script, "--home", home, "--claude-dir", claude,
                   "--ollama-url", "http://127.0.0.1:%d" % port,
                   "--lmstudio-url", "http://127.0.0.1:1"]
            r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp)
            setline = "SET local-reader endpoint http://127.0.0.1:%d/v1 model o-test" % port
            ok = False
            got = "rc=%d set=%s" % (r.returncode, setline in r.stdout)
            if r.returncode == 0 and setline in r.stdout:
                try:
                    doc = json.load(open(os.path.join(home, "models.json"), encoding="utf-8"))
                    lr = [m for m in doc["models"] if m.get("id") == "local-reader"]
                    ok = (len(lr) == 1
                          and lr[0]["endpoint"] == "http://127.0.0.1:%d/v1" % port
                          and lr[0]["name"] == "o-test")
                    got = "rc=0 endpoint=%s name=%s" % (
                        lr[0]["endpoint"] if lr else "?", lr[0]["name"] if lr else "?")
                except (OSError, ValueError, KeyError) as e:
                    ok = False
                    got = "rc=%d models_unreadable=%s" % (r.returncode, str(e))
            results.append(("8 only Ollama answers: its endpoint and model name are written", ok, got))
    finally:
        server.shutdown()

    # Test 9: no engine answers but DEEPSEEK_API_KEY is set: UNSET line and remote-coder wired to DeepSeek.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = dict(os.environ)
        env["HOME"] = tmp
        for name in list(env):
            if name.endswith("_API_KEY"):
                env.pop(name)
        env["DEEPSEEK_API_KEY"] = "sk-test"
        cmd = [sys.executable, script, "--home", home, "--claude-dir", claude,
               "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"]
        r = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp)
        models_file = os.path.join(home, "models.json")
        unsetline = "UNSET local-reader: no local engine answered, edit " + models_file
        setline = "SET remote-coder key DEEPSEEK_API_KEY endpoint https://api.deepseek.com/v1"
        ok = False
        got = "rc=%d unset=%s set=%s" % (
            r.returncode, unsetline in r.stdout, setline in r.stdout)
        if r.returncode == 0 and unsetline in r.stdout and setline in r.stdout:
            try:
                doc = json.load(open(models_file, encoding="utf-8"))
                lr = [m for m in doc["models"] if m.get("id") == "local-reader"]
                rc_ = [m for m in doc["models"] if m.get("id") == "remote-coder"]
                ok = (len(lr) == 1 and len(rc_) == 1
                      and lr[0]["endpoint"] == "http://127.0.0.1:8000/v1"
                      and rc_[0]["key_env"] == "DEEPSEEK_API_KEY"
                      and rc_[0]["endpoint"] == "https://api.deepseek.com/v1")
                got = "rc=0 lr_endpoint=%s rc_key_env=%s rc_endpoint=%s" % (
                    lr[0]["endpoint"] if lr else "?",
                    rc_[0]["key_env"] if rc_ else "?",
                    rc_[0]["endpoint"] if rc_ else "?")
            except (OSError, ValueError, KeyError) as e:
                ok = False
                got = "rc=%d models_unreadable=%s" % (r.returncode, str(e))
        results.append(("9 no engine but DEEPSEEK_API_KEY: UNSET line and remote-coder wired", ok, got))

    # Test 10: init writes model_notes.json identical to the example and prints its models help line.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r = run(tmp, home, claude)
        notes_file = os.path.join(home, "model_notes.json")
        help_line = "  models: per model and engine: what the vendor prescribes, what was measured and the pitfalls met, each with its proof"
        ok = False
        got = "rc=%d wrote=%s" % (r.returncode, ("WROTE " + notes_file) in r.stdout)
        if r.returncode == 0 and ("WROTE " + notes_file) in r.stdout and help_line in r.stdout:
            try:
                with open(notes_file, "r", encoding="utf-8", newline="") as f:
                    written = f.read()
                with open(os.path.join(config_dir, "model_notes.example.json"), "r", encoding="utf-8", newline="") as f:
                    example = f.read()
                ok = written == example
                got = "rc=0 identical_to_example=%s" % ok
            except OSError as e:
                got = "rc=%d notes_unreadable=%s" % (r.returncode, str(e))
        results.append(("10 init writes model_notes.json identical to the example and prints the models help line", ok, got))

    # Test 11: the written guard.json fix_hint names an absolute existing delegate.py, and CLAUDE.md carries the anti-shrink line.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        r = run(tmp, home, claude)
        guard_file = os.path.join(home, "guard.json")
        claude_md = os.path.join(claude, "CLAUDE.md")
        ok = False
        got = "rc=%d" % r.returncode
        if r.returncode == 0:
            try:
                doc = json.load(open(guard_file, encoding="utf-8"))
                with open(claude_md, encoding="utf-8") as f:
                    text = f.read()
            except (OSError, ValueError) as e:
                got = "rc=0 unreadable=%s" % e
            else:
                hint = doc.get("fix_hint", "")
                marker = "/delegate.py --role code"
                pos = hint.find(marker)
                bin_path = hint[:pos].split()[-1] if pos > 0 else ""
                absolute = pos > 0 and os.path.isabs(bin_path) and os.path.exists(bin_path + "/delegate.py")
                expected_tail = (" Check the task file first: python3 " + BIN
                                 + "/frugalflow.py lint <task file>; each refusal names the line to add."
                                 " Never read FrugalFlow source code.")
                tail_ok = hint.endswith(expected_tail)
                block_line = "- Never shrink or split a file to slip under the guard threshold: that is working around it."
                lint_line = ("- Check a task file before delegating: python3 " + BIN
                             + "/frugalflow.py lint <task file>. Every refusal names its fix:"
                             " never read FrugalFlow source code.")
                check_line = "- Check its state: "
                ordered = (check_line in text and block_line in text
                           and text.find(check_line) < text.find(block_line)
                           and text.find(block_line + "\n" + lint_line) != -1)
                ok = absolute and tail_ok and ordered and lint_line in text
                got = ("rc=0 absolute=%s hint_tail_ok=%s lint_line_in_claude=%s block_line_then_lint_line=%s"
                       % (absolute, tail_ok, lint_line in text, ordered))
        results.append(("11 guard.json fix_hint points to an absolute existing delegate.py, ends with the frugalflow.py lint tail, and CLAUDE.md has the anti-shrink line after the check line followed by the lint line", ok, got))

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
    exit_log.run(main, "init_cmd", sys.argv[1:])
