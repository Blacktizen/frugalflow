#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: the MCP server writes the sealed journal and the delegation receipt with the user's rights, outside the sandbox, and refuses the escape routes (verify, out outside the project)."""

import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))
SERVER = os.path.join(BIN, "mcp_server.py")

sys.path.insert(0, HERE)
import e2e_delegation_server  # the fake engine pattern comes from this file

USAGE = "usage: e2e_mcp_server.py | --notice\n"

NOTICE = (
    "NAME      e2e_mcp_server.py - end-to-end test: drives the MCP server over stdio in a subprocess, with a disposable HOME and FRUGALFLOW_HOME and a fake local engine.\n"
    "READS     the tools in ../bin (mcp_server.py, vault_new.py, vault_check.py); everything else lives in temporary folders.\n"
    "WRITES    only a temporary folder, always removed, even on failure: a vault, a models.json, brief rules, one out file, one delegation log, one harden.json. Exit 0 all fifteen steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_mcp_server.py\n"
    "PITFALLS  2026-11-13 the delegate tool takes no trust argument, so the route lands on trust private: the models.json must declare a local model, and the fake engine must answer the card probe (GET /api/v0/models) and the sampling call (POST /v1/chat/completions).\n"
    "          2026-11-13 the card probe POSTs 'Reply with 1.' before the delegation call: a queue that answers every POST in order hands the probe the queued answer and the delegation gets none.\n"
    "          2026-11-13 the receipt is proof: the delegation log line must exist in the disposable FRUGALFLOW_HOME after the tools/call, written by delegate.py itself, not by the server.\n"
    "          2026-11-13 the server confines out to its working folder (its cwd), so the server runs with cwd=work and every refused out path is checked for absence: a refusal that wrote the file is not a refusal.\n"
    "          2026-11-13 out is refused by base name at any depth: CLAUDE.local.md in a subfolder is refused like CLAUDE.md at the root — Claude Code loads both as instructions.\n"
)

RULES = {"limits": {}, "rules": [{"id": "N1", "title": "no nature",
                                  "born_from": {"date": "2026-01-01", "incident": "i"},
                                  "fix": "write nature:", "trigger": {},
                                  "requirement": {"type": "regex_all", "patterns": ["nature:"]}}]}
BRIEF = "NATURE: creation\nWrite print(42).\n"
ANSWER = "```python\nprint(42)\n```"

QUEUE = []


def models_doc(port):
    worker = {"id": "worker", "name": "alpha-7b", "location": "local",
              "endpoint": "http://127.0.0.1:" + str(port) + "/v1",
              "context_window": 8192, "paid": False, "trust": "private",
              "key_env": "", "sampling": {"temperature": 0.7},
              "max_output": 2048, "max_parallel": 2}
    return {"schema_version": "1", "models": [worker],
            "layers": [{"name": "work", "delegable": True}],
            "roles": [{"name": "code", "layer": "work", "model": "worker"}]}


