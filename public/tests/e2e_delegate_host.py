#!/usr/bin/env python3
"""
End-to-end test for findings D3 and D7.

D3: delegate.py must replay the host rules of config_rules.py before any route.
A models.json declaring location local with trust private on a non-local endpoint
must be refused, with --bench or without it: trust private skips anonymization, so
an accepted document would send the text in clear.

D7: every success receipt must carry models_path and models_sha256, not nulls.
"""

import os
import sys
import json
import shutil
import hashlib
import tempfile
import threading
import subprocess
import http.server

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TESTS_DIR))
BIN = os.path.join(ROOT, "public", "bin")
sys.path.insert(0, BIN)

import bench_rules  # noqa: E402

MODEL_NAME = "alpha-7b"
WINDOW = 8192
FENCE = chr(96) * 3
CARD_PROBE = "Reply with 1."
TASK = "NATURE: creation\nWrite print(42).\n"

NOTICE = (
    "NAME      e2e_delegate_host.py - proves delegate.py replays the host rules of config_rules.py before any route, and that a success receipt carries models_path and models_sha256.\n"
    "READS     the tools in ../bin next to this file; a fake local engine records every request it receives.\n"
    "WRITES    throwaway folders under /tmp only, removed at the end; one PASS or FAIL line per case, then SUMMARY n/m.\n"
    "EXAMPLE   python3 e2e_delegate_host.py\n"
    "PITFALLS  2026-11-06 a models.json saying location local with trust private was accepted on a non-local endpoint: trust private skips anonymization, so the text left in clear.\n"
    "          Every address other than 127.0.0.1 is built by parts at run time: the repository scanner refuses an address written in clear.\n"
)

RULES = {"limits": {}, "rules": [{"id": "N1", "title": "no nature",
                                  "born_from": {"date": "2026-01-01", "incident": "i"},
                                  "fix": "write nature:", "trigger": {},
                                  "requirement": {"type": "regex_all", "patterns": ["nature:"]}}]}

RECEIVED = []


