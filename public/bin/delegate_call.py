#!/usr/bin/env python3
import sys, os, json, socket, threading, subprocess
import http.server, urllib.request, urllib.error

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import answer_rules
import budget_rules


def failed(refusal, max_tokens, http):
    return {"content": "", "truncated": False, "model": None, "tokens_in": None, "tokens_out": None, "refusal": refusal, "max_tokens": max_tokens, "http": http}


def call(endpoint, name, messages, settings, max_tokens, timeout, key=None, extra=None, retry=True):
    body = {"model": name, "messages": messages, "max_tokens": max_tokens}
    body.update(settings or {})
    body.update(extra or {})
    headers = {"Content-Type": "application/json"}
    if isinstance(key, str) and key:
        headers["Authorization"] = "Bearer " + key
    url = endpoint.rstrip("/") + "/chat/completions"
    req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        text = e.read().decode("utf-8", "replace")
        limit = budget_rules.read_overflow(text)
        if limit is not None and retry:
            chars = sum(len(m["content"]) for m in messages if isinstance(m["content"], str))
            new, why = budget_rules.plan_max_tokens(limit, chars, len(messages), max_tokens)
            if new is None:
                return failed(why, max_tokens, e.code)
            if new < max_tokens:
                return call(endpoint, name, messages, settings, new, timeout, key, extra, retry=False)
        return failed("HTTP " + str(e.code) + (": window " + str(limit) if limit is not None else ""), max_tokens, e.code)
    except Exception:
        return failed("no answer from the engine", max_tokens, None)
    try:
        data = json.loads(raw)
    except ValueError:
        return failed("invalid JSON from the engine", max_tokens, 200)
    ans = answer_rules.read_answer(data, name)
    ans["max_tokens"] = max_tokens
    ans["http"] = 200
    return ans


