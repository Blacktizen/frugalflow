#!/usr/bin/env python3
"""
End-to-end test for reviewer sequence C5, C8, and control.
"""

import sys
import os
import json
import tempfile
import shutil
import threading
import subprocess
import http.server
import socket
import time


class FakeEngineHandler(http.server.BaseHTTPRequestHandler):
    def __init__(self, log_path, *args, **kwargs):
        self._log_path = log_path
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == "/v1/models":
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            body = json.dumps({"data": [{"id": "fake", "loaded_context_length": 16384}]}).encode("utf-8")
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length)
            with open(self._log_path, "ab") as f:
                f.write(body + b"\n")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            resp = {
                "model": "fake",
                "choices": [{
                    "message": {
                        "role": "assistant",
                        "content": "```python\nprint('code chosen by the assistant, not by a model')\n```"
                    },
                    "finish_reason": "stop"
                }],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1}
            }
            data = json.dumps(resp).encode("utf-8")
            self.send_header("Content-Length", str(len(data)))
            self.wfile.write(data)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, fmt, *args):
        pass


def get_free_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def get_closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    return port


def run_c5(repo_root, tmp_root):
    proj = os.path.join(tmp_root, "proj")
    alt = os.path.join(proj, "alt")
    home = os.path.join(tmp_root, "home")
    os.makedirs(alt, exist_ok=True)
    os.makedirs(home, exist_ok=True)

    engine_log = os.path.join(tmp_root, "engine.log")

    port = get_free_port()
    server = http.server.HTTPServer(("127.0.0.1", port), lambda *a, **kw: FakeEngineHandler(engine_log, *a, **kw))
    srv_thread = threading.Thread(target=server.serve_forever, daemon=True)
    srv_thread.start()

    try:
        models_json = {
            "schema_version": "1",
            "models": [{
                "id": "m",
                "name": "fake",
                "location": "local",
                "endpoint": f"http://127.0.0.1:{port}/v1",
                "context_window": 16384,
                "paid": False,
                "trust": "private",
                "key_env": "",
                "sampling": {"temperature": 0.2}
            }],
            "layers": [{"name": "code_writing", "delegable": True}],
            "roles": [{"name": "code", "layer": "code_writing", "model": "m"}]
        }
        with open(os.path.join(alt, "models.json"), "w", encoding="utf-8") as f:
            json.dump(models_json, f)

        brief_template_path = os.path.join(repo_root, "public", "examples", "brief_template.md")
        with open(brief_template_path, "r", encoding="utf-8") as f:
            brief_content = f.read()
        client_mail = "@".join(["camille.martin", "example.org"])
        client_line = "Client: Camille Martin (fictitious name), 12 rue des Lilas, " + client_mail + " (fictitious address)\n"  # lang-ok: the fixture must read as a French address, to test anonymization
        with open(os.path.join(proj, "task.md"), "w", encoding="utf-8") as f:
            f.write(brief_content)
            f.write(client_line)

        closed_port = get_closed_port()
        home_models = {
            "schema_version": "1",
            "models": [{
                "id": "own",
                "name": "alpha-7b",
                "location": "remote",
                "endpoint": f"http://127.0.0.1:{closed_port}/v1",
                "context_window": 8192,
                "paid": False,
                "trust": "trusted_third_party",
                "key_env": "",
                "sampling": {"temperature": 0.2}
            }],
            "layers": [{"name": "work", "delegable": True}],
            "roles": [{"name": "code", "layer": "work", "model": "own"}]
        }
        with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
            json.dump(home_models, f)

        anon_src = os.path.join(repo_root, "public", "config", "anonymization.example.json")
        shutil.copy2(anon_src, os.path.join(home, "anonymization.json"))

        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = home

        delegate_path = os.path.join(repo_root, "public", "bin", "delegate.py")
        out_path = os.path.join(proj, "count_words.py")

        cmd = [
            sys.executable, delegate_path,
            "--models", os.path.join(alt, "models.json"),
            "--role", "code",
            "--file", os.path.join(proj, "task.md"),
            "--out", out_path,
            "--max-tokens", "2000"
        ]

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env, cwd=proj)
        rc = proc.returncode
        stdout = proc.stdout
        stderr = proc.stderr

        success_receipt = False
        delegations_path = os.path.join(home, "delegations.jsonl")
        if os.path.exists(delegations_path):
            with open(delegations_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line and "success" in line:
                        success_receipt = True
                        break

        leaked = False
        if os.path.exists(engine_log):
            with open(engine_log, "r", encoding="utf-8") as f:
                content = f.read()
                if "Camille" in content or "Martin" in content:
                    leaked = True

        defect = success_receipt or leaked

        def trunc(s):
            s = s.replace("\n", " | ")
            return s[-300:] if len(s) > 300 else s

        print(f"RAW C5 rc={rc} success_receipt={success_receipt} leaked={leaked}")
        print(f"RAW C5 stdout: {trunc(stdout)}")
        print(f"RAW C5 stderr: {trunc(stderr)}")

        if not defect and rc != 0:
            print("PASS C5 defect=False rc!=0")
            return True
        else:
            print(f"FAIL C5 defect={defect} rc={rc}")
            return False

    finally:
        server.shutdown()
        srv_thread.join(timeout=5)


def test_c8(repo_root):
    sys.path.insert(0, os.path.join(repo_root, "public", "bin"))
    import onboard_choice
    import config_rules

    doc = {
        "schema_version": "1",
        "models": [
            {
                "id": "local-reader",
                "name": "m",
                "location": "local",
                "endpoint": "http://127.0.0.1:9000/v1",
                "context_window": 65536,
                "paid": False,
                "trust": "private",
                "key_env": ""
            },
            {
                "id": "remote-coder",
                "name": "n",
                "location": "remote",
                "endpoint": "https://api.example.com/v1",
                "context_window": 131072,
                "paid": True,
                "trust": "trusted_third_party",
                "key_env": "REMOTE_KEY"
            }
        ],
        "layers": [
            {"name": "reading", "delegable": True},
            {"name": "kept", "delegable": False}
        ],
        "roles": [
            {"name": "code", "layer": "reading", "model": "local-reader"},
            {"name": "judgment", "layer": "kept", "model": ""}
        ]
    }

    choice = {"kind": "openai", "endpoint": "https://api.openai.com/v1", "model": "gpt-x", "key_env": ""}
    out = onboard_choice.apply_choice(doc, choice)

    m = None
    for model in out["models"]:
        if model["id"] == "local-reader":
            m = model
            break

    errs = config_rules.validate_models(out)
    dangerous = (m["location"] == "local" and m["trust"] == "private"
                 and m["endpoint"] == "https://api.openai.com/v1")
    ok = (not dangerous) or len(errs) > 0

    print(f"RAW C8 location={m['location']} trust={m['trust']} endpoint={m['endpoint']} validate={errs}")
    if ok:
        print("PASS C8 remote endpoint never sits in local+private without a validation error")
        return True
    else:
        print("FAIL C8 remote endpoint sits in local+private without a validation error")
        return False


def test_c8_control(repo_root):
    sys.path.insert(0, os.path.join(repo_root, "public", "bin"))
    import onboard_choice
    import config_rules

    doc = {
        "schema_version": "1",
        "models": [
            {
                "id": "local-reader",
                "name": "m",
                "location": "local",
                "endpoint": "http://127.0.0.1:9000/v1",
                "context_window": 65536,
                "paid": False,
                "trust": "private",
                "key_env": ""
            },
            {
                "id": "remote-coder",
                "name": "n",
                "location": "remote",
                "endpoint": "https://api.example.com/v1",
                "context_window": 131072,
                "paid": True,
                "trust": "trusted_third_party",
                "key_env": "REMOTE_KEY"
            }
        ],
        "layers": [
            {"name": "reading", "delegable": True},
            {"name": "kept", "delegable": False}
        ],
        "roles": [
            {"name": "code", "layer": "reading", "model": "local-reader"},
            {"name": "judgment", "layer": "kept", "model": ""}
        ]
    }

    choice = {"kind": "ollama", "endpoint": "http://127.0.0.1:11434/v1", "model": "q", "key_env": ""}
    out = onboard_choice.apply_choice(doc, choice)

    m = None
    for model in out["models"]:
        if model["id"] == "local-reader":
            m = model
            break

    errs = config_rules.validate_models(out)
    ok = (m["location"] == "local" and m["trust"] == "private" and errs == [])

    print(f"RAW OK-control location={m['location']} trust={m['trust']} validate={errs}")
    if ok:
        print("PASS OK control ollama keeps local+private valid")
        return True
    else:
        print("FAIL OK control ollama broke local+private")
        return False


def main():
    if len(sys.argv) == 2:
        repo_root = sys.argv[1]
    elif len(sys.argv) == 1:
        repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    else:
        print("usage: python3 e2e_d4_models_source.py [repo_root]")
        sys.exit(2)
    tmp_root = tempfile.mkdtemp(prefix="d4-", dir="/tmp")

    try:
        c5_ok = run_c5(repo_root, tmp_root)
        c8_ok = test_c8(repo_root)
        ctrl_ok = test_c8_control(repo_root)

        if c5_ok and c8_ok and ctrl_ok:
            sys.exit(0)
        else:
            sys.exit(1)
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)


if __name__ == "__main__":
    main()