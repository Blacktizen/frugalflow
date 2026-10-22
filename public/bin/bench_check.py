#!/usr/bin/env python3
import sys
import os
import json
import time
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
import bench_rules
import layers

NOTICE = (
    "NAME      bench_check.py - asks a role's model three questions and refuses it if it answers wrong or is not the model asked.\n"
    "READS     models.json from --models, else FRUGALFLOW_HOME, else ~/.frugalflow; --sampling, a JSON object sent with each question.\n"
    "WRITES    nothing: BENCH OK (0), bad arguments or models file (2), BENCH REFUSED (3); SKIPPED for the session model (0).\n"
    "EXAMPLE   python3 bench_check.py --role code --sampling '{\"temperature\": 1.0}'\n"
    "PITFALLS  2026-08-23 an engine answered with another model than the one asked; each answer's model field is checked.\n"
)

USAGE = "usage: bench_check.py --role NAME [--models FILE] [--sampling JSON] [--timeout S] | --notice | --autotest"


def main():
    if "--notice" in sys.argv[1:]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if "--autotest" in sys.argv[1:]:
        sys.exit(_autotest())

    parser = argparse.ArgumentParser()
    parser.add_argument("--models")
    parser.add_argument("--role")
    parser.add_argument("--sampling")
    parser.add_argument("--timeout", type=float, default=120.0)
    args = parser.parse_args()

    if not args.role:
        print(USAGE)
        sys.exit(2)

    if args.sampling is not None:
        try:
            s = json.loads(args.sampling)
        except (json.JSONDecodeError, ValueError):
            s = None
        if not isinstance(s, dict):
            print("BAD SAMPLING: must be a JSON object")
            sys.exit(2)
        sampling = s
    else:
        sampling = {}

    if args.models:
        path = args.models
    elif "FRUGALFLOW_HOME" in os.environ:
        path = os.path.join(os.environ["FRUGALFLOW_HOME"], "models.json")
    else:
        path = os.path.join(os.path.expanduser("~"), ".frugalflow", "models.json")

    try:
        with open(path, "r") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError, ValueError):
        print("NO MODELS FILE: " + path)
        sys.exit(2)

    errors = layers.verify(doc)
    if errors:
        print("MODELS REFUSED: " + errors[0])
        sys.exit(2)

    model, why = layers.route(doc, args.role, layers.TRUST[-1])
    if model is None:
        print("ROLE REFUSED: " + why)
        sys.exit(2)

    if model.get("location") == "in_session":
        print("SKIPPED " + model["id"] + ": not an engine")
        sys.exit(0)

    name = model["name"]
    url = model.get("endpoint", "").rstrip("/") + "/chat/completions"

    headers = {"Content-Type": "application/json"}
    key_env = model.get("key_env")
    if isinstance(key_env, str) and key_env and key_env in os.environ:
        headers["Authorization"] = "Bearer " + os.environ[key_env]

    answers = []
    for (item_name, question, want) in bench_rules.PROBES:
        payload = {"model": name, "messages": [{"role": "user", "content": question}], "max_tokens": 512}
        payload.update(sampling)

        t0 = time.monotonic()
        try:
            req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                raw = resp.read()
            duration = int((time.monotonic() - t0) * 1000)
            try:
                D = json.loads(raw)
            except (json.JSONDecodeError, ValueError):
                answers.append({"probe": item_name, "model": None, "content": None, "error": "invalid answer", "tokens": 0, "ms": duration})
            else:
                content = None
                choices = D.get("choices")
                if isinstance(choices, list) and len(choices) > 0:
                    msg = choices[0].get("message")
                    if isinstance(msg, dict):
                        content = msg.get("content")
                tokens = 0
                usage = D.get("usage")
                if isinstance(usage, dict):
                    t = usage.get("completion_tokens")
                    if isinstance(t, int):
                        tokens = t
                answers.append({"probe": item_name, "model": D.get("model"), "content": content, "error": None, "tokens": tokens, "ms": duration})
        except urllib.error.HTTPError as e:
            duration = int((time.monotonic() - t0) * 1000)
            answers.append({"probe": item_name, "model": None, "content": None, "error": "HTTP " + str(e.code), "tokens": 0, "ms": duration})
        except Exception:
            duration = int((time.monotonic() - t0) * 1000)
            answers.append({"probe": item_name, "model": None, "content": None, "error": "no answer", "tokens": 0, "ms": duration})

    v = bench_rules.verdict(name, answers)
    for line in bench_rules.render(name, v, answers):
        print(line)
    sys.exit(0 if v["ok"] else 3)