def _autotest():
    OK_ANSWER = {"model": "alpha-7b", "choices": [{"message": {"content": "done"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 10, "completion_tokens": 2}}
    OVERFLOW_TEXT = "This model's maximum context length is 4096 tokens. However, you requested more."
    MESSAGES = [{"role": "system", "content": "You are terse."}, {"role": "user", "content": "Say done."}]

    class Handler(http.server.BaseHTTPRequestHandler):
        MODE = "ok"
        BODIES = []

        def do_POST(self):
            length = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(length).decode("utf-8"))
            Handler.BODIES.append(body)
            if self.path == "/v1/chat/completions":
                if Handler.MODE == "ok":
                    self._reply(200, json.dumps(OK_ANSWER))
                elif Handler.MODE == "overflow_then_ok":
                    if body["max_tokens"] > 3500:
                        self._reply(400, OVERFLOW_TEXT)
                    else:
                        self._reply(200, json.dumps(OK_ANSWER))
                elif Handler.MODE == "always_overflow":
                    self._reply(400, OVERFLOW_TEXT)
                elif Handler.MODE == "boom":
                    self._reply(500, "boom")
                else:
                    self.send_response(404)
                    self.end_headers()
            else:
                self.send_response(404)
                self.end_headers()

        def _reply(self, code, text):
            payload = text.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    threading.Thread(target=server.serve_forever, daemon=True).start()
    url = "http://127.0.0.1:" + str(port) + "/v1"
    lines = []

    # test 1
    Handler.MODE = "ok"
    Handler.BODIES = []
    a = call(url, "alpha-7b", MESSAGES, {"temperature": 0.5}, 3000, 5, extra={"chat_template_kwargs": {"reasoning_effort": "medium"}})
    ok = (isinstance(a, dict) and a.get("content") == "done" and a.get("refusal") is None
          and a.get("tokens_out") == 2 and a.get("http") == 200 and a.get("max_tokens") == 3000
          and len(Handler.BODIES) == 1 and Handler.BODIES[0].get("temperature") == 0.5
          and Handler.BODIES[0].get("chat_template_kwargs") == {"reasoning_effort": "medium"})
    if ok:
        lines.append("PASS test 1: content=done refusal=None tokens_out=2 http=200 max_tokens=3000 req=1 temp=0.5 ctk=medium")
    else:
        lines.append("FAIL test 1: expected content=done refusal=None tokens_out=2 http=200 max_tokens=3000 req=1 temp=0.5 ctk=medium got " + repr(a))

    # test 2
    Handler.MODE = "overflow_then_ok"
    Handler.BODIES = []
    a = call(url, "alpha-7b", MESSAGES, {}, 60000, 5)
    mt = [b.get("max_tokens") for b in Handler.BODIES]
    ok = (isinstance(a, dict) and a.get("refusal") is None and a.get("max_tokens") == 3448 and mt == [60000, 3448])
    if ok:
        lines.append("PASS test 2: refusal=None max_tokens=3448 mt=[60000, 3448]")
    else:
        lines.append("FAIL test 2: expected refusal=None max_tokens=3448 mt=[60000, 3448] got refusal=" + repr(a.get("refusal")) + " max_tokens=" + repr(a.get("max_tokens")) + " mt=" + repr(mt))

    # test 3
    Handler.MODE = "always_overflow"
    Handler.BODIES = []
    a = call(url, "alpha-7b", MESSAGES, {}, 5000, 5)
    mt = [b.get("max_tokens") for b in Handler.BODIES]
    ok = (isinstance(a, dict) and a.get("refusal") == "HTTP 400: window 4096" and a.get("http") == 400 and mt == [5000, 3448])
    if ok:
        lines.append("PASS test 3: refusal='HTTP 400: window 4096' http=400 mt=[5000, 3448]")
    else:
        lines.append("FAIL test 3: expected refusal='HTTP 400: window 4096' http=400 mt=[5000, 3448] got refusal=" + repr(a.get("refusal")) + " http=" + repr(a.get("http")) + " mt=" + repr(mt))

    # test 4
    Handler.MODE = "boom"
    Handler.BODIES = []
    a = call(url, "alpha-7b", MESSAGES, {}, 100, 5)
    ok1 = isinstance(a, dict) and a.get("refusal") == "HTTP 500" and len(Handler.BODIES) == 1
    Handler.MODE = "ok"
    Handler.BODIES = []
    a2 = call(url, "beta-3b", MESSAGES, {}, 100, 5)
    ok2 = isinstance(a2, dict) and a2.get("refusal") == "model substituted: expected beta-3b, answered by alpha-7b"
    if ok1 and ok2:
        lines.append("PASS test 4: refusal='HTTP 500' req=1 then refusal='model substituted: expected beta-3b, answered by alpha-7b'")
    else:
        lines.append("FAIL test 4: expected refusal='HTTP 500' req=1 then 'model substituted: expected beta-3b, answered by alpha-7b' got refusal=" + repr(a.get("refusal")) + " req=" + str(len(Handler.BODIES)) + " refusal2=" + repr(a2.get("refusal")))

    # test 5
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port_closed = s.getsockname()[1]
    s.close()
    a = call("http://127.0.0.1:" + str(port_closed) + "/v1", "alpha-7b", MESSAGES, {}, 100, 5)
    ok1 = isinstance(a, dict) and a.get("refusal") == "no answer from the engine"
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    ok2 = r.returncode == 0 and r.stdout.startswith("NAME      delegate_call.py")
    if ok1 and ok2:
        lines.append("PASS test 5: refusal='no answer from the engine' subprocess rc=0 notice_ok")
    else:
        lines.append("FAIL test 5: expected refusal='no answer from the engine' subprocess rc=0 notice_ok got refusal=" + repr(a.get("refusal")) + " rc=" + str(r.returncode) + " stdout[:40]=" + repr(r.stdout[:40]))

    for line in lines:
        print(line)
    return 0 if all(l.startswith("PASS") for l in lines) else 1


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print("NAME      delegate_call.py - makes one exchange with an OpenAI-compatible engine, retrying once with the real window when it reports an overflow.")
        print("READS     nothing on disk: the endpoint, the messages and the settings it is given; the engine's answer.")
        print("WRITES    nothing: call() returns the judged answer, with the max_tokens used and the HTTP code.")
        print("EXAMPLE   python3 delegate_call.py --notice")
        print("PITFALLS  2026-09-17 the advertised window was wider than the served one and the request failed; the engine's own error now sets the retry budget.")
        print("          The engine's error text is never copied into the refusal: it may echo the prompt.")
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: delegate_call.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "delegate_call", sys.argv[1:])
