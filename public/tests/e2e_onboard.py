#!/usr/bin/env python3
"""e2e_onboard.py - end-to-end test for frugalflow setup/uninstall."""

import os
import sys
import json
import tempfile
import shutil
import subprocess
import http.server
import threading

TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "frugalflow.py"
)

DEAD = "http://127.0.0.1:1"

MY_CLAUDE = "# my notes\n"
MY_SETTINGS = "{\"theme\": \"dark\"}\n"
KEYVAL = "s3cr3t-value-0123"


class FakeHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            body = {"data": [{"id": "fake-model-1"}]}
        elif self.path == "/api/tags":
            body = {"models": [{"name": "fake-ollama:1b"}]}
        else:
            self.send_response(404)
            self.end_headers()
            return
        raw = json.dumps(body).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(raw)))
        self.end_headers()
        self.wfile.write(raw)

    def log_message(self, *args):
        pass


def start_fake():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:" + str(server.server_address[1])


TMP = None


def run(args, tmp_home, extra_env=None, stdin_text=None):
    env = dict(os.environ)
    env.pop("HOME", None)
    env.pop("USERPROFILE", None)
    env.pop("FRUGALFLOW_HOME", None)
    for key in list(env.keys()):
        if key.endswith("_API_KEY"):
            del env[key]
        if key.startswith("GIT_"):
            del env[key]
    env["HOME"] = tmp_home
    env["USERPROFILE"] = tmp_home
    env["PYTHONPYCACHEPREFIX"] = os.path.join(TMP, "pyc")
    if extra_env:
        env.update(extra_env)
    cmd = [sys.executable, TOOL] + args
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        input=stdin_text,
        timeout=300,
        env=env,
    )
    return result


def dirs(name):
    home = os.path.join(TMP, name, "home")
    ff = os.path.join(TMP, name, "ff")
    cl = os.path.join(TMP, name, "cl")
    os.makedirs(home, exist_ok=True)
    return home, ff, cl


