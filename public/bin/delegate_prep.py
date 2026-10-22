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
from http.server import HTTPServer, BaseHTTPRequestHandler

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import layers

NOTICE = (
    "NAME      delegate_prep.py - turns a role into a checked model plan, or refuses with the reason and its code.\n"
    "READS     --models; the key named by key_env; for a local model, the answers of card_check.py, sampling_check.py and bench_check.py.\n"
    "WRITES    nothing: READY (0), bad arguments or config (2), a check or the session refused (3), content more sensitive than the model (4).\n"
    "EXAMPLE   python3 delegate_prep.py --models ~/.frugalflow/models.json --role code --bench\n"
    "PITFALLS  2026-09-22 a private text was about to leave for a third party; the declared sensitivity is the routing ceiling.\n"
    "          The key is read from the environment and never printed.\n"
)

USAGE = "usage: delegate_prep.py --models FILE --role NAME [--trust LEVEL] [--bench] | --notice | --autotest"


def last_line(text):
    for line in reversed(text.strip().splitlines()):
        if line.strip():
            return line.strip()
    return ""


def prepare(models_path, role, trust, bench=False, timeout=300):
    try:
        with open(models_path, "r") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        return (None, 2, "NO MODELS FILE: " + models_path)

    errors = layers.verify(doc)
    if errors:
        return (None, 2, "MODELS REFUSED: " + errors[0])

    if trust not in layers.TRUST:
        return (None, 2, "UNKNOWN TRUST: " + str(trust))

    model, why = layers.route(doc, role, trust)
    if model is None:
        return (None, 4, "ROLE REFUSED: " + why)

    if model.get("location") == "in_session":
        return (None, 3, "IN SESSION: role " + role + " is held by the session model; do it there")

    key_env = model.get("key_env")
    if isinstance(key_env, str) and key_env:
        key = os.environ.get(key_env)
        if not key:
            return (None, 2, "NO KEY: set " + key_env)
    else:
        key = None

    if model.get("location") == "local":
        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "card_check.py"),
             "--models", models_path, "--role", role, "--probe"],
            capture_output=True, text=True, timeout=timeout
        )
        if r.returncode != 0:
            return (None, 3, last_line(r.stdout))

        r = subprocess.run(
            [sys.executable, os.path.join(HERE, "sampling_check.py"),
             "--models", models_path, "--role", role, "--json"],
            capture_output=True, text=True, timeout=timeout
        )
        if r.returncode != 0:
            return (None, 3, last_line(r.stdout))
        settings = json.loads(last_line(r.stdout))

        if bench:
            r = subprocess.run(
                [sys.executable, os.path.join(HERE, "bench_check.py"),
                 "--models", models_path, "--role", role,
                 "--sampling", json.dumps(settings)],
                capture_output=True, text=True, timeout=timeout
            )
            if r.returncode != 0:
                lines = [l for l in r.stdout.splitlines() if l.strip()]
                msg = lines[0].strip() if lines else ""
                return (None, 3, msg)
    else:
        settings = model["sampling"] if isinstance(model.get("sampling"), dict) else {}

    slots = model.get("max_parallel")
    if isinstance(slots, bool) or not isinstance(slots, int) or slots < 1:
        slots = 1

    plan = {
        "id": model["id"],
        "name": model["name"],
        "endpoint": model["endpoint"],
        "location": model["location"],
        "trust": model["trust"],
        "window": model["context_window"],
        "max_output": model.get("max_output"),
        "settings": settings,
        "key": key,
        "slots": slots,
    }
    return (plan, 0, "READY " + model["name"] + " (" + model["location"] + ")")


def _models_doc(port, closed):
    local = {"id": "reader", "name": "alpha-7b", "location": "local", "endpoint": "http://127.0.0.1:" + str(port) + "/v1", "context_window": 8192, "trust": "private", "key_env": "", "sampling": {"temperature": 0.7}, "max_output": 2048, "max_parallel": 2}
    dead = dict(local, id="dead", endpoint="http://127.0.0.1:" + str(closed) + "/v1")
    far = {"id": "far", "name": "beta-pro", "location": "remote", "endpoint": "https://api.example.com/v1", "context_window": 65536, "trust": "untrusted_third_party", "key_env": "FF_TEST_KEY"}
    me = {"id": "me", "name": "session", "location": "in_session", "trust": "private", "key_env": ""}
    ids = ["reader", "dead", "far", "me"]
    return {"models": [local, dead, far, me], "layers": [{"name": "work", "delegable": True}],
            "roles": [{"name": i, "layer": "work", "model": i} for i in ids]}


