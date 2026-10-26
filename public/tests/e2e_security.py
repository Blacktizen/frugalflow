#!/usr/bin/env python3
"""E2E security suite."""

import sys
import os
import json
import shutil
import subprocess
import tempfile
import threading
import http.server

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
CONFIG = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config")

FENCE = chr(96) * 3
BODIES = []

NOTICE = (
    "NAME      e2e_security.py - runs the security suite: delegate.py applies the ceilings of preferences.json, reads anonymization.json beside models.json, and the guard example runs the guard.\n"
    "READS     the tools in ../bin and the examples in ../config next to this file; a local fake engine answers every delegation.\n"
    "WRITES    temporary folders only, removed after each test; one PASS or FAIL line per test, then E2E SECURITY OK (0) or E2E SECURITY FAILED (1).\n"
    "EXAMPLE   python3 e2e_security.py\n"
    "PITFALLS  2026-10-02 the preferences were validated but never applied: --tries 5 ran 5 attempts under a ceiling of 2."
)

PREFS = {
    "schema_version": "1",
    "verbosity": {"final_answer_words": 120, "step_message_words": 30},
    "ceilings": {"max_trust": "private", "max_tries": 2, "max_output_tokens": 100},
    "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
    "grouping": {"independent_calls_same_turn": True},
}

CHECK = 'python3 "$FRUGALFLOW_CANDIDATE" | grep -q 42'


class FakeHandler(http.server.BaseHTTPRequestHandler):
    """Handles POST requests for the fake model engine."""

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(length)
        BODIES.append(json.loads(body))
        resp = {
            "model": "alpha-7b",
            "choices": [
                {
                    "message": {"content": FENCE + "python\nprint(41)\n" + FENCE},
                    "finish_reason": "stop",
                }
            ],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1},
        }
        payload = json.dumps(resp).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        pass


