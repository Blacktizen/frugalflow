import sys
import os
import json
import time
import shutil
import tempfile
import subprocess
import urllib.request
import urllib.error
import http.server
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env_detect
import init_cmd
import doctor_cmd
import config_rules
import setup_manifest
import onboard_choice

NOTICE = (
    "NAME      onboard_cmd.py - the guided frugalflow setup: detects your engines, asks which one to use, backs up, writes the settings, runs doctor.\n"
    "READS     the local engines (Ollama, LM Studio, a typed OpenAI-compatible endpoint), the names of the *_API_KEY environment variables, the existing settings and CLAUDE.md.\n"
    "WRITES    the five settings files in --home, the FrugalFlow block in CLAUDE.md and the hook in settings.json; first a copy of each existing file in home/setup-backups and a manifest that uninstall reads.\n"
    "EXAMPLE   python3 onboard_cmd.py --yes\n"
    "PITFALLS  2026-10-25 a second setup saved the configured files over the originals; the manifest now keeps the first backup of each file.\n"
    "          2026-10-25 an engine named with --engine that did not answer used to fall back to another one silently; it is now refused with code 4 and nothing is written."
)

USAGE = (
    "usage: onboard_cmd.py [--yes] [--interactive] [--home DIR] [--claude-dir DIR]"
    " [--engine ollama|lmstudio|openai|key|none] [--endpoint URL] [--model NAME]"
    " [--key-env VAR] [--mode observe|active|silent] [--ollama-url URL] [--lmstudio-url URL]"
    " [--no-doctor] | --notice | --autotest"
)

DEAD = "http://127.0.0.1:1"


class FakeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            raw = json.dumps({"data": [{"id": "fake-model-1"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def start_fake():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:" + str(server.server_address[1])


def _parse(argv):
    flags = {"--yes", "--interactive", "--no-doctor"}
    valued = {"--home", "--claude-dir", "--ollama-url", "--lmstudio-url",
              "--engine", "--endpoint", "--model", "--key-env", "--mode"}
    valid_engines = {"ollama", "lmstudio", "openai", "key", "none"}
    valid_modes = {"observe", "active", "silent"}

    if argv == ["--notice"]:
        return ("notice",)
    if argv == ["--autotest"]:
        return ("autotest",)

    opts = {}
    opts["yes"] = False
    opts["interactive"] = False
    opts["no_doctor"] = False
    opts["home"] = None
    opts["claude_dir"] = None
    opts["ollama_url"] = None
    opts["lmstudio_url"] = None
    opts["engine"] = None
    opts["endpoint"] = None
    opts["model"] = None
    opts["key_env"] = None
    opts["mode"] = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg in flags:
            if arg == "--yes":
                opts["yes"] = True
            elif arg == "--interactive":
                opts["interactive"] = True
            elif arg == "--no-doctor":
                opts["no_doctor"] = True
            i += 1
        elif arg in valued:
            if i + 1 >= len(argv):
                return None
            val = argv[i + 1]
            i += 2
            if arg == "--engine":
                if val not in valid_engines:
                    return None
                opts["engine"] = val
            elif arg == "--mode":
                if val not in valid_modes:
                    return None
                opts["mode"] = val
            elif arg == "--home":
                opts["home"] = val
            elif arg == "--claude-dir":
                opts["claude_dir"] = val
            elif arg == "--ollama-url":
                opts["ollama_url"] = val
            elif arg == "--lmstudio-url":
                opts["lmstudio_url"] = val
            elif arg == "--endpoint":
                opts["endpoint"] = val
            elif arg == "--model":
                opts["model"] = val
            elif arg == "--key-env":
                opts["key_env"] = val
        elif arg == "--notice" or arg == "--autotest":
            return None
        else:
            return None

    return opts


def main(argv):
    parsed = _parse(argv)

    if parsed is None:
        print(USAGE)
        return 2

    if isinstance(parsed, tuple) and parsed[0] == "notice":
        print(NOTICE)
        return 0

    if isinstance(parsed, tuple) and parsed[0] == "autotest":
        return _autotest()

    opts = parsed

    home = opts["home"]
    if home is None:
        fh = os.environ.get("FRUGALFLOW_HOME", "")
        home = fh if fh else os.path.expanduser("~/.frugalflow")

    claude_dir = opts["claude_dir"]
    if claude_dir is None:
        claude_dir = os.path.expanduser("~/.claude")

    ollama_url = opts["ollama_url"]
    if ollama_url is None:
        ollama_url = env_detect.OLLAMA_URL
    ollama_url = init_cmd._normalize_url(ollama_url)

    lmstudio_url = opts["lmstudio_url"]
    if lmstudio_url is None:
        lmstudio_url = env_detect.LMSTUDIO_URL
    lmstudio_url = init_cmd._normalize_url(lmstudio_url)

    mode = opts["mode"]
    if mode is None:
        mode = "observe"

    key_env_val = opts["key_env"] if opts["key_env"] is not None else ""

    # --- Step 1: Detection ---
    findings = env_detect.detect(ollama_url, lmstudio_url, os.environ)
    for line in env_detect.describe(findings):
        print(line)

    endpoint_url = ""
    if opts["endpoint"] is not None:
        ep = onboard_choice.normalize_endpoint(opts["endpoint"])
        if env_detect.probe(ep, "/models"):
            endpoint_url = ep
            print("FOUND openai " + ep)
        else:
            endpoint_url = ""
            print("NOT ANSWERING " + ep)

    cands = onboard_choice.build_candidates(findings, endpoint_url, key_env_val)

    # --- Step 2: Choice ---
    cand = None

    if opts["engine"] is not None:
        ok, cand = onboard_choice.select(cands, opts["engine"])
        if not ok:
            print("REFUSED engine " + opts["engine"] + " not found")
            return 4
    elif (opts["interactive"]
          or (not opts["yes"] and sys.stdin.isatty()
              and len(cands) > 0)):
        for line in onboard_choice.menu_lines(cands):
            print(line)
        n = len(cands)
        answered = False
        for _attempt in range(3):
            try:
                text = input("Choose [1]: ")
            except EOFError:
                text = ""
            r = onboard_choice.parse_answer(text, n)
            if r is None:
                print("Not a valid choice.")
                continue
            if r == 0:
                cand = None
            else:
                cand = cands[r - 1]
            answered = True
            break
        if not answered:
            print("REFUSED no valid choice")
            return 4
    else:
        ok, cand = onboard_choice.select(cands, "")

    if cand is not None:
        print("CHOSEN " + cand["label"])
    else:
        print("CHOSEN none")

    # --- Step 3: Build choice dict ---
    kind = cand["kind"] if cand is not None else "none"
    model_name = opts["model"] if opts["model"] is not None else None
    key_env = ""
    endpoint = ""

    if kind == "lmstudio":
        endpoint = lmstudio_url + "/v1"
        if model_name is not None:
            model_name = model_name
        else:
            model_name = init_cmd._fetch_local_model(lmstudio_url) or ""
    elif kind == "ollama":
        endpoint = ollama_url + "/v1"
        if model_name is not None:
            model_name = model_name
        else:
            model_name = init_cmd._fetch_ollama_model(ollama_url) or ""
    elif kind == "openai":
        endpoint = cand["where"]
        if model_name is not None:
            model_name = model_name
        else:
            model_name = _fetch_openai_model(endpoint)
        key_env = opts["key_env"] if opts["key_env"] is not None else ""
    elif kind == "key":
        key_env = cand["where"]
        endpoint = ""
        model_name = model_name if model_name is not None else ""
    else:
        endpoint = ""
        model_name = ""

    choice = {"kind": kind, "endpoint": endpoint, "model": model_name, "key_env": key_env}

    # --- Step 4: Save (manifest snapshot) ---
    paths = [
        os.path.abspath(os.path.join(claude_dir, "CLAUDE.md")),
        os.path.abspath(os.path.join(claude_dir, "settings.json")),
        os.path.abspath(os.path.join(home, "models.json")),
        os.path.abspath(os.path.join(home, "preferences.json")),
        os.path.abspath(os.path.join(home, "guard.json")),
        os.path.abspath(os.path.join(home, "anonymization.json")),
        os.path.abspath(os.path.join(home, "model_notes.json")),
    ]
    manifest = setup_manifest.snapshot(home, paths)

    # --- Step 5: Init ---
    if kind == "ollama":
        ollama_for_init = ollama_url
    else:
        ollama_for_init = DEAD

    if kind == "lmstudio":
        lmstudio_for_init = lmstudio_url
    else:
        lmstudio_for_init = DEAD

    rc = init_cmd.main([
        "--home", home,
        "--claude-dir", claude_dir,
        "--ollama-url", ollama_for_init,
        "--lmstudio-url", lmstudio_for_init,
        "--mode", mode,
    ])
    if rc != 0:
        setup_manifest.finish(home, manifest)
        print("SETUP FAILED: init returned " + str(rc))
        return rc

    # --- Step 6: Model tuning ---
    if kind != "none":
        models_path = os.path.join(home, "models.json")
        with open(models_path, encoding="utf-8") as f:
            doc = json.load(f)
        doc2 = onboard_choice.apply_choice(doc, choice)
        errors = config_rules.validate_models(doc2)
        if errors:
            setup_manifest.finish(home, manifest)
            for e in errors:
                print("REFUSED " + e)
            return 1
        if doc2 != doc:
            tmp_path = models_path + ".tmp"
            with open(tmp_path, "w", encoding="utf-8") as f:
                f.write(json.dumps(doc2, indent=2, ensure_ascii=False) + "\n")
            os.replace(tmp_path, models_path)
            label = cand["label"] if cand is not None else "none"
            print("SET models.json " + label)

    # --- Step 7: Manifest finish ---
    setup_manifest.finish(home, manifest)

    # --- Step 8: Doctor ---
    if opts["no_doctor"]:
        rc_doctor = 0
    else:
        rc_doctor = doctor_cmd.main([
            "--home", home,
            "--claude-dir", claude_dir,
            "--ollama-url", ollama_for_init,
            "--lmstudio-url", lmstudio_for_init,
        ])

    # --- Step 9: Done ---
    print("SETUP DONE. Next: frugalflow scan .   To undo: frugalflow uninstall")
    return rc_doctor


def _fetch_openai_model(endpoint):
    try:
        opener = urllib.request.build_opener(
            urllib.request.ProxyHandler({})
        )
        req = urllib.request.Request(endpoint + "/models")
        resp = opener.open(req, timeout=3)
        data = json.loads(resp.read().decode("utf-8"))
        return data["data"][0]["id"]
    except Exception:
        return ""


# ---------------------------------------------------------------------------
# Autotest
# ---------------------------------------------------------------------------

def _autotest():
    script = os.path.abspath(__file__)
    passes = 0
    results = []

    # --- Test 1: bad argument -> code 2, usage in output ---
    tmp = tempfile.mkdtemp()
    try:
        env = _clean_env(tmp)
        proc = subprocess.run(
            [sys.executable, script, "--bogus"],
            capture_output=True, text=True, timeout=300,
            env=env, cwd=tmp,
        )
        ok = proc.returncode == 2 and "usage: onboard_cmd.py" in proc.stdout
        if ok:
            passes += 1
            results.append("PASS test1: expected code 2 and usage, got code " + str(proc.returncode))
        else:
            results.append("FAIL test1: expected code 2 and usage, got code " + str(proc.returncode))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 2: engine not found -> code 4, no models.json ---
    tmp = tempfile.mkdtemp()
    try:
        env = _clean_env(tmp)
        proc = subprocess.run(
            [sys.executable, script, "--yes", "--engine", "ollama",
             "--home", "ff", "--claude-dir", "cl",
             "--ollama-url", DEAD, "--lmstudio-url", DEAD],
            capture_output=True, text=True, timeout=300,
            env=env, cwd=tmp,
        )
        no_models = not os.path.exists(os.path.join(tmp, "ff", "models.json"))
        ok = proc.returncode == 4 and "REFUSED engine ollama not found" in proc.stdout and no_models
        if ok:
            passes += 1
            results.append("PASS test2: expected code 4 and refusal, got code " + str(proc.returncode))
        else:
            results.append("FAIL test2: expected code 4 and refusal, got code " + str(proc.returncode))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 3: nothing detected -> code 0, FOUND nothing, CHOSEN none, SETUP DONE ---
    tmp = tempfile.mkdtemp()
    try:
        env = _clean_env(tmp)
        proc = subprocess.run(
            [sys.executable, script, "--yes", "--no-doctor",
             "--home", "ff", "--claude-dir", "cl",
             "--ollama-url", DEAD, "--lmstudio-url", DEAD],
            capture_output=True, text=True, timeout=300,
            env=env, cwd=tmp,
        )
        models_exist = os.path.exists(os.path.join(tmp, "ff", "models.json"))
        ok = (proc.returncode == 0
              and "FOUND nothing" in proc.stdout
              and "CHOSEN none" in proc.stdout
              and "SETUP DONE" in proc.stdout
              and models_exist)
        if ok:
            passes += 1
            results.append("PASS test3: expected code 0, got code " + str(proc.returncode))
        else:
            results.append("FAIL test3: expected code 0, got code " + str(proc.returncode))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 4: fake LM Studio server ---
    tmp = tempfile.mkdtemp()
    server = None
    try:
        server, addr = start_fake()
        env = _clean_env(tmp)
        proc = subprocess.run(
            [sys.executable, script, "--yes", "--no-doctor",
             "--home", "ff", "--claude-dir", "cl",
             "--lmstudio-url", addr, "--ollama-url", DEAD],
            capture_output=True, text=True, timeout=300,
            env=env, cwd=tmp,
        )
        ok = (proc.returncode == 0
              and ("CHOSEN LM Studio at " + addr) in proc.stdout)
        models_path = os.path.join(tmp, "ff", "models.json")
        if ok and os.path.exists(models_path):
            with open(models_path, encoding="utf-8") as f:
                doc = json.load(f)
            found_model = False
            for m in doc.get("models", []):
                if m.get("id") == "local-reader":
                    if m.get("endpoint") == addr + "/v1" and m.get("name") == "fake-model-1":
                        found_model = True
                    break
            if not found_model:
                ok = False
        else:
            ok = False
        if ok:
            passes += 1
            results.append("PASS test4: expected code 0 and fake-model-1, got code " + str(proc.returncode))
        else:
            results.append("FAIL test4: expected code 0 and fake-model-1, got code " + str(proc.returncode))
    finally:
        if server is not None:
            server.shutdown()
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 5: --notice -> code 0, starts with NAME ---
    tmp = tempfile.mkdtemp()
    try:
        env = _clean_env(tmp)
        proc = subprocess.run(
            [sys.executable, script, "--notice"],
            capture_output=True, text=True, timeout=300,
            env=env, cwd=tmp,
        )
        ok = proc.returncode == 0 and proc.stdout.startswith("NAME      onboard_cmd.py")
        if ok:
            passes += 1
            results.append("PASS test5: expected code 0 and NAME, got code " + str(proc.returncode))
        else:
            results.append("FAIL test5: expected code 0 and NAME, got code " + str(proc.returncode))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in results:
        print(line)
    print("AUTOTEST " + str(passes) + "/5")
    return 0 if passes == 5 else 1


def _clean_env(tmp):
    env = dict(os.environ)
    env["HOME"] = tmp
    env["USERPROFILE"] = tmp
    env.pop("FRUGALFLOW_HOME", None)
    keys_to_del = [k for k in env if k.endswith("_API_KEY")]
    for k in keys_to_del:
        del env[k]
    keys_to_del = [k for k in env if k.startswith("GIT_")]
    for k in keys_to_del:
        del env[k]
    pycache = tempfile.mkdtemp()
    env["PYTHONPYCACHEPREFIX"] = pycache
    return env


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