def _autotest():
    D = tempfile.mkdtemp()
    try:
        class _Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/v0/models":
                    body = json.dumps({"data": [{"id": "alpha-7b", "loaded_context_length": 8192}]})
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def do_POST(self):
                if self.path == "/v1/chat/completions":
                    length = int(self.headers.get("Content-Length", 0))
                    self.rfile.read(length)
                    body = json.dumps({"model": "alpha-7b", "choices": [{"message": {"content": "1"}}], "usage": {"completion_tokens": 1}})
                    self.send_response(200)
                    self.send_header("Content-Type", "application/json")
                    self.end_headers()
                    self.wfile.write(body.encode())
                else:
                    self.send_response(404)
                    self.end_headers()

            def log_message(self, fmt, *args):
                pass

        server = HTTPServer(("127.0.0.1", 0), _Handler)
        port = server.server_address[1]
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        closed_port = s.getsockname()[1]
        s.close()

        M = os.path.join(D, "models.json")
        with open(M, "w") as f:
            json.dump(_models_doc(port, closed_port), f)

        results = []

        # Test 1
        plan, code, message = prepare(M, "reader", "private", timeout=20)
        exp = "code=0 msg='READY alpha-7b (local)' settings={'temperature': 0.7} slots=2 max_output=2048 window=8192 key=None"
        ok = (
            code == 0
            and message == "READY alpha-7b (local)"
            and plan is not None
            and plan["settings"] == {"temperature": 0.7}
            and plan["slots"] == 2
            and plan["max_output"] == 2048
            and plan["window"] == 8192
            and plan["key"] is None
        )
        got = "code=" + str(code) + " msg='" + str(message) + "'"
        if plan is not None:
            got += " settings=" + repr(plan.get("settings")) + " slots=" + str(plan.get("slots")) + " max_output=" + str(plan.get("max_output")) + " window=" + str(plan.get("window")) + " key=" + repr(plan.get("key"))
        results.append(("test 1", ok, exp, got))

        # Test 2
        plan, code, message = prepare(M, "reader", "private", bench=True, timeout=20)
        exp = "code=3 msg starts with 'BENCH REFUSED alpha-7b: '"
        ok = (code == 3 and message.startswith("BENCH REFUSED alpha-7b: "))
        got = "code=" + str(code) + " msg='" + str(message) + "'"
        results.append(("test 2", ok, exp, got))

        # Test 3
        plan, code, message = prepare(M, "dead", "private", timeout=20)
        exp = "code=3 msg='CARD REFUSED engine_absent: the engine does not answer'"
        ok = (code == 3 and message == "CARD REFUSED engine_absent: the engine does not answer")
        got = "code=" + str(code) + " msg='" + str(message) + "'"
        results.append(("test 3", ok, exp, got))

        # Test 4
        plan, code, message = prepare(M, "far", "private", timeout=20)
        ok1 = (code == 4 and message.startswith("ROLE REFUSED: "))

        saved_key = os.environ.pop("FF_TEST_KEY", None)
        plan, code, message = prepare(M, "far", "untrusted_third_party", timeout=20)
        ok2 = (code == 2 and message == "NO KEY: set FF_TEST_KEY")
        if saved_key is not None:
            os.environ["FF_TEST_KEY"] = saved_key

        plan, code, message = prepare(M, "me", "private", timeout=20)
        ok3 = (code == 3 and message == "IN SESSION: role me is held by the session model; do it there")

        ok = ok1 and ok2 and ok3
        exp = "code 4 + code 2 + code 3"
        got = "ok1=" + str(ok1) + " ok2=" + str(ok2) + " ok3=" + str(ok3)
        results.append(("test 4", ok, exp, got))

        # Test 5
        r = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--models", os.path.join(D, "absent.json"), "--role", "reader"],
            capture_output=True, text=True
        )
        exp_out = "NO MODELS FILE: " + os.path.join(D, "absent.json")
        ok1 = (r.returncode == 2 and r.stdout.strip() == exp_out)

        r = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True
        )
        ok2 = (r.returncode == 2)

        ok = ok1 and ok2
        exp = "rc=2 + rc=2"
        got = "rc=" + str(r.returncode) + " out='" + r.stdout.strip()[:80] + "'"
        results.append(("test 5", ok, exp, got))

        server.shutdown()

        all_pass = True
        for name, passed, expected, obtained in results:
            if passed:
                print("PASS " + name + ": expected " + expected + ", got " + obtained)
            else:
                print("FAIL " + name + ": expected " + expected + ", got " + obtained)
                all_pass = False

        sys.exit(0 if all_pass else 1)
    finally:
        shutil.rmtree(D)


def main():
    if "--notice" in sys.argv[1:]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if "--autotest" in sys.argv[1:]:
        _autotest()

    parser = argparse.ArgumentParser(prog="delegate_prep.py")
    parser.add_argument("--models", required=True)
    parser.add_argument("--role", required=True)
    parser.add_argument("--trust", default="private")
    parser.add_argument("--bench", action="store_true")
    parser.usage = USAGE[len("usage: "):]

    args = parser.parse_args()

    plan, code, message = prepare(args.models, args.role, args.trust, args.bench)
    print(message)
    sys.exit(code)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "delegate_prep", sys.argv[1:])
