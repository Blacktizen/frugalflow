#!/usr/bin/env python3
import sys
import os
import json
import argparse
import socket
import tempfile
import shutil
import threading
import subprocess
import http.server
import urllib.request
import urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import card_rules
import layers

NOTICE = (
    "NAME      card_check.py - refuses a local delegation when the engine does not serve the role's model, alone, with enough context.\n"
    "READS     models.json from --models, else FRUGALFLOW_HOME, else ~/.frugalflow; the engine's model list; with --probe, a one-token answer.\n"
    "WRITES    nothing: CARD OK (0), SKIPPED for a remote model (0), bad arguments or models file (2), CARD REFUSED (3), PROBE REFUSED (4).\n"
    "EXAMPLE   python3 card_check.py --role code --probe\n"
    "PITFALLS  2026-08-23 an engine served another model than the one asked; only the answer's model field is trusted.\n"
    "          2026-09-22 an environment variable could switch this check off in silence; there is no switch any more."
)


class _FakeHandler(http.server.BaseHTTPRequestHandler):
    LMS = None
    V1 = {}
    ANSWER = ""

    def log_message(self, *a):
        pass

    def do_GET(self):
        if self.path == "/api/v0/models":
            if _FakeHandler.LMS is None:
                self.send_response(404)
                self.end_headers()
            else:
                body = json.dumps(_FakeHandler.LMS).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(body)
        elif self.path == "/v1/models":
            body = json.dumps(_FakeHandler.V1).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            self.rfile.read(length)
            body = json.dumps({"model": _FakeHandler.ANSWER, "choices": []}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)
        else:
            self.send_response(404)
            self.end_headers()


def _autotest():
    tmpdir = tempfile.mkdtemp()
    failures = 0

    def models_doc(port):
        return {"models": [
            {"id": "reader", "name": "alpha-7b", "location": "local",
             "endpoint": "http://127.0.0.1:" + str(port) + "/v1",
             "context_window": 65536, "trust": "private", "key_env": ""},
            {"id": "remote-coder", "name": "beta-pro", "location": "remote",
             "endpoint": "https://api.example.com/v1",
             "context_window": 131072, "trust": "untrusted_third_party", "key_env": "X_KEY"}],
            "layers": [{"name": "reading", "delegable": True}],
            "roles": [{"name": "code", "layer": "reading", "model": "reader"},
                      {"name": "remote", "layer": "reading", "model": "remote-coder"}]}

    LMS_OK = {"data": [{"id": "alpha-7b", "loaded_context_length": 65536}]}
    V1_SHORT = {"data": [{"id": "alpha-7b", "max_model_len": 32768}]}

    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeHandler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()

    models_file = os.path.join(tmpdir, "models.json")

    def run(args_list):
        return subprocess.run(
            [sys.executable, os.path.abspath(__file__)] + args_list,
            capture_output=True, text=True, timeout=20
        )

    def lines_of(p):
        s = p.stdout.strip()
        return s.splitlines() if s else []

    def check(label, p, exp_code, exp_lines):
        nonlocal failures
        got = lines_of(p)
        if p.returncode == exp_code and got == exp_lines:
            print("PASS " + label + " expected=" + str(exp_code) + " " + str(exp_lines) + " got=" + str(p.returncode) + " " + str(got))
        else:
            print("FAIL " + label + " expected=" + str(exp_code) + " " + str(exp_lines) + " got=" + str(p.returncode) + " " + str(got))
            failures += 1

    # Test 1
    _FakeHandler.LMS = LMS_OK
    _FakeHandler.V1 = {}
    _FakeHandler.ANSWER = "alpha-7b"
    with open(models_file, "w") as f:
        f.write(json.dumps(models_doc(port)))
    p = run(["--models", models_file, "--role", "code", "--probe", "--timeout", "3"])
    check("t1", p, 0, ["CARD OK: alpha-7b loaded with 65536 tokens", "PROBE OK: answered by alpha-7b"])

    # Test 2
    _FakeHandler.LMS = None
    _FakeHandler.V1 = V1_SHORT
    _FakeHandler.ANSWER = ""
    with open(models_file, "w") as f:
        f.write(json.dumps(models_doc(port)))
    p = run(["--models", models_file, "--role", "code", "--timeout", "3"])
    check("t2", p, 3, ["CARD REFUSED short_context: 32768 tokens loaded, 65536 required"])

    # Test 3
    _FakeHandler.LMS = LMS_OK
    _FakeHandler.V1 = {}
    _FakeHandler.ANSWER = "beta-3b"
    with open(models_file, "w") as f:
        f.write(json.dumps(models_doc(port)))
    p = run(["--models", models_file, "--role", "code", "--probe", "--timeout", "3"])
    check("t3", p, 4, ["CARD OK: alpha-7b loaded with 65536 tokens",
                        "PROBE REFUSED model_substituted: expected alpha-7b, answered by beta-3b"])

    # Test 4
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    dead_port = s.getsockname()[1]
    s.close()
    with open(models_file, "w") as f:
        f.write(json.dumps(models_doc(dead_port)))
    p = run(["--models", models_file, "--role", "code", "--timeout", "3"])
    check("t4a", p, 3, ["CARD REFUSED engine_absent: the engine does not answer"])

    p = run(["--models", models_file, "--role", "remote"])
    check("t4b", p, 0, ["SKIPPED remote-coder: not a local model"])

    # Test 5
    p = run([])
    got = lines_of(p)
    if p.returncode == 2 and len(got) > 0:
        print("PASS t5a expected=2 non-empty got=" + str(p.returncode) + " " + str(got))
    else:
        print("FAIL t5a expected=2 non-empty got=" + str(p.returncode) + " " + str(got))
        failures += 1

    bad_path = os.path.join(tmpdir, "nonexistent.json")
    p = run(["--models", bad_path, "--role", "code"])
    got = lines_of(p)
    if p.returncode == 2 and got and got[0].startswith("NO MODELS FILE: "):
        print("PASS t5b expected=2 NO MODELS FILE: got=" + str(p.returncode) + " " + str(got))
    else:
        print("FAIL t5b expected=2 NO MODELS FILE: got=" + str(p.returncode) + " " + str(got))
        failures += 1

    shutil.rmtree(tmpdir)
    sys.exit(1 if failures else 0)


