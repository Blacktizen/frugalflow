#!/usr/bin/env python3
# e2e_disarmed_guard.py - end-to-end test for disarmed mode guard behavior

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

GUARD_SETTINGS = {
    "code_extensions": [".py", ".sh", ".js", ".ts", ".ipynb"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "delegate_tools": ["delegate.py"],
    "fix_hint": "delegate it.",
}

PREFS = {
    "schema_version": "1",
    "switch": {"enabled": True, "mode": "active"},
}

TOOL_30_LINES = "\n".join("x%d = %d" % (i, i) for i in range(30)) + "\n"


def CALL(tool, inp):
    return json.dumps({"tool_name": tool, "tool_input": inp})


def run_hook(home_user, home_ff, work_dir, payload, env_extra=None, active=None, guard_env=None):
    """Run the guard hook as Claude Code does. payload is a dict, not a JSON string."""
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "FRUGALFLOW_HOME": home_ff,
        "HOME": home_user,
    }
    if env_extra:
        env.update(env_extra)
    if guard_env:
        env["FRUGALFLOW_GUARD"] = guard_env

    # Write guard.json with active setting
    guard_json = dict(GUARD_SETTINGS)
    if active is not None:
        guard_json["active"] = active
    if guard_env:
        guard_json["allow_env_disarm"] = True
    with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(guard_json, f)

    # Write preferences.json
    with open(os.path.join(home_user, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)

    # Write empty delegations.jsonl
    with open(os.path.join(home_ff, "delegations.jsonl"), "w", encoding="utf-8") as f:
        pass

    script_path = os.path.join(BIN, "guard_hook.py")
    r = subprocess.run(
        [sys.executable, script_path, "--hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=work_dir,
        timeout=30,
    )
    return r.returncode, r.stdout.strip()


def get_decision(stdout):
    """Extract permissionDecision from hook output. Empty stdout = allow."""
    if not stdout:
        return "allow"
    try:
        d = json.loads(stdout.splitlines()[-1])
        return d.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return "unreadable"


def audit_has_label(home_ff, label):
    """Check if audit.jsonl contains a line with the given audit label."""
    path = os.path.join(home_ff, "audit.jsonl")
    if not os.path.exists(path):
        return False
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    if json.loads(line).get("audit") == label:
                        return True
                except json.JSONDecodeError:
                    pass
    return False


def main():
    results = []
    all_pass = True

    with tempfile.TemporaryDirectory() as tmp:
        home_user = os.path.join(tmp, "home_user")
        home_ff = os.path.join(tmp, "home_ff")
        work_dir = os.path.join(tmp, "work")
        os.makedirs(home_user)
        os.makedirs(home_ff)
        os.makedirs(work_dir)

        prefs_path = os.path.join(home_user, "preferences.json")

        # --- Case a: active: false, Write to preferences.json ---
        payload = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(home_ff, "preferences.json"), "content": "{}"}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=False)
        decision = get_decision(stdout)
        expected = "deny"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("a", expected, decision, passed))

        # --- Case b: active: false, Bash append to delegations.jsonl ---
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo '{}' >> " + os.path.join(home_ff, "delegations.jsonl")}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=False)
        decision = get_decision(stdout)
        expected = "deny"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("b", expected, decision, passed))

        # --- Case c: active: false, Write 30-line tool.py in work/ ---
        tool_py = os.path.join(work_dir, "tool.py")
        payload = {"tool_name": "Write", "tool_input": {"file_path": tool_py, "content": TOOL_30_LINES}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=False)
        decision = get_decision(stdout)
        expected = "allow"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("c", expected, decision, passed))

        # --- Case d: active: true but FRUGALFLOW_GUARD=0 ---
        # Re-create guard.json with active: true (default)
        with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
            json.dump(GUARD_SETTINGS, f)

        # d.a: Write to preferences.json with FRUGALFLOW_GUARD=0
        payload = {"tool_name": "Write", "tool_input": {"file_path": os.path.join(home_ff, "preferences.json"), "content": "{}"}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=True, guard_env="0")
        decision = get_decision(stdout)
        expected = "deny"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("d.a", expected, decision, passed))

        # d.b: Bash append to delegations.jsonl with FRUGALFLOW_GUARD=0
        payload = {"tool_name": "Bash", "tool_input": {"command": "echo '{}' >> " + os.path.join(home_ff, "delegations.jsonl")}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=True, guard_env="0")
        decision = get_decision(stdout)
        expected = "deny"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("d.b", expected, decision, passed))

        # d.c: Write 30-line tool.py in work/ with FRUGALFLOW_GUARD=0
        tool_py2 = os.path.join(work_dir, "tool2.py")
        payload = {"tool_name": "Write", "tool_input": {"file_path": tool_py2, "content": TOOL_30_LINES}}
        code, stdout = run_hook(home_user, home_ff, work_dir, payload, active=True, guard_env="0")
        decision = get_decision(stdout)
        expected = "allow"
        passed = decision == expected
        if not passed:
            all_pass = False
        results.append(("d.c", expected, decision, passed))

        # --- Case e: active: false, Write 30-line tool.py with audit check ---
        # Use a fresh temp dir for this case to have clean audit log
        with tempfile.TemporaryDirectory() as tmp2:
            home_user2 = os.path.join(tmp2, "home_user")
            home_ff2 = os.path.join(tmp2, "home_ff")
            work_dir2 = os.path.join(tmp2, "work")
            os.makedirs(home_user2)
            os.makedirs(home_ff2)
            os.makedirs(work_dir2)

            # Write preferences.json for this temp dir
            with open(os.path.join(home_user2, "preferences.json"), "w", encoding="utf-8") as f:
                json.dump(PREFS, f)

            tool_py3 = os.path.join(work_dir2, "tool3.py")
            payload = {"tool_name": "Write", "tool_input": {"file_path": tool_py3, "content": TOOL_30_LINES}}
            code, stdout = run_hook(home_user2, home_ff2, work_dir2, payload, active=False)
            decision = get_decision(stdout)
            expected = "allow"
            passed_decision = decision == expected
            passed_audit = audit_has_label(home_ff2, "disarmed")
            passed = passed_decision and passed_audit
            if not passed:
                all_pass = False
            results.append(("e", f"decision={expected}/audit=disarmed", f"decision={decision}/audit={'disarmed' if passed_audit else 'missing'}", passed))

    # Print results
    for case, expected, got, passed in results:
        status = "PASS" if passed else "FAIL"
        print(f"{status} case {case}: expected {expected} | got {got}")

    return all_pass


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)