def models(ff):
    with open(os.path.join(ff, "models.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("models", data if isinstance(data, list) else []):
        if m.get("id") == "local-reader":
            return m
    if isinstance(data, dict) and "models" not in data:
        return data.get("local-reader", data)
    raise AssertionError("local-reader not found in models.json")


def remote(ff):
    with open(os.path.join(ff, "models.json"), "r", encoding="utf-8") as f:
        data = json.load(f)
    for m in data.get("models", data if isinstance(data, list) else []):
        if m.get("id") == "remote-coder":
            return m
    if isinstance(data, dict) and "models" not in data:
        return data.get("remote-coder", data)
    raise AssertionError("remote-coder not found in models.json")


def test_1():
    home, ff, cl = dirs("one")
    res = run(
        ["setup", "--yes", "--home", ff, "--claude-dir", cl,
         "--lmstudio-url", FAKE_LM, "--ollama-url", DEAD],
        home,
    )
    assert res.returncode == 0, "returncode is %d" % res.returncode
    out = res.stdout
    assert "FOUND lmstudio " + FAKE_LM in out, "missing FOUND lmstudio line"
    assert "OK CLAUDE.md has the FrugalFlow block" in out, "missing CLAUDE.md block message"
    assert "SETUP DONE" in out, "missing SETUP DONE"
    m = models(ff)
    assert m["endpoint"] == FAKE_LM + "/v1", "endpoint mismatch"
    assert m["name"] == "fake-model-1", "name mismatch"
    settings_path = os.path.join(cl, "settings.json")
    assert os.path.isfile(settings_path), "settings.json missing"
    with open(settings_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert "guard_hook.py" in content, "guard_hook.py not in settings.json"
    return "PASS 1 setup --yes picks LM Studio and ends with doctor"


def test_2():
    home, ff, cl = dirs("two")
    os.makedirs(cl, exist_ok=True)
    with open(os.path.join(cl, "CLAUDE.md"), "w", encoding="utf-8", newline="") as f:
        f.write(MY_CLAUDE)
    with open(os.path.join(cl, "settings.json"), "w", encoding="utf-8", newline="") as f:
        f.write(MY_SETTINGS)
    res = run(
        ["setup", "--yes", "--home", ff, "--claude-dir", cl,
         "--ollama-url", FAKE_OLL, "--lmstudio-url", DEAD],
        home,
    )
    assert res.returncode == 0, "setup returncode is %d" % res.returncode
    m = models(ff)
    assert m["name"] == "fake-ollama:1b", "ollama name mismatch"
    assert m["endpoint"] == FAKE_OLL + "/v1", "ollama endpoint mismatch"
    with open(os.path.join(cl, "CLAUDE.md"), "r", encoding="utf-8") as f:
        claude_after = f.read()
    assert claude_after != MY_CLAUDE, "CLAUDE.md was not modified"
    backups_dir = os.path.join(ff, "setup-backups")
    assert os.path.isdir(backups_dir), "setup-backups dir missing"
    backup_files = [
        e for e in os.listdir(backups_dir)
        if os.path.isfile(os.path.join(backups_dir, e))
    ]
    assert len(backup_files) == 2, "expected 2 backup files, got %d" % len(backup_files)
    backup_contents = []
    for bf in backup_files:
        with open(os.path.join(backups_dir, bf), "r", encoding="utf-8", newline="") as f:
            backup_contents.append(f.read())
    expected = {MY_CLAUDE, MY_SETTINGS}
    assert set(backup_contents) == expected, "backup contents mismatch"
    manifest_path = os.path.join(ff, "setup-manifest.json")
    assert os.path.isfile(manifest_path), "setup-manifest.json missing"
    res2 = run(["uninstall", "--home", ff, "--claude-dir", cl], home)
    assert res2.returncode == 0, "uninstall returncode is %d" % res2.returncode
    with open(os.path.join(cl, "CLAUDE.md"), "r", encoding="utf-8", newline="") as f:
        claude_restored = f.read()
    assert claude_restored == MY_CLAUDE, "CLAUDE.md not restored byte for byte"
    with open(os.path.join(cl, "settings.json"), "r", encoding="utf-8", newline="") as f:
        settings_restored = f.read()
    assert settings_restored == MY_SETTINGS, "settings.json not restored byte for byte"
    assert not os.path.exists(manifest_path), "setup-manifest.json still exists"
    models_path = os.path.join(ff, "models.json")
    assert not os.path.exists(models_path), "models.json still exists after uninstall"
    return "PASS 2 backups taken, uninstall restores them byte for byte"


def test_3():
    home, ff, cl = dirs("three")
    res = run(
        ["setup", "--yes", "--engine", "openai", "--endpoint", FAKE_LM,
         "--home", ff, "--claude-dir", cl,
         "--lmstudio-url", DEAD, "--ollama-url", DEAD],
        home,
    )
    assert res.returncode == 0, "part A returncode is %d" % res.returncode
    m = models(ff)
    assert m["endpoint"] == FAKE_LM + "/v1", "part A endpoint mismatch"
    assert m["name"] == "fake-model-1", "part A name mismatch"
    home_b, ff_b, cl_b = dirs("three_b")
    res2 = run(
        ["setup", "--yes", "--engine", "openai", "--endpoint", DEAD,
         "--home", ff_b, "--claude-dir", cl_b,
         "--lmstudio-url", DEAD, "--ollama-url", DEAD],
        home_b,
    )
    assert res2.returncode == 4, "part B returncode is %d, expected 4" % res2.returncode
    out_all = res2.stdout + res2.stderr
    assert "REFUSED engine openai not found" in out_all, "missing REFUSED message"
    assert not os.path.exists(os.path.join(ff_b, "models.json")), "models.json should not exist"
    return "PASS 3 typed endpoint is probed, a silent one is refused"


def test_4():
    home, ff, cl = dirs("four")
    res = run(
        ["setup", "--yes", "--engine", "key", "--key-env", "FFTEST_API_KEY",
         "--home", ff, "--claude-dir", cl,
         "--lmstudio-url", DEAD, "--ollama-url", DEAD],
        home,
        extra_env={"FFTEST_API_KEY": KEYVAL},
    )
    assert res.returncode == 0, "returncode is %d" % res.returncode
    r = remote(ff)
    assert r["key_env"] == "FFTEST_API_KEY", "key_env mismatch"
    combined = res.stdout + res.stderr
    assert KEYVAL not in combined, "KEYVAL leaked in output"
    with open(os.path.join(ff, "models.json"), "r", encoding="utf-8") as f:
        models_content = f.read()
    assert KEYVAL not in models_content, "KEYVAL leaked in models.json"
    return "PASS 4 key variable is named, its value never printed or stored"


def test_5():
    # (a) nothing found
    home_a, ff_a, cl_a = dirs("five_a")
    res_a = run(
        ["setup", "--yes", "--home", ff_a, "--claude-dir", cl_a,
         "--lmstudio-url", DEAD, "--ollama-url", DEAD],
        home_a,
    )
    assert res_a.returncode == 0, "5a returncode is %d" % res_a.returncode
    out_a = res_a.stdout
    assert "FOUND nothing" in out_a, "missing FOUND nothing in 5a"
    assert "SETUP DONE" in out_a, "missing SETUP DONE in 5a"
    m_a = models(ff_a)
    assert m_a["endpoint"] == "http://127.0.0.1:8000/v1", "5a endpoint mismatch"

    # (b) interactive
    home_b, ff_b, cl_b = dirs("five_b")
    res_b = run(
        ["setup", "--interactive", "--home", ff_b, "--claude-dir", cl_b,
         "--lmstudio-url", FAKE_LM, "--ollama-url", FAKE_OLL],
        home_b,
        stdin_text="2\n",
    )
    assert res_b.returncode == 0, "5b returncode is %d" % res_b.returncode
    out_b = res_b.stdout
    assert "1) " in out_b, "missing 1) prompt in 5b"
    assert "2) " in out_b, "missing 2) prompt in 5b"
    m_b = models(ff_b)
    assert m_b["name"] == "fake-ollama:1b", "5b name mismatch"

    # (c) refused engine
    home_c, ff_c, cl_c = dirs("five_c")
    res_c = run(
        ["setup", "--yes", "--engine", "ollama",
         "--home", ff_c, "--claude-dir", cl_c,
         "--lmstudio-url", DEAD, "--ollama-url", DEAD],
        home_c,
    )
    assert res_c.returncode == 4, "5c returncode is %d, expected 4" % res_c.returncode
    assert not os.path.exists(os.path.join(ff_c, "models.json")), "5c models.json should not exist"

    return "PASS 5 nothing found, interactive choice, refused engine"


def main():
    global TMP, FAKE_LM, FAKE_OLL
    servers = []
    TMP = tempfile.mkdtemp()
    try:
        srv_lm, FAKE_LM = start_fake()
        srv_oll, FAKE_OLL = start_fake()
        servers.append(srv_lm)
        servers.append(srv_oll)

        tests = [test_1, test_2, test_3, test_4, test_5]
        passed = 0
        for t in tests:
            try:
                line = t()
                print(line)
                passed += 1
            except AssertionError as e:
                print("FAIL %s" % str(e))
            except Exception as e:
                print("FAIL %s: %s" % (type(e).__name__, str(e)))
        print("E2E ONBOARD %d/5" % passed)
        sys.exit(0 if passed == 5 else 1)
    finally:
        for s in servers:
            s.shutdown()
        shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    main()
