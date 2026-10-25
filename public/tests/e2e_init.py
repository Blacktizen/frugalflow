#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: init adapts models.json to a detected engine, setup walks the layers."""

import os
import sys
import json
import time
import shutil
import tempfile
import subprocess
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")

USAGE = "usage: e2e_init.py | --notice\n"

NOTICE = (
    "NAME      e2e_init.py - end-to-end test: runs frugalflow.py init against a stub Ollama and frugalflow.py setup on the models.json it wrote, in subprocesses.\n"
    "READS     the tools in ../bin, frugalflow.py and its neighbours.\n"
    "WRITES    only a temporary folder, always removed, even on failure: a disposable HOME, a stub server, the four settings files and the model notes file. Exit 0 all six steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_init.py\n"
    "PITFALLS  2026-10-09 the subprocesses get a HOME of their own and no *_API_KEY: detection must come from the stub server only.\n"
    "          2026-10-09 setup must name the stub engine in a DETECTED line; a setup that stops probing fails step 7.\n"
    "          2026-10-09 notes measure must turn the delegation log into a dated measure; a measure typed by hand fails step 8.\n"
)

OLLAMA_MODEL = "e2e-model:1b"

STUB_SRC = (
    "import http.server, sys\n"
    "\n"
    "class Handler(http.server.BaseHTTPRequestHandler):\n"
    "    def do_GET(self):\n"
    "        if self.path == \"/api/tags\":\n"
    "            self._reply(200, b'{\"models\": [{\"name\": \"" + OLLAMA_MODEL + "\"}]}')\n"
    "        else:\n"
    "            self._reply(404, b\"missing\")\n"
    "\n"
    "    def _reply(self, code, body):\n"
    "        try:\n"
    "            self.send_response(code)\n"
    "            self.send_header(\"Content-Type\", \"application/json\")\n"
    "            self.send_header(\"Content-Length\", str(len(body)))\n"
    "            self.end_headers()\n"
    "            self.wfile.write(body)\n"
    "        except (BrokenPipeError, ConnectionResetError):\n"
    "            pass\n"
    "\n"
    "    def log_message(self, *args):\n"
    "        pass\n"
    "\n"
    "server = http.server.ThreadingHTTPServer((\"127.0.0.1\", 0), Handler)\n"
    "with open(sys.argv[1], \"w\", encoding=\"utf-8\") as handle:\n"
    "    handle.write(str(server.server_address[1]))\n"
    "server.serve_forever()\n"
)

VERIFY_SRC = (
    "import sys, json\n"
    "sys.path.insert(0, sys.argv[1])\n"
    "import layers, config_rules\n"
    "with open(sys.argv[2], encoding=\"utf-8\") as handle:\n"
    "    doc = json.load(handle)\n"
    "errors = layers.verify(doc) + config_rules.validate_models(doc)\n"
    "print(\"ERRORS \" + json.dumps(errors))\n"
    "sys.exit(0 if errors == [] else 1)\n"
)


def make_env(tmp):
    env = dict(os.environ)
    env["HOME"] = tmp
    env["PYTHONPYCACHEPREFIX"] = os.path.join(tmp, "pycache")
    for name in list(env):
        if name.endswith("_API_KEY") or name == "FRUGALFLOW_HOME":
            env.pop(name)
    return env


def run_frugalflow(env, cwd, *args):
    return subprocess.run(
        [sys.executable, FRUGALFLOW] + list(args),
        capture_output=True, text=True, input="", env=env, cwd=cwd)


def wait_port(port_file):
    deadline = time.time() + 15.0
    while time.time() < deadline:
        try:
            with open(port_file, "r", encoding="utf-8") as handle:
                text = handle.read().strip()
            if text:
                return int(text)
        except (OSError, ValueError):
            pass
        time.sleep(0.1)
    return None


