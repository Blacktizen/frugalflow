#!/usr/bin/env python3
"""
End-to-end audit guarantee tests for guard_hook.py.
Tests the audit log behavior across different modes and conditions.
"""

import os
import sys
import json
import tempfile
import shutil
import subprocess
import hashlib
import datetime


def _compute_paths():
    """Compute BIN and HOOK paths relative to this file."""
    here = os.path.dirname(os.path.abspath(__file__))
    # File is at public/tests/, so parent is public/
    repo_root = os.path.dirname(here)
    bin_dir = os.path.join(repo_root, "bin")
    hook_path = os.path.join(bin_dir, "guard_hook.py")
    return bin_dir, hook_path


BIN, HOOK = _compute_paths()

# Constants used across test cases
BIG_CONTENT = "a\nb\nc\nd\n"
RECEIPT_LINE = {
    "time": datetime.datetime.now().astimezone().isoformat(),
    "status": "success",
    "model_answered": "m",
    "target": "/w/a.py",
    "sha256": hashlib.sha256(BIG_CONTENT.encode("utf-8")).hexdigest(),
}


def _make_env(home):
    """Build subprocess environment: copy os.environ, strip GIT_* and FRUGALFLOW_*, add FRUGALFLOW_HOME and PYTHONDONTWRITEBYTECODE."""
    env = dict(os.environ)
    for key in list(env.keys()):
        if key.startswith("GIT_") or key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY"):
            env.pop(key, None)
    env["FRUGALFLOW_HOME"] = home
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def _write_settings(home, audit_log_path, mode="active"):
    """Write guard.json and preferences.json for a test case."""
    guard_settings = {
        "code_extensions": [".py"],
        "line_threshold": 3,
        "receipt_minutes": 60,
        "delegate_tools": [],
        "fix_hint": "delegate it.",
        "delegation_logs": ["delegations.jsonl"],
        "audit_log": audit_log_path,
    }
    prefs = {
        "schema_version": "1",
        "switch": {"enabled": True, "mode": mode},
    }
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(guard_settings, f)
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f)


def _write_delegations(home):
    """Write delegations.jsonl with the standard receipt line."""
    with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write(json.dumps(RECEIPT_LINE) + "\n")


def _create_readonly_dir(home):
    """Create a read-only directory 'ro' under home and verify it's truly read-only."""
    ro_dir = os.path.join(home, "ro")
    os.makedirs(ro_dir, exist_ok=True)
    os.chmod(ro_dir, 0o555)
    # Verify write fails
    test_file = os.path.join(ro_dir, "probe.txt")
    try:
        with open(test_file, "w") as f:
            f.write("test")
        # If we get here, write succeeded - this is a FAIL condition
        os.remove(test_file)
        return False, "setup: read-only folder is writable"
    except OSError:
        return True, None


def _count_audit_lines(home, audit_log_path):
    """Count non-empty lines in the audit log file."""
    audit_path = os.path.join(home, audit_log_path)
    if not os.path.exists(audit_path):
        return 0
    count = 0
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                count += 1
    return count


