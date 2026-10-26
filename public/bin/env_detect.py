import sys
import os
import json
import subprocess
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import example_defaults

OLLAMA_URL = example_defaults.get("engines", "ollama.url")
LMSTUDIO_URL = example_defaults.get("engines", "lmstudio.url")

_NO_PROXY_OPENER = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def probe(base_url, path, timeout=1.0):
    try:
        with _NO_PROXY_OPENER.open(base_url + path, timeout=timeout) as resp:
            if resp.getcode() != 200:
                return False
            json.loads(resp.read())
            return True
    except Exception:
        return False


def detect(ollama_url, lmstudio_url, environ):
    findings = []
    if probe(ollama_url, "/api/tags"):
        findings.append({"kind": "ollama", "where": ollama_url})
    if probe(lmstudio_url, "/v1/models"):
        findings.append({"kind": "lmstudio", "where": lmstudio_url})
    for name in sorted(environ):
        if name.endswith("_API_KEY") and environ[name]:
            findings.append({"kind": "key", "where": name})
    return findings


def describe(findings):
    if not findings:
        return ["FOUND nothing: no local engine answered and no *_API_KEY is set; delegation stays off until you add one."]
    return ["FOUND " + f["kind"] + " " + f["where"] for f in findings]


NOTICE = (
    "NAME      env_detect.py - probes the local Ollama and LM Studio endpoints and lists *_API_KEY names.\n"
    "READS     nothing on disk; probe() sends one HTTP GET to the URL it is given.\n"
    "WRITES    nothing: probe() returns a bool, detect() and describe() return values, they never print or write.\n"
    "EXAMPLE   python3 env_detect.py --notice\n"
    "PITFALLS  2026-10-03 the macOS proxy auto-detection killed the process mid-probe; every request now opens through an opener built with ProxyHandler({}).\n"
)


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    print("usage: env_detect.py --notice | --autotest")
    return 2


def _autotest():
    import http.server
    import threading
    import time

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == "/ok":
                self._reply(200, b'{"models": []}')
            elif self.path == "/badjson":
                self._reply(200, b"not json")
            elif self.path == "/slow":
                time.sleep(0.4)
                self._reply(200, b'{"a": 1}')
            elif self.path == "/api/tags":
                self._reply(200, b'{"models": []}')
            elif self.path == "/v1/models":
                self._reply(200, b'{"data": []}')
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

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    base = "http://127.0.0.1:%d" % server.server_address[1]

    all_pass = True

    # Test 1
    ok = (probe(base, "/ok") is True
          and probe(base, "/badjson") is False
          and probe(base, "/missing") is False
          and probe(base, "/slow", timeout=0.2) is False)
    if ok:
        print("PASS test1: probe true on 200 JSON, false on bad JSON, 404 and timeout")
    else:
        print("FAIL test1: ok=%r badjson=%r missing=%r slow=%r" % (
            probe(base, "/ok"), probe(base, "/badjson"), probe(base, "/missing"), probe(base, "/slow", timeout=0.2)))
        all_pass = False

    # Test 2
    environ = {"OPENAI_API_KEY": "sk-x", "EMPTY_API_KEY": "", "NOT_A_KEY": "v", "ANTHROPIC_API_KEY": "y"}
    findings = detect(base, base, environ)
    expected = [{"kind": "ollama", "where": base},
                {"kind": "lmstudio", "where": base},
                {"kind": "key", "where": "ANTHROPIC_API_KEY"},
                {"kind": "key", "where": "OPENAI_API_KEY"}]
    if findings == expected:
        print("PASS test2: detect orders engines then sorted non-empty *_API_KEY names")
    else:
        print("FAIL test2: expected %r got %r" % (expected, findings))
        all_pass = False

    # Test 3
    if describe([]) == ["FOUND nothing: no local engine answered and no *_API_KEY is set; delegation stays off until you add one."]:
        print("PASS test3: describe([]) returns the exact one-line list")
    else:
        print("FAIL test3: got %r" % describe([]))
        all_pass = False

    # Test 4
    lines = describe(findings)
    expected_lines = ["FOUND ollama " + base, "FOUND lmstudio " + base,
                      "FOUND key ANTHROPIC_API_KEY", "FOUND key OPENAI_API_KEY"]
    if lines == expected_lines:
        print("PASS test4: describe(findings) returns one FOUND line per finding")
    else:
        print("FAIL test4: expected %r got %r" % (expected_lines, lines))
        all_pass = False

    # Test 5
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    ok = (probe("http://127.0.0.1:1", "/x", timeout=0.2) is False
          and r.returncode == 0 and r.stdout.startswith("NAME      env_detect.py"))
    if ok:
        print("PASS test5: unreachable host is false and --notice prints the notice")
    else:
        print("FAIL test5: rc=%d stdout=%r" % (r.returncode, r.stdout))
        all_pass = False

    server.shutdown()
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "env_detect", sys.argv[1:])