def _autotest():
    D = tempfile.mkdtemp()
    try:
        class H(http.server.BaseHTTPRequestHandler):
            QUEUE = []
            BODIES = []

            def do_POST(self):
                length = int(self.headers.get("Content-Length", 0))
                body = json.loads(self.rfile.read(length))
                self.BODIES.append(body)
                resp = self.QUEUE.pop(0)
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.end_headers()
                self.wfile.write(json.dumps(resp).encode())

            def log_message(self, *a):
                pass

        server = http.server.HTTPServer(("127.0.0.1", 0), H)
        port = server.server_address[1]
        threading.Thread(target=server.serve_forever, daemon=True).start()

        def reply(model, content):
            return {"model": model, "choices": [{"message": {"content": content}}], "usage": {"completion_tokens": 5}}

        def models_doc(p):
            return {"models": [
                {"id": "reader", "name": "alpha-7b", "location": "local", "endpoint": "http://127.0.0.1:" + str(p) + "/v1", "context_window": 8192, "trust": "private", "key_env": ""},
                {"id": "me", "name": "session", "location": "in_session", "trust": "private", "key_env": ""}],
              "layers": [{"name": "reading", "delegable": True}],
              "roles": [{"name": "code", "layer": "reading", "model": "reader"}, {"name": "here", "layer": "reading", "model": "me"}]}

        def write_models(p):
            with open(os.path.join(D, "models.json"), "w") as f:
                json.dump(models_doc(p), f)

        def run(extra):
            return subprocess.run(
                [sys.executable, os.path.abspath(__file__)] + extra,
                capture_output=True, text=True, timeout=30)

        results = []

        # Test 1
        H.QUEUE = [reply("alpha-7b", "PONG"), reply("alpha-7b", "391"), reply("alpha-7b", "YES")]
        H.BODIES = []
        write_models(port)
        r = run(["--models", os.path.join(D, "models.json"), "--role", "code", "--timeout", "3"])
        lines = r.stdout.strip().splitlines() if r.stdout.strip() else []
        expected1 = "code 0, 4 lines, first starts with 'BENCH OK alpha-7b: 3/3, '"
        got1 = "code=%d, lines=%d, first=%r" % (r.returncode, len(lines), lines[0] if lines else "")
        ok1 = (r.returncode == 0 and len(lines) == 4 and lines[0].startswith("BENCH OK alpha-7b: 3/3, "))
        results.append(("test 1", ok1, expected1, got1))

        # Test 2
        H.QUEUE = [reply("alpha-7b", "PONG"), reply("beta-3b", "391"), reply("alpha-7b", "YES")]
        H.BODIES = []
        write_models(port)
        r = run(["--models", os.path.join(D, "models.json"), "--role", "code", "--timeout", "3"])
        lines = r.stdout.strip().splitlines() if r.stdout.strip() else []
        expected2 = "code 3, first == 'BENCH REFUSED alpha-7b: model substituted: expected alpha-7b, answered by beta-3b'"
        got2 = "code=%d, first=%r" % (r.returncode, lines[0] if lines else "")
        ok2 = (r.returncode == 3 and len(lines) >= 1 and lines[0] == "BENCH REFUSED alpha-7b: model substituted: expected alpha-7b, answered by beta-3b")
        results.append(("test 2", ok2, expected2, got2))

        # Test 3
        H.QUEUE = [reply("alpha-7b", "PONG"), reply("alpha-7b", "391"), reply("alpha-7b", "YES")]
        H.BODIES = []
        write_models(port)
        r = run(["--models", os.path.join(D, "models.json"), "--role", "code", "--timeout", "3", "--sampling", '{"temperature": 0.5}'])
        lines = r.stdout.strip().splitlines() if r.stdout.strip() else []
        bodies_ok = (len(H.BODIES) == 3 and all(
            b.get("temperature") == 0.5 and b.get("max_tokens") == 512 and b.get("model") == "alpha-7b"
            for b in H.BODIES))
        expected3 = "code 0, len(BODIES)==3, temperature==0.5, max_tokens==512, model==alpha-7b"
        got3 = "code=%d, len(BODIES)=%d, bodies_ok=%s" % (r.returncode, len(H.BODIES), bodies_ok)
        ok3 = (r.returncode == 0 and bodies_ok)
        results.append(("test 3", ok3, expected3, got3))

        # Test 4
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        dead_port = s.getsockname()[1]
        s.close()
        H.QUEUE = []
        H.BODIES = []
        write_models(dead_port)
        r = run(["--models", os.path.join(D, "models.json"), "--role", "code", "--timeout", "3"])
        lines = r.stdout.strip().splitlines() if r.stdout.strip() else []
        ok4a = (r.returncode == 3 and len(lines) >= 2
                and lines[0] == "BENCH REFUSED alpha-7b: 3 probes needed, 0 passed: echo, calc, instruction"
                and lines[1].startswith("  NO echo ("))

        r2 = run(["--models", os.path.join(D, "models.json"), "--role", "here", "--timeout", "3"])
        lines2 = r2.stdout.strip().splitlines() if r2.stdout.strip() else []
        ok4b = (r2.returncode == 0 and lines2 == ["SKIPPED me: not an engine"])

        expected4 = "code 3 + SKIPPED"
        got4 = "4a code=%d, 4b code=%d" % (r.returncode, r2.returncode)
        ok4 = ok4a and ok4b
        results.append(("test 4", ok4, expected4, got4))

        # Test 5
        r = run([])
        ok5a = (r.returncode == 2 and r.stdout.strip() != "")

        r2 = run(["--models", os.path.join(D, "models.json"), "--role", "code", "--timeout", "3", "--sampling", "[1]"])
        lines2 = r2.stdout.strip().splitlines() if r2.stdout.strip() else []
        ok5b = (r2.returncode == 2 and lines2 == ["BAD SAMPLING: must be a JSON object"])

        expected5 = "code 2 + BAD SAMPLING"
        got5 = "5a code=%d, 5b code=%d" % (r.returncode, r2.returncode)
        ok5 = ok5a and ok5b
        results.append(("test 5", ok5, expected5, got5))

        server.shutdown()

        all_ok = True
        for name, passed, expected, got in results:
            if passed:
                print("PASS %s" % name)
            else:
                print("FAIL %s: want %s, got %s" % (name, expected, got))
                all_ok = False

        return 0 if all_ok else 1
    finally:
        shutil.rmtree(D)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bench_check", sys.argv[1:])