def _read_audit_lines(home, audit_log_path):
    """Read all non-empty JSON lines from the audit log."""
    audit_path = os.path.join(home, audit_log_path)
    if not os.path.exists(audit_path):
        return []
    lines = []
    with open(audit_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                lines.append(json.loads(line))
    return lines


def _run_hook(home, tool_call_json):
    """Run the guard hook subprocess with the given tool call JSON."""
    env = _make_env(home)
    proc = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=tool_call_json,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout, proc.stderr


def _cleanup_home(home):
    """Clean up temp directory, fixing permissions on read-only dirs first."""
    # Fix permissions on any read-only directories before removal
    for root, dirs, files in os.walk(home, topdown=False):
        for d in dirs:
            path = os.path.join(root, d)
            try:
                os.chmod(path, 0o755)
            except OSError:
                pass
        for f in files:
            path = os.path.join(root, f)
            try:
                os.chmod(path, 0o644)
            except OSError:
                pass
    try:
        os.chmod(home, 0o755)
    except OSError:
        pass
    shutil.rmtree(home, ignore_errors=True)


def _check_case_a():
    """Case (a): active mode, audit log unreadable, code write with receipt."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        # Create read-only ro/ directory
        ok, reason = _create_readonly_dir(home)
        if not ok:
            return False, f"FAIL case (a): {reason}"

        # Write settings with audit_log = "ro/audit.jsonl"
        _write_settings(home, "ro/audit.jsonl", mode="active")
        _write_delegations(home)

        # Tool call: Write to /w/a.py with BIG_CONTENT
        tool_call = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/w/a.py", "content": BIG_CONTENT}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        # Expected: exit code 0, stdout contains JSON with permissionDecision="deny",
        # reason contains "audit" and "To fix:"
        if code != 0:
            return False, f"FAIL case (a): expected exit code 0, got {code}"

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return False, f"FAIL case (a): stdout is not valid JSON: {stdout!r}"

        hook_output = output.get("hookSpecificOutput", {})
        decision = hook_output.get("permissionDecision")
        reason = hook_output.get("permissionDecisionReason", "")

        if decision != "deny":
            return False, f"FAIL case (a): expected permissionDecision='deny', got {decision!r}"

        if "audit" not in reason.lower():
            return False, f"FAIL case (a): reason missing 'audit': {reason!r}"

        if "To fix:" not in reason:
            return False, f"FAIL case (a): reason missing 'To fix:': {reason!r}"

        return True, "PASS case (a): active, unreadable audit log, code write with receipt -> deny with audit reason"

    finally:
        _cleanup_home(home)


def _check_case_b():
    """Case (b): observe mode, audit log unreadable, same call as (a)."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        ok, reason = _create_readonly_dir(home)
        if not ok:
            return False, f"FAIL case (b): {reason}"

        _write_settings(home, "ro/audit.jsonl", mode="observe")
        _write_delegations(home)

        tool_call = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/w/a.py", "content": BIG_CONTENT}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        if code != 0:
            return False, f"FAIL case (b): expected exit code 0, got {code}"

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return False, f"FAIL case (b): stdout is not valid JSON: {stdout!r}"

        # In observe mode, no "deny" permissionDecision; should have systemMessage with "audit"
        hook_output = output.get("hookSpecificOutput", {})
        decision = hook_output.get("permissionDecision")
        if decision == "deny":
            return False, f"FAIL case (b): unexpected permissionDecision='deny' in observe mode"

        system_msg = output.get("systemMessage", "")
        if "audit" not in system_msg.lower():
            return False, f"FAIL case (b): systemMessage missing 'audit': {system_msg!r}"

        return True, "PASS case (b): observe, unreadable audit log, code write with receipt -> systemMessage with audit"

    finally:
        _cleanup_home(home)


def _check_case_c():
    """Case (c): active mode, audit log writable, free write (non-code file)."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        _write_settings(home, "audit.jsonl", mode="active")
        _write_delegations(home)

        # Count audit lines before
        before_count = _count_audit_lines(home, "audit.jsonl")

        tool_call = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/w/notes.md", "content": "one line\n"}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        if code != 0:
            return False, f"FAIL case (c): expected exit code 0, got {code}"

        # Count audit lines after
        after_count = _count_audit_lines(home, "audit.jsonl")

        if after_count != before_count + 1:
            return False, f"FAIL case (c): expected audit lines to increase by 1 (before={before_count}, after={after_count})"

        # Verify the new audit line has tool="Write" and decision="allow"
        audit_lines = _read_audit_lines(home, "audit.jsonl")
        last_line = audit_lines[-1]
        if last_line.get("tool") != "Write":
            return False, f"FAIL case (c): expected tool='Write', got {last_line.get('tool')!r}"
        if last_line.get("decision") != "allow":
            return False, f"FAIL case (c): expected decision='allow', got {last_line.get('decision')!r}"

        return True, "PASS case (c): active, writable audit log, non-code write -> audit line with tool=Write decision=allow"

    finally:
        _cleanup_home(home)


def _check_case_d():
    """Case (d): active mode, pure read (Read tool)."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        _write_settings(home, "audit.jsonl", mode="active")
        _write_delegations(home)

        # Count audit lines before
        before_count = _count_audit_lines(home, "audit.jsonl")

        tool_call = json.dumps({
            "tool_name": "Read",
            "tool_input": {"file_path": "/w/notes.md"}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        if code != 0:
            return False, f"FAIL case (d): expected exit code 0, got {code}"

        # Count audit lines after
        after_count = _count_audit_lines(home, "audit.jsonl")

        if after_count != before_count:
            return False, f"FAIL case (d): expected audit lines unchanged (before={before_count}, after={after_count})"

        return True, "PASS case (d): active, pure Read -> no audit log created/changed"

    finally:
        _cleanup_home(home)


def _check_case_e():
    """Case (e): active mode, audit log unreadable, free write (non-code file)."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        ok, reason = _create_readonly_dir(home)
        if not ok:
            return False, f"FAIL case (e): {reason}"

        _write_settings(home, "ro/audit.jsonl", mode="active")
        _write_delegations(home)

        tool_call = json.dumps({
            "tool_name": "Write",
            "tool_input": {"file_path": "/w/notes.md", "content": "one line\n"}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        if code != 0:
            return False, f"FAIL case (e): expected exit code 0, got {code}"

        try:
            output = json.loads(stdout)
        except json.JSONDecodeError:
            return False, f"FAIL case (e): stdout is not valid JSON: {stdout!r}"

        hook_output = output.get("hookSpecificOutput", {})
        decision = hook_output.get("permissionDecision")
        reason = hook_output.get("permissionDecisionReason", "")

        if decision != "deny":
            return False, f"FAIL case (e): expected permissionDecision='deny', got {decision!r}"

        if "audit" not in reason.lower():
            return False, f"FAIL case (e): reason missing 'audit': {reason!r}"

        return True, "PASS case (e): active, unreadable audit log, non-code write -> deny with audit reason"

    finally:
        _cleanup_home(home)


def _check_case_f():
    """Case (f): observe mode, Bash write (tee) with no receipt -> observed:shell_write audit, allow."""
    home = tempfile.mkdtemp(dir="/tmp")
    try:
        _write_settings(home, "audit.jsonl", mode="observe")
        # Write delegations.jsonl without a receipt for /w/a.py
        with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
            f.write("")  # empty, no receipt

        tool_call = json.dumps({
            "tool_name": "Bash",
            "tool_input": {"command": "tee /w/a.py"}
        })

        code, stdout, stderr = _run_hook(home, tool_call)

        if code != 0:
            return False, f"FAIL case (f): expected exit code 0, got {code}"

        # No permissionDecision deny in stdout
        if "permissionDecision" in stdout and "deny" in stdout:
            return False, f"FAIL case (f): unexpected deny in stdout: {stdout!r}"

        # Check audit log has at least one line with audit starting with "observed:shell_write"
        audit_lines = _read_audit_lines(home, "audit.jsonl")
        found = False
        for line in audit_lines:
            audit_val = line.get("audit", "")
            if audit_val.startswith("observed:shell_write"):
                found = True
                break

        if not found:
            return False, f"FAIL case (f): no audit line with 'observed:shell_write' prefix, audit_lines={audit_lines}"

        return True, "PASS case (f): observe, Bash write no receipt -> audit observed:shell_write, allow"

    finally:
        _cleanup_home(home)


def main():
    """Run all 6 test cases and report results."""
    cases = [
        ("(a) active, unreadable audit, code write with receipt", _check_case_a),
        ("(b) observe, unreadable audit, code write with receipt", _check_case_b),
        ("(c) active, writable audit, non-code write", _check_case_c),
        ("(d) active, pure Read", _check_case_d),
        ("(e) active, unreadable audit, non-code write", _check_case_e),
        ("(f) observe, Bash write no receipt", _check_case_f),
    ]

    all_passed = True
    for name, check_fn in cases:
        passed, message = check_fn()
        if passed:
            print(f"PASS {name}")
        else:
            print(f"FAIL {name}: {message}")
            all_passed = False

    sys.exit(0 if all_passed else 1)


if __name__ == "__main__":
    main()
