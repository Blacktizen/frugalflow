#!/usr/bin/env python3
# e2e_code_guard_disarm.py - C11 (the guard's own code is protected) and C12
# (FRUGALFLOW_GUARD=0 disarms only when guard.json allows it).
# Each case prints one PASS or FAIL line; exit 1 if any case fails.

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
HOOK = os.path.join(BIN, "guard_hook.py")

GUARD_BASE = {
    "code_extensions": [".py", ".sh", ".js", ".ts", ".ipynb"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "delegate_tools": ["delegate.py"],
    "fix_hint": "delegate it.",
}

# 2026-11-12: the code-receipt rule lives in orchestrator mode.
PREFS = {"schema_version": "1", "switch": {"enabled": True, "mode": "orchestrator"}}

BIG_PY = "\n".join("x%d = %d" % (i, i) for i in range(60)) + "\n"


def run_hook(home_ff, home_user, work, payload, guard_extra=None, env_extra=None):
    guard = dict(GUARD_BASE)
    if guard_extra:
        guard.update(guard_extra)
    with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(guard, f)
    with open(os.path.join(home_ff, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    with open(os.path.join(home_user, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    open(os.path.join(home_ff, "delegations.jsonl"), "w", encoding="utf-8").close()
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "FRUGALFLOW_HOME": home_ff,
        "HOME": home_user,
    }
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=30,
    )
    return r.returncode, r.stdout.strip()


def decision(stdout):
    if not stdout:
        return "allow"
    try:
        d = json.loads(stdout.splitlines()[-1])
        return d.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return "unreadable"


def main():
    tmp = tempfile.mkdtemp(prefix="e2e-code-guard-")
    failures = 0
    try:
        home_ff = os.path.join(tmp, "ff")
        home_user = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        for d in (home_ff, home_user, work):
            os.makedirs(d)
        disarm = {"FRUGALFLOW_GUARD": "0"}
        cases = []

        # C12: the environment switch alone must not disarm the guard.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write", "tool_input": {"file_path": os.path.join(work, "big.py"), "content": BIG_PY}},
                          env_extra=disarm)
        cases.append(("C12 FRUGALFLOW_GUARD=0 without allow_env_disarm refuses a 60-line .py", decision(out), "deny"))

        # Control: the same environment switch, explicitly allowed in guard.json, disarms.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write", "tool_input": {"file_path": os.path.join(work, "big.py"), "content": BIG_PY}},
                          guard_extra={"allow_env_disarm": True}, env_extra=disarm)
        cases.append(("OK FRUGALFLOW_GUARD=0 with allow_env_disarm true allows (disarmed)", decision(out), "allow"))

        # C11: the installed guard code is in the protected zone (one-line write, active mode).
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write", "tool_input": {"file_path": os.path.join(BIN, "journal_guard.py"), "content": "x"}})
        cases.append(("C11 Write of one line to bin/journal_guard.py refuses in active mode", decision(out), "deny"))

        # C11: a one-line Edit of the guard code is refused too.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(BIN, "guard_hook.py"),
                                                              "old_string": "return paths", "new_string": "return []"}})
        cases.append(("C11 one-line Edit of bin/guard_hook.py refuses in active mode", decision(out), "deny"))

        # Control: an ordinary small file in the work folder is allowed.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write", "tool_input": {"file_path": os.path.join(work, "s.py"), "content": "a = 1\n"}})
        cases.append(("OK Write of a small .py in the work folder allows", decision(out), "allow"))

        for name, got, want in cases:
            ok = got == want
            if not ok:
                failures += 1
            print("%s  %s  (expected %s, got %s)" % ("PASS" if ok else "FAIL", name, want, got))
        print("SUMMARY %d / %d" % (len(cases) - failures, len(cases)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())