def _main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--notice", action="store_true")
    parser.add_argument("--autotest", action="store_true")
    parser.add_argument("--models")
    parser.add_argument("--role")
    parser.add_argument("--probe", action="store_true")
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args()

    if args.notice:
        print(NOTICE)
        sys.exit(0)

    if args.autotest:
        _autotest()
        return

    if not args.role:
        print("usage: card_check.py --role NAME [--models FILE] [--probe] [--timeout S] | --notice | --autotest")
        sys.exit(2)

    if args.models:
        models_path = args.models
    elif "FRUGALFLOW_HOME" in os.environ:
        models_path = os.path.join(os.environ["FRUGALFLOW_HOME"], "models.json")
    else:
        models_path = os.path.join(os.path.expanduser("~"), ".frugalflow", "models.json")

    try:
        with open(models_path, "r") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        print("NO MODELS FILE: " + models_path)
        sys.exit(2)

    errors = layers.verify(doc)
    if errors:
        print("MODELS REFUSED: " + errors[0])
        sys.exit(2)

    model, why = layers.route(doc, args.role, layers.TRUST[-1])
    if model is None:
        print("ROLE REFUSED: " + why)
        sys.exit(2)

    if model.get("location") != "local":
        print("SKIPPED " + model["id"] + ": not a local model")
        sys.exit(0)

    name = model.get("name")
    window = model.get("context_window")
    if not isinstance(name, str) or not name or not isinstance(window, int) or isinstance(window, bool):
        print("MODELS REFUSED: model " + model["id"] + " lacks name or context_window")
        sys.exit(2)

    endpoint = model.get("endpoint", "").rstrip("/")
    base = endpoint[:-3] if endpoint.endswith("/v1") else endpoint

    headers = {}
    key_env = model.get("key_env")
    if isinstance(key_env, str) and key_env and key_env in os.environ:
        headers["Authorization"] = "Bearer " + os.environ[key_env]

    try:
        req = urllib.request.Request(base + "/api/v0/models", headers=headers)
        resp = urllib.request.urlopen(req, timeout=args.timeout)
        payload = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        if e.code == 404:
            try:
                req2 = urllib.request.Request(endpoint + "/models", headers=headers)
                resp2 = urllib.request.urlopen(req2, timeout=args.timeout)
                payload = json.loads(resp2.read().decode("utf-8"))
            except Exception:
                print("CARD REFUSED engine_absent: the engine does not answer")
                sys.exit(3)
        else:
            print("CARD REFUSED engine_absent: the engine does not answer")
            sys.exit(3)
    except Exception:
        print("CARD REFUSED engine_absent: the engine does not answer")
        sys.exit(3)

    models_list, _ = card_rules.parse_models(payload)
    code, message = card_rules.judge(models_list, name, window)
    if code != "ok":
        print("CARD REFUSED " + code + ": " + message)
        sys.exit(3)
    print("CARD OK: " + message)

    if not args.probe:
        sys.exit(0)

    probe_body = json.dumps({
        "model": name,
        "messages": [{"role": "user", "content": "Reply with 1."}],
        "max_tokens": 1,
        "stream": False
    }).encode("utf-8")

    probe_headers = {"Content-Type": "application/json"}
    probe_headers.update(headers)

    outcome = {}
    try:
        req3 = urllib.request.Request(
            endpoint + "/chat/completions",
            data=probe_body, headers=probe_headers, method="POST"
        )
        resp3 = urllib.request.urlopen(req3, timeout=args.timeout)
        raw = resp3.read().decode("utf-8")
        status_code = resp3.getcode()
        try:
            body_json = json.loads(raw)
            outcome = {"reached": True, "status": status_code, "model": body_json.get("model")}
        except (json.JSONDecodeError, ValueError):
            outcome = {"reached": True, "status": status_code, "model": None}
    except urllib.error.HTTPError as e:
        outcome = {"reached": True, "status": e.code}
    except (socket.timeout, TimeoutError):
        outcome = {"timed_out": True}
    except urllib.error.URLError as e:
        reason = getattr(e, "reason", None)
        if isinstance(reason, (socket.timeout, TimeoutError)):
            outcome = {"timed_out": True}
        else:
            outcome = {}
    except OSError:
        outcome = {}

    code, message = card_rules.classify_probe(outcome, name)
    if code != "ok":
        print("PROBE REFUSED " + code + ": " + message)
        sys.exit(4)
    print("PROBE OK: " + message)
    sys.exit(0)


def _cli():
    _main()


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "card_check", sys.argv[1:])