def start_engine():
    """Start the fake engine and return (server, port)."""
    server = http.server.HTTPServer(("127.0.0.1", 0), FakeHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, server.server_address[1]


def make_home(port, prefs, project, with_rules):
    """Create a temporary home directory with all required fixtures."""
    home = tempfile.mkdtemp()
    OWN = {
        "id": "own",
        "name": "alpha-7b",
        "location": "remote",
        "endpoint": "http://127.0.0.1:" + str(port) + "/v1",
        "context_window": 8192,
        "trust": "private",
        "key_env": "",
        "max_output": 1024,
    }
    FAR = dict(OWN)
    FAR["id"] = "far"
    FAR["trust"] = "untrusted_third_party"

    models = {
        "models": [OWN, FAR],
        "layers": [{"name": "work", "delegable": True}],
        "roles": [
            {"name": "code", "layer": "work", "model": "own"},
            {"name": "far", "layer": "work", "model": "far"},
        ],
    }
    with open(os.path.join(home, "models.json"), "w") as f:
        json.dump(models, f)

    with open(os.path.join(home, "rules.json"), "w") as f:
        json.dump({"limits": {}, "rules": []}, f)

    with open(os.path.join(home, "task.md"), "w") as f:
        f.write("NATURE: creation\nWrite print(42).\n")

    if prefs is not None:
        with open(os.path.join(home, "preferences.json"), "w") as f:
            json.dump(prefs, f)

    if project is not None:
        with open(os.path.join(home, ".frugalflow.json"), "w") as f:
            json.dump(project, f)

    if with_rules:
        shutil.copy2(os.path.join(CONFIG, "anonymization.example.json"), os.path.join(home, "anonymization.json"))

    return home


def delegate(home, role, extra):
    """Run delegate.py and return (code, calls, max_tokens, output)."""
    BODIES.clear()
    env = os.environ.copy()
    env["FRUGALFLOW_HOME"] = home
    env["FRUGALFLOW_BRIEF_RULES"] = os.path.join(home, "rules.json")
    args = (
        [sys.executable, os.path.join(BIN, "delegate.py")]
        + ["--timeout", "10", "--file", "task.md", "--role", role, "--out", "a.py", "--verify", CHECK]
        + list(extra)
    )
    proc = subprocess.run(args, cwd=home, env=env, capture_output=True, text=True, timeout=180)
    code = proc.returncode
    calls = len(BODIES)
    max_tokens = None
    for b in BODIES:
        mt = b.get("max_tokens")
        if mt is not None:
            if max_tokens is None or mt > max_tokens:
                max_tokens = mt
    output = proc.stdout + proc.stderr
    return (code, calls, max_tokens, output)


def run_tool(name, *args):
    """Run a tool from BIN and return the subprocess result."""
    return subprocess.run(
        [sys.executable, os.path.join(BIN, name)] + list(args),
        capture_output=True,
        text=True,
        timeout=180,
    )


def test1_self_tests():
    """Test 1: all tools pass their --autotest flag."""
    for tool in ["run_limits.py", "limits_files.py", "exit_log.py", "delegate.py", "chain_vars.py", "python_literal_roles.py"]:
        proc = run_tool(tool, "--autotest")
        if proc.returncode != 0:
            return False, f"{tool} --autotest expected exit 0", f"got exit {proc.returncode}"
    return True, "", ""


def test2_anonymization_path():
    """Test 2: anonymization.json is read beside models.json."""
    server, port = start_engine()
    home = make_home(port, None, None, with_rules=True)
    code, calls, max_tokens, output = delegate(home, "far", ["--trust", "untrusted_third_party"])
    shutil.rmtree(home, ignore_errors=True)
    if code == 4:
        server.shutdown()
        return False, "code != 4 with rules present", f"code {code}"
    if "NO RULES" in output:
        server.shutdown()
        return False, "no 'NO RULES' with rules present", "found 'NO RULES' in output"

    home2 = make_home(port, None, None, with_rules=False)
    code2, calls2, mt2, output2 = delegate(home2, "far", ["--trust", "untrusted_third_party"])
    shutil.rmtree(home2, ignore_errors=True)
    if code2 != 4:
        server.shutdown()
        return False, "code 4 without rules", f"code {code2}"
    if "NO RULES" not in output2:
        server.shutdown()
        return False, "'NO RULES' in output without rules", f"output: {output2[:200]}"
    server.shutdown()
    return True, "", ""


def test3_ceilings():
    """Test 3: preferences.json ceilings are applied."""
    server, port = start_engine()
    home = make_home(port, PREFS, None, with_rules=False)
    code, calls, max_tokens, output = delegate(home, "code", [])
    if calls != 2:
        shutil.rmtree(home, ignore_errors=True)
        server.shutdown()
        return False, "exactly 2 calls", f"{calls} calls"
    if max_tokens is None or max_tokens > 100:
        shutil.rmtree(home, ignore_errors=True)
        server.shutdown()
        return False, "max_tokens <= 100", f"max_tokens={max_tokens}"

    code2, calls2, mt2, output2 = delegate(home, "code", ["--tries", "5"])
    shutil.rmtree(home, ignore_errors=True)
    if code2 != 2:
        server.shutdown()
        return False, "code 2 for --tries 5 under ceiling 2", f"code {code2}"
    if "CEILING" not in output2:
        server.shutdown()
        return False, "'CEILING' in output", f"output: {output2[:200]}"
    if calls2 != 0:
        server.shutdown()
        return False, "0 calls when ceiling rejects", f"{calls2} calls"
    server.shutdown()
    return True, "", ""


def test4_project_file():
    """Test 4: .frugalflow.json project ceilings override preferences."""
    server, port = start_engine()
    project_low = {"schema_version": "1", "ceilings": {"max_tries": 1}}
    home = make_home(port, PREFS, project_low, with_rules=False)
    code, calls, max_tokens, output = delegate(home, "code", [])
    shutil.rmtree(home, ignore_errors=True)
    if calls != 1:
        server.shutdown()
        return False, "exactly 1 call with project max_tries 1", f"{calls} calls"

    project_high = {"schema_version": "1", "ceilings": {"max_tries": 9}}
    home2 = make_home(port, PREFS, project_high, with_rules=False)
    code2, calls2, mt2, output2 = delegate(home2, "code", [])
    shutil.rmtree(home2, ignore_errors=True)
    if code2 != 2:
        server.shutdown()
        return False, "code 2 for project max_tries 9 over ceiling 2", f"code {code2}"
    if "CEILING" not in output2:
        server.shutdown()
        return False, "'CEILING' in output", f"output: {output2[:200]}"
    if calls2 != 0:
        server.shutdown()
        return False, "0 calls when ceiling rejects", f"{calls2} calls"
    server.shutdown()
    return True, "", ""


def test5_guard_example():
    """Test 5: the guard example config drives guard_hook.py --hook."""
    home = tempfile.mkdtemp()
    shutil.copy2(os.path.join(CONFIG, "guard.example.json"), os.path.join(home, "guard.json"))
    with open(os.path.join(home, "delegations.jsonl"), "w"):
        pass

    env = os.environ.copy()
    env["FRUGALFLOW_HOME"] = home

    bash_call = json.dumps({"tool_name": "Bash", "tool_input": {"command": "ls"}})
    proc = subprocess.run(
        [sys.executable, os.path.join(BIN, "guard_hook.py"), "--hook"],
        input=bash_call,
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if "deny" in proc.stdout:
        shutil.rmtree(home, ignore_errors=True)
        return False, "Bash call passes (no deny)", "found 'deny' in output"

    content = "\n".join(f"x{i} = {i}" for i in range(40))
    write_call = json.dumps(
        {"tool_name": "Write", "tool_input": {"file_path": os.path.join(home, "a.py"), "content": content}}
    )
    proc2 = subprocess.run(
        [sys.executable, os.path.join(BIN, "guard_hook.py"), "--hook"],
        input=write_call,
        cwd=home,
        env=env,
        capture_output=True,
        text=True,
        timeout=180,
    )
    if "deny" not in proc2.stdout:
        shutil.rmtree(home, ignore_errors=True)
        return False, "Write call is denied", "no 'deny' in output"

    shutil.rmtree(home, ignore_errors=True)
    return True, "", ""


def test6_readable_targets():
    """Test 6: a variable set between two && and a script run by Python are free; the holes stay closed."""
    sys.path.insert(0, BIN)
    import shell_rules
    run = "python3 - <<'EOF'\nimport subprocess, sys\nsubprocess.run([sys.executable, 'bin/t.py'])\nEOF"
    free = ["cd /x && f=a.md && sed -i '' y $f", run]
    for cmd in free + ["cd /x && f=a.md; sed -i '' y $f", run.replace("subprocess.run", "open('bin/t.py', 'w')\nsubprocess.run")]:
        verdict = shell_rules.judge_command(cmd, {"code_extensions": [".py"], "delegate_tools": []})["verdict"]
        if (verdict == "free") != (cmd in free):
            return False, "free only for the readable commands", f"{verdict} for {cmd!r}"
    return True, "", ""


def main():
    if "--notice" in sys.argv:
        print(NOTICE)
        sys.exit(0)

    tests = [
        (1, "self-tests", test1_self_tests),
        (2, "anonymization path", test2_anonymization_path),
        (3, "ceilings", test3_ceilings),
        (4, "project file", test4_project_file),
        (5, "guard example", test5_guard_example),
        (6, "readable targets", test6_readable_targets),
    ]

    all_passed = True
    for num, name, fn in tests:
        try:
            ok, expected, got = fn()
        except Exception as exc:
            ok, expected, got = False, "no exception", str(exc)
        if ok:
            print(f"PASS {num} {name}")
        else:
            all_passed = False
            print(f"FAIL {num} {name} expected: {expected} got: {got}")

    if all_passed:
        print("E2E SECURITY OK")
        sys.exit(0)
    else:
        print("E2E SECURITY FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