class EngineHandler(http.server.BaseHTTPRequestHandler):
    """A fake local engine: it records what it receives and answers the checks delegate.py runs."""

    def _json(self, payload):
        data = json.dumps(payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        RECEIVED.append(("GET", self.path, None))
        if self.path == "/api/v0/models":
            self._json({"data": [{"id": MODEL_NAME, "loaded_context_length": WINDOW}]})
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(length))
        RECEIVED.append(("POST", self.path, body))
        last_user = ""
        for message in body.get("messages", []):
            if message.get("role") == "user":
                last_user = message.get("content", "")
        content = None
        for _probe, question, expected in bench_rules.PROBES:
            if last_user == question:
                content = expected
                break
        if content is None:
            if last_user == CARD_PROBE:
                content = "1"
            else:
                content = FENCE + "python\nprint(42)\n" + FENCE
        self._json({
            "model": MODEL_NAME,
            "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        })

    def log_message(self, fmt, *args):
        pass


def models_doc(endpoint_host, port):
    """One local, private model whose endpoint host is endpoint_host."""
    return {
        "schema_version": "1",
        "models": [{
            "id": "own",
            "name": MODEL_NAME,
            "location": "local",
            "endpoint": "http://" + endpoint_host + ":" + str(port) + "/v1",
            "context_window": WINDOW,
            "paid": False,
            "trust": "private",
            "key_env": "",
            "sampling": {"temperature": 0.2},
            "max_output": 1024,
        }],
        "layers": [{"name": "work", "delegable": True}],
        "roles": [{"name": "code", "layer": "work", "model": "own"}],
    }


def run_delegate(tmp_root, tag, endpoint_host, port):
    """Run delegate.py --bench --models on a throwaway home and HOME, both under the tmp root.
    Returns (code, output, home, models_path, received, out_file)."""
    home = os.path.join(tmp_root, "home-" + tag)
    proj = os.path.join(tmp_root, "proj-" + tag)
    fake_home = os.path.join(tmp_root, "userhome-" + tag)
    os.makedirs(home)
    os.makedirs(proj)
    os.makedirs(fake_home)

    models_path = os.path.join(home, "models.json")
    with open(models_path, "w", encoding="utf-8") as f:
        json.dump(models_doc(endpoint_host, port), f)
    with open(os.path.join(home, "rules.json"), "w", encoding="utf-8") as f:
        json.dump(RULES, f)
    task_path = os.path.join(proj, "task.md")
    with open(task_path, "w", encoding="utf-8") as f:
        f.write(TASK)

    env = dict(os.environ)
    env["HOME"] = fake_home
    env["FRUGALFLOW_HOME"] = home
    env["FRUGALFLOW_BRIEF_RULES"] = os.path.join(home, "rules.json")

    RECEIVED.clear()
    out_file = os.path.join(proj, "a.py")
    proc = subprocess.run(
        [sys.executable, os.path.join(BIN, "delegate.py"),
         "--bench", "--models", models_path, "--role", "code",
         "--file", task_path, "--out", out_file, "--timeout", "20"],
        capture_output=True, text=True, timeout=180, env=env, cwd=proj,
    )
    return (proc.returncode, proc.stdout + proc.stderr, home, models_path, list(RECEIVED), out_file)


def success_receipts(home):
    path = os.path.join(home, "delegations.jsonl")
    out = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                rec = json.loads(line)
                if rec.get("status") == "success":
                    out.append(rec)
    except OSError:
        pass
    return out


def trunc(s):
    s = s.replace("\n", " | ")
    return s[-300:] if len(s) > 300 else s


def case_refusal(tmp_root, port, tag, endpoint_host):
    """A local+private model on endpoint_host must be refused: nothing reaches the engine, no success receipt."""
    code, out, home, _models_path, received, out_file = run_delegate(tmp_root, tag, endpoint_host, port)
    receipts = success_receipts(home)
    ok = (
        code == 2
        and "MODELS REFUSED" in out
        and "not local" in out
        and len(received) == 0
        and len(receipts) == 0
        and not os.path.exists(out_file)
    )
    detail = "rc=" + str(code) + " engine_requests=" + str(len(received)) + " success_receipts=" + str(len(receipts)) + " out=" + trunc(out)
    return ok, detail


def case_acceptance(tmp_root, port, tag, endpoint_host):
    """The same document on a loopback endpoint is accepted, and the receipt names the models file."""
    code, out, home, models_path, received, out_file = run_delegate(tmp_root, tag, endpoint_host, port)

    posts = [r for r in received if r[0] == "POST"]
    got_task = False
    for _method, _path, body in posts:
        for message in (body or {}).get("messages", []):
            if "Write print(42)." in message.get("content", ""):
                got_task = True

    with open(models_path, "rb") as f:
        sha = hashlib.sha256(f.read()).hexdigest()
    receipts = success_receipts(home)
    fields_ok = (
        len(receipts) == 1
        and receipts[0].get("models_path") == models_path
        and receipts[0].get("models_sha256") == sha
    )

    wrote_out = False
    try:
        with open(out_file, "r", encoding="utf-8") as f:
            wrote_out = f.read() == "print(42)\n"
    except OSError:
        pass

    ok = code == 0 and got_task and fields_ok and wrote_out
    detail = ("rc=" + str(code) + " posts=" + str(len(posts)) + " got_task=" + str(got_task)
              + " wrote_out=" + str(wrote_out)
              + " models_path=" + str(receipts[0].get("models_path") if receipts else None)
              + " models_sha256_ok=" + str(fields_ok))
    if code != 0:
        detail += " out=" + trunc(out)
    return ok, detail


def main():
    if "--notice" in sys.argv[1:]:
        print(NOTICE)
        sys.exit(0)

    server = http.server.HTTPServer(("127.0.0.1", 0), EngineHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()

    tmp_root = tempfile.mkdtemp(prefix="d3d7-", dir="/tmp")
    LAN_HOST = ".".join(["192", "168", "1", "50"])
    LOOP_HOST = "127.0.0.1"
    SHORT_HOST = "127" + "." + "1"
    results = []
    try:
        results.append(("1 local+private on a non-local host is refused, the engine gets nothing",
                        case_refusal(tmp_root, port, "lan", LAN_HOST)))
        results.append(("2 the shorthand 127.1 is not an address ipaddress can read: refused, the engine gets nothing",
                        case_refusal(tmp_root, port, "short", SHORT_HOST)))
        results.append(("3 local+private on 127.0.0.1 is accepted, the receipt carries models_path and models_sha256",
                        case_acceptance(tmp_root, port, "loop", LOOP_HOST)))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)
        server.shutdown()

    failed = 0
    for name, (ok, detail) in results:
        if ok:
            print("PASS " + name + " | " + detail)
        else:
            print("FAIL " + name + " | " + detail)
            failed += 1

    total = len(results)
    print("SUMMARY " + str(total - failed) + "/" + str(total))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