class _Handler(e2e_delegation_server._FakeHandler):
    """The fake engine of e2e_delegation_server, plus the answers a local model needs."""

    def do_GET(self):
        if self.path == "/api/v0/models":
            payload = json.dumps({"data": [{"id": "alpha-7b", "loaded_context_length": 8192}]})
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            # card_check --probe sends "Reply with 1." first: answer it, keep the queued answer for the delegation.
            if "Reply with 1." in body:
                content = "1"
            else:
                content = QUEUE.pop(0) if QUEUE else "NONE"
            payload = json.dumps({
                "model": "alpha-7b",
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()


def make_env(tmp, ff, rules_path):
    env = {k: v for k, v in os.environ.items()
           if k != "CLAUDECODE" and k != "CLAUDE_PROJECT_DIR"
           and not k.startswith("GIT_") and not k.endswith("_API_KEY")}
    env["HOME"] = os.path.join(tmp, "home")
    env["FRUGALFLOW_HOME"] = ff
    env["FRUGALFLOW_BRIEF_RULES"] = rules_path
    return env


def run_e2e():
    server = http.server.HTTPServer(("127.0.0.1", 0), _Handler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    QUEUE.append(ANSWER)

    tmp = tempfile.mkdtemp()
    try:
        # The server confines out to its working folder: run it with cwd=work,
        # and keep the FrugalFlow home inside work so a home path is inside the
        # project and only the home rule can refuse it.
        work = os.path.join(tmp, "work")
        ff = os.path.join(work, "ff")
        os.makedirs(ff, exist_ok=True)
        os.makedirs(os.path.join(tmp, "home"), exist_ok=True)
        with open(os.path.join(ff, "models.json"), "w", encoding="utf-8") as handle:
            json.dump(models_doc(port), handle)
        rules_path = os.path.join(tmp, "rules.json")
        with open(rules_path, "w", encoding="utf-8") as handle:
            json.dump(RULES, handle)
        protected_dir = os.path.join(work, "protected")
        with open(os.path.join(ff, "harden.json"), "w", encoding="utf-8") as handle:
            json.dump({"schema_version": 1, "denyWrite_added": [protected_dir]}, handle)
        env = make_env(tmp, ff, rules_path)

        def tool(name, *args):
            return subprocess.run([sys.executable, "-I", os.path.join(BIN, name)] + list(args),
                                  capture_output=True, text=True, input="", env=env, timeout=60)

        created = tool("vault_new.py", "--root", os.path.join(tmp, "proj"), "--name", "demo")
        vault = os.path.join(tmp, "proj", "vault")
        log_path = os.path.join(vault, "log.md")
        size_before = os.path.getsize(log_path) if os.path.isfile(log_path) else 0
        out_path = os.path.join(work, "answer.py")
        marker = os.path.join(tmp, "pwned")

        def call(i, args):
            return {"jsonrpc": "2.0", "id": i, "method": "tools/call",
                    "params": {"name": "delegate", "arguments": args}}

        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": "2025-06-18", "capabilities": {},
                        "clientInfo": {"name": "e2e", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "journal_add",
             "arguments": {"vault": vault, "title": "Written through the server",
                           "fields": {"Decision": "route writes through the MCP tools",
                                      "Why": "the sandbox blocks Bash writes"}}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "lint_brief",
             "arguments": {"brief": ""}}},
            {"jsonrpc": "2.0", "id": 5, "method": "tools/call", "params": {"name": "journal_add",
             "arguments": {"vault": "relative/vault", "title": "x", "fields": {}}}},
            "not json at all",
            {"jsonrpc": "2.0", "id": 6, "method": "ping"},
            call(7, {"role": "code", "brief": BRIEF, "out": os.path.join(work, "a.txt"),
                     "verify": "touch " + marker}),
            call(8, {"role": "code", "brief": BRIEF, "out": os.path.join(ff, "receipts.jsonl")}),
            call(9, {"role": "code", "brief": BRIEF,
                     "out": os.path.join(work, ".githooks", "pre-commit")}),
            call(10, {"role": "code", "brief": BRIEF,
                      "out": os.path.join(work, ".claude", "settings.json")}),
            call(11, {"role": "code", "brief": BRIEF, "out": os.path.join(work, "CLAUDE.md")}),
            call(12, {"role": "code", "brief": BRIEF, "out": os.path.join(tmp, "outside.py")}),
            call(13, {"role": "code", "brief": BRIEF,
                      "out": os.path.join(protected_dir, "answer.py")}),
            call(14, {"role": "code", "brief": BRIEF, "out": "answer/relative.py"}),
            call(15, {"role": "code", "brief": BRIEF, "out": out_path}),
            call(16, {"role": "code", "brief": BRIEF, "out": os.path.join(work, "CLAUDE.local.md")}),
            call(17, {"role": "code", "brief": BRIEF,
                      "out": os.path.join(work, "sub", "CLAUDE.local.md")}),
        ]

        proc = subprocess.Popen([sys.executable, "-I", SERVER],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env, cwd=work)
        for message in messages:
            proc.stdin.write((message if isinstance(message, str) else json.dumps(message)) + "\n")
        proc.stdin.close()
        stdout = proc.stdout.read()
        stderr = proc.stderr.read()
        exit_code = proc.wait(timeout=180)

        answers = {}
        for line in stdout.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and "id" in obj:
                answers[obj["id"] if obj["id"] is not None else "null"] = obj

        results = []

        def step(num, expected, fn):
            try:
                ok, got = fn()
            except Exception as error:
                ok, got = False, "exception: " + str(error)
            results.append((num, ok, expected, got))

        def refused(i, path):
            """A refusal is only real when the file it guards does not exist."""
            is_error = answers[i]["result"]["isError"]
            text = answers[i]["result"]["content"][0]["text"]
            ok = is_error is True and "out is not allowed" in text and not os.path.exists(path)
            return ok, "isError=" + repr(is_error) + " text=" + repr(text[:80]) \
                   + " file_exists=" + str(os.path.exists(path))

        def s1():
            info = answers[1]["result"]
            ok = (info["serverInfo"]["name"] == "frugalflow" and "tools" in info["capabilities"])
            return ok, "name=" + repr(info["serverInfo"]["name"]) + " capabilities=" + repr(sorted(info["capabilities"]))

        def s2():
            tools = answers[2]["result"]["tools"]
            names = sorted(t["name"] for t in tools)
            schemas = all(t.get("inputSchema", {}).get("type") == "object" for t in tools)
            delegate_props = {}
            for t in tools:
                if t.get("name") == "delegate":
                    delegate_props = t.get("inputSchema", {}).get("properties", {})
            ok = names == ["delegate", "journal_add", "lint_brief", "resume"] and schemas \
                 and "verify" not in delegate_props
            return ok, "names=" + repr(names) + " schemas=" + str(schemas) \
                   + " delegate_props=" + repr(sorted(delegate_props))

        def s3():
            is_error = answers[3]["result"]["isError"]
            grew = os.path.getsize(log_path) > size_before
            checked = tool("vault_check.py", "--vault", vault)
            ok = (created.returncode == 0 and is_error is False and grew
                  and checked.returncode == 0 and exit_code == 0)
            return ok, ("isError=" + repr(is_error) + " log_grew=" + str(grew)
                        + " vault_check=" + str(checked.returncode) + " server_exit=" + str(exit_code))

        def s4():
            is_error = answers[4]["result"]["isError"]
            return is_error is True, "isError=" + repr(is_error)

        def s5():
            text_a = answers[5]["result"]["content"][0]["text"]
            text_b = answers[14]["result"]["content"][0]["text"]
            ok = (answers[5]["result"]["isError"] is True and "path must be absolute" in text_a
                  and answers[14]["result"]["isError"] is True and "path must be absolute" in text_b)
            return ok, "journal=" + repr(text_a) + " delegate=" + repr(text_b)

        def s6():
            parse_ok = answers["null"]["error"]["code"] == -32700
            ping_ok = answers[6]["result"] == {}
            return parse_ok and ping_ok, \
                   "parse_code=" + repr(answers["null"]["error"]["code"]) + " ping=" + repr(answers[6]["result"])

        def s7():
            is_error = answers[7]["result"]["isError"]
            text = answers[7]["result"]["content"][0]["text"]
            ok = (is_error is True and "verify is not accepted" in text
                  and not os.path.exists(marker))
            return ok, "isError=" + repr(is_error) + " text=" + repr(text[:80]) \
                   + " marker_exists=" + str(os.path.exists(marker))

        def s8():
            return refused(8, os.path.join(ff, "receipts.jsonl"))

        def s9():
            return refused(9, os.path.join(work, ".githooks", "pre-commit"))

        def s10():
            return refused(10, os.path.join(work, ".claude", "settings.json"))

        def s11():
            return refused(11, os.path.join(work, "CLAUDE.md"))

        def s12():
            return refused(12, os.path.join(tmp, "outside.py"))

        def s13():
            return refused(13, os.path.join(protected_dir, "answer.py"))

        def s14():
            is_error = answers[15]["result"]["isError"]
            with open(out_path, "r", encoding="utf-8") as handle:
                written = handle.read()
            with open(os.path.join(ff, "delegations.jsonl"), "r", encoding="utf-8") as handle:
                lines = [ln for ln in handle.read().splitlines() if ln.strip()]
            receipt = json.loads(lines[-1]) if lines else {}
            ok = (is_error is False and written == "print(42)\n"
                  and len(lines) >= 1 and receipt.get("status") == "success")
            return ok, ("isError=" + repr(is_error) + " out=" + repr(written)
                        + " receipt_lines=" + str(len(lines)) + " status=" + repr(receipt.get("status")))

        step(1, "initialize: serverInfo frugalflow, capabilities tools", s1)
        step(2, "tools/list: four tools with object schemas, delegate schema has no verify", s2)
        step(3, "journal_add: isError False, log.md grows, vault_check exits 0, server exits 0", s3)
        step(4, "lint_brief: empty brief refused (isError True)", s4)
        step(5, "relative vault and relative out refused: isError True, 'path must be absolute'", s5)
        step(6, "non-JSON line: error -32700 with id null, then ping answers {}", s6)
        step(7, "delegate with verify refused: isError True, 'verify is not accepted', no marker file", s7)
        step(8, "out under FRUGALFLOW_HOME refused: isError True, file absent", s8)
        step(9, "out under .githooks refused: isError True, file absent", s9)
        step(10, "out under .claude refused: isError True, file absent", s10)
        step(11, "out named CLAUDE.md refused: isError True, file absent", s11)
        step(12, "out outside the working folder refused: isError True, file absent", s12)
        step(13, "out covered by a harden.json protected path refused: isError True, file absent", s13)
        step(14, "delegate with out inside the working folder: isError False, out file written, one receipt line status success in the delegation log", s14)

        def s15():
            ok_a, got_a = refused(16, os.path.join(work, "CLAUDE.local.md"))
            ok_b, got_b = refused(17, os.path.join(work, "sub", "CLAUDE.local.md"))
            return ok_a and ok_b, "root=" + got_a + " nested=" + got_b

        step(15, "out named CLAUDE.local.md refused at the root and in a subfolder: isError True, file absent", s15)

        if stderr.strip():
            sys.stderr.write(stderr)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
        server.shutdown()

    all_pass = True
    for num, ok, expected, got in results:
        if ok:
            print("PASS {} expected {} | got {}".format(num, expected, got))
        else:
            print("FAIL {} expected {} | got {}".format(num, expected, got))
            all_pass = False
    if all_pass:
        print("E2E MCP SERVER OK")
        return 0
    print("E2E MCP SERVER FAILED")
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(run_e2e())
    elif sys.argv[1:] == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