def read_models(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def local_reader(doc):
    entries = [m for m in doc.get("models", []) if isinstance(m, dict) and m.get("id") == "local-reader"]
    return entries[0] if len(entries) == 1 else None


def role_model(doc, name):
    for entry in doc.get("roles", []):
        if isinstance(entry, dict) and entry.get("name") == name:
            return entry.get("model")
    return None


def _step1(ollama_url):
    if ollama_url is None:
        return False, "the stub server writes its port within 15 s", "no port file"
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(ollama_url + "/api/tags", timeout=5) as resp:
            body = json.loads(resp.read())
    except Exception as error:
        return False, "GET /api/tags answers " + repr({"models": [{"name": OLLAMA_MODEL}]}), "exception: " + str(error)
    models = body.get("models") if isinstance(body, dict) else None
    ok = isinstance(models, list) and len(models) == 1 and models[0].get("name") == OLLAMA_MODEL
    expected = "GET /api/tags answers one model named " + OLLAMA_MODEL
    got = "body=" + json.dumps(body)
    return ok, expected, got


def _step2(env, tmp, home, claude, ollama_url, models_path):
    proc = run_frugalflow(env, tmp, "init", "--mode", "observe",
                          "--home", home, "--claude-dir", claude,
                          "--ollama-url", ollama_url or "", "--lmstudio-url", "http://127.0.0.1:1")
    expected = ("init exits 0 and models.json holds one local-reader with endpoint "
                + (ollama_url or "?") + "/v1 and name " + OLLAMA_MODEL)
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    try:
        doc = read_models(models_path)
    except (OSError, ValueError) as error:
        return False, expected, "code=0 models.json unreadable: " + str(error)
    lr = local_reader(doc)
    if lr is None:
        return False, expected, "code=0 local-reader entries=" + str(len(doc.get("models", [])))
    ok = lr.get("endpoint") == ollama_url + "/v1" and lr.get("name") == OLLAMA_MODEL
    got = "code=0 endpoint=" + repr(lr.get("endpoint")) + " name=" + repr(lr.get("name"))
    return ok, expected, got


def _step3(env, tmp, home, models_path):
    proc = run_frugalflow(env, tmp, "setup", "--home", home, "--answer", "code=session")
    expected = ("setup --answer code=session exits 0, prints '  SET code session' and "
                "'WROTE " + models_path + "', and role code is session in the file")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    try:
        doc = read_models(models_path)
    except (OSError, ValueError) as error:
        return False, expected, "code=0 models.json unreadable: " + str(error)
    ok = ("  SET code session" in proc.stdout
          and "WROTE " + models_path in proc.stdout
          and role_model(doc, "code") == "session")
    got = ("code=0 set_line=" + str("  SET code session" in proc.stdout)
           + " wrote_line=" + str("WROTE " + models_path in proc.stdout)
           + " code_role=" + repr(role_model(doc, "code")))
    return ok, expected, got


def _step4(env, tmp, home, models_path):
    with open(models_path, "rb") as handle:
        before = handle.read()
    proc = run_frugalflow(env, tmp, "setup", "--home", home, "--answer", "judgment=local-reader")
    refusal = "REFUSED role judgment is in kept layer kept_judgment: it is never delegated"
    expected = ("setup --answer judgment=local-reader exits 1, prints '" + refusal
                + "', and models.json is byte for byte as it was")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 1:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    with open(models_path, "rb") as handle:
        after = handle.read()
    ok = refusal in proc.stdout and after == before
    got = ("code=1 refusal_line=" + str(refusal in proc.stdout)
           + " file_unchanged=" + str(after == before))
    return ok, expected, got


def _step5(env, tmp, models_path):
    proc = subprocess.run(
        [sys.executable, "-c", VERIFY_SRC, BIN, models_path],
        capture_output=True, text=True, env=env, cwd=tmp)
    expected = "the final models.json passes layers.verify and config_rules.validate_models (empty lists)"
    got = "code=" + str(proc.returncode) + " out=" + repr(proc.stdout.splitlines()[:1])
    return proc.returncode == 0, expected, got


def _step6(env, tmp, home):
    notes_path = os.path.join(home, "model_notes.json")
    added_line = "ADDED " + OLLAMA_MODEL + " ollama 2026-10-09"
    pitfall_line = "PITFALL 2026-10-09 ollama s => r"
    valid_line = "VALID " + notes_path
    expected = ("notes add-pitfall --home exits 0 and prints '" + added_line + "', "
                "notes show --home prints '" + pitfall_line + "', "
                "notes check --home exits 0 and prints '" + valid_line + "'")
    proc_add = run_frugalflow(env, tmp, "notes", "add-pitfall", "--home", home,
                              "--model", OLLAMA_MODEL, "--engine", "ollama",
                              "--symptom", "s", "--remedy", "r", "--proof", "p",
                              "--date", "2026-10-09")
    got = "add code=" + str(proc_add.returncode)
    if proc_add.returncode != 0 or proc_add.stdout.strip() != added_line:
        got += " out=" + repr(proc_add.stdout.splitlines()[:2])
        return False, expected, got
    proc_show = run_frugalflow(env, tmp, "notes", "show", "--home", home, "--model", OLLAMA_MODEL)
    got += " | show code=" + str(proc_show.returncode)
    if proc_show.returncode != 0 or proc_show.stdout.strip() != pitfall_line:
        got += " out=" + repr(proc_show.stdout.splitlines()[:2])
        return False, expected, got
    proc_check = run_frugalflow(env, tmp, "notes", "check", "--home", home)
    got += " | check code=" + str(proc_check.returncode)
    if proc_check.returncode != 0 or proc_check.stdout.strip() != valid_line:
        got += " out=" + repr(proc_check.stdout.splitlines()[:2])
        return False, expected, got
    got += (" | add out=" + repr(added_line) + " show out=" + repr(pitfall_line)
            + " check out=" + repr(valid_line) + " notes_file=" + str(os.path.isfile(notes_path)))
    return True, expected, got


def _step7(env, tmp, home, ollama_url):
    proc = run_frugalflow(env, tmp, "setup", "--layers", "--home", home,
                          "--ollama-url", ollama_url or "", "--lmstudio-url", "http://127.0.0.1:1")
    detected_line = "DETECTED local-reader ollama " + (ollama_url or "")
    proposed_line = "PROPOSED local-reader, remote-coder, session"
    expected = ("setup --ollama-url --lmstudio-url exits 0 and prints the exact line '"
                + detected_line + "' and the exact line '" + proposed_line + "'")
    lines = proc.stdout.splitlines()
    ok = (proc.returncode == 0 and detected_line in lines and proposed_line in lines)
    got = ("code=" + str(proc.returncode)
           + " detected_line=" + str(detected_line in lines)
           + " proposed_line=" + str(proposed_line in lines))
    return ok, expected, got


def _step8(env, tmp, home):
    log_path = os.path.join(home, "delegations.jsonl")
    fixture = (
        "{\"time\": \"2026-10-09T10:00:00\", \"model_asked\": \"e2e-model\","
        " \"model_answered\": \"e2e-model\", \"tokens_out\": 120, \"seconds\": 4,"
        " \"status\": \"success\"}\n"
        "{\"time\": \"2026-10-09T10:05:00\", \"model_asked\": \"e2e-model\","
        " \"model_answered\": \"e2e-model\", \"tokens_out\": null, \"seconds\": 2,"
        " \"status\": \"failure\"}\n"
    )
    with open(log_path, "a", encoding="utf-8") as handle:
        handle.write(fixture)
    expected_value = ("2 calls, 1 succeeded (50%), median 30.0 output tokens/s,"
                      " 0 answered by another model")
    expected_line = "MEASURED e2e-model e2e-engine 2026-10-09 " + expected_value
    notes_path = os.path.join(home, "model_notes.json")
    proc = run_frugalflow(env, tmp, "notes", "measure", "--home", home,
                          "--model", "e2e-model", "--engine", "e2e-engine",
                          "--date", "2026-10-09")
    expected = ("notes measure --model e2e-model exits 0 and prints the exact line '"
                + expected_line + "', model_notes.json holds a measured value '"
                + expected_value + "' for (e2e-model, e2e-engine), and "
                "notes measure --model absent-model exits 1")
    got = "measure code=" + str(proc.returncode)
    if proc.returncode != 0 or proc.stdout.strip() != expected_line:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    value_in_notes = False
    try:
        with open(notes_path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
        for entry in doc.get("models", []):
            if (isinstance(entry, dict) and entry.get("model") == "e2e-model"
                    and entry.get("engine") == "e2e-engine"):
                for item in entry.get("measured", []):
                    if isinstance(item, dict) and item.get("value") == expected_value:
                        value_in_notes = True
    except (OSError, ValueError):
        value_in_notes = False
    got += (" | measure out=" + repr(expected_line)
            + " value_in_notes=" + str(value_in_notes))
    if not value_in_notes:
        return False, expected, got
    proc_absent = run_frugalflow(env, tmp, "notes", "measure", "--home", home,
                                 "--model", "absent-model", "--engine", "e2e-engine",
                                 "--date", "2026-10-09")
    got += " | absent code=" + str(proc_absent.returncode)
    if proc_absent.returncode != 1:
        got += " out=" + repr(proc_absent.stdout.splitlines()[:2])
        return False, expected, got
    got += " | absent out=" + repr(proc_absent.stdout.strip())
    return True, expected, got


def main_run():
    tmp = tempfile.mkdtemp()
    server = None
    try:
        env = make_env(tmp)
        stub_path = os.path.join(tmp, "ollama_stub.py")
        with open(stub_path, "w", encoding="utf-8") as handle:
            handle.write(STUB_SRC)
        port_file = os.path.join(tmp, "ollama_port.txt")
        server = subprocess.Popen(
            [sys.executable, stub_path, port_file],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, env=env, cwd=tmp)
        port = wait_port(port_file)
        ollama_url = "http://127.0.0.1:%d" % port if port is not None else None

        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        models_path = os.path.join(home, "models.json")

        fns = [
            lambda: _step1(ollama_url),
            lambda: _step2(env, tmp, home, claude, ollama_url, models_path),
            lambda: _step3(env, tmp, home, models_path),
            lambda: _step4(env, tmp, home, models_path),
            lambda: _step5(env, tmp, models_path),
            lambda: _step6(env, tmp, home),
            lambda: _step7(env, tmp, home, ollama_url),
            lambda: _step8(env, tmp, home),
        ]
        results = []
        for num, fn in enumerate(fns, start=1):
            try:
                ok, expected, got = fn()
            except Exception as error:
                ok, expected, got = False, "the step runs", "exception: " + str(error)
            results.append((num, bool(ok), expected, got))
    finally:
        if server is not None:
            server.terminate()
            try:
                server.wait(timeout=5)
            except subprocess.TimeoutExpired:
                server.kill()
        shutil.rmtree(tmp, ignore_errors=True)

    failed = None
    for num, ok, expected, got in results:
        if ok:
            print("PASS {} expected {} | got {}".format(num, expected, got))
        else:
            print("FAIL {} expected {} | got {}".format(num, expected, got))
            if failed is None:
                failed = (num, got)
    if failed is None:
        print("E2E INIT OK")
        return 0
    print("E2E INIT FAIL {} {}".format(failed[0], failed[1]))
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main_run())
    elif sys.argv[1:] == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
