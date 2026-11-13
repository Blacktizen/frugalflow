#!/usr/bin/env python3
# e2e_orchestrator_mode.py - the code-receipt rule lives in orchestrator mode:
# active/silent/observe allow a big code write with the audit label
# receipt_not_required; orchestrator refuses it without a receipt.

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
HOOK = os.path.join(BIN, "guard_hook.py")
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")

GUARD = {
    "code_extensions": [".py", ".sh", ".js", ".ts"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "delegate_tools": ["delegate.py"],
    "fix_hint": "delegate it.",
}

BIG_PY = "\n".join("x%d = %d" % (i, i) for i in range(40)) + "\n"

USAGE = "usage: e2e_orchestrator_mode.py [--notice]\n"

NOTICE = (
    "NAME      e2e_orchestrator_mode.py - end-to-end test of the orchestrator mode: outside it a big code write passes with the audit label receipt_not_required, inside it the write needs a delegation receipt.\n"
    "READS     ../bin/guard_hook.py, ../bin/frugalflow.py, ../config/guard.example.json.\n"
    "WRITES    temporary folders only, removed after each case; one PASS or FAIL line per case, then a summary. Exit 0 all pass, 1 a case failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_orchestrator_mode.py\n"
    "PITFALLS  2026-11-12 the receipt rule moved out of the default mode: a test that expects a receipt refusal must set switch.mode to orchestrator.\n"
)


def setup_home(home, mode):
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(GUARD, f)
    with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write("")
    prefs = {
        "schema_version": "1",
        "switch": {"enabled": True, "mode": mode},
        "verbosity": {"final_answer_words": 120, "step_message_words": 30},
        "ceilings": {"max_trust": "private", "max_tries": 3, "max_output_tokens": 16000},
        "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
        "grouping": {"independent_calls_same_turn": True},
    }
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f)


def run_hook(home, work, tool_name, tool_input):
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    env = {
        "PATH": "/usr/bin:/bin",
        "HOME": work,
        "FRUGALFLOW_HOME": home,
    }
    r = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=30,
    )
    decision = "allow"
    reason = ""
    if r.stdout.strip():
        try:
            d = json.loads(r.stdout.strip().splitlines()[-1])
            decision = d["hookSpecificOutput"]["permissionDecision"]
            reason = d["hookSpecificOutput"]["permissionDecisionReason"]
        except Exception:
            decision = "unreadable"
    return decision, reason


def read_audit(home):
    path = os.path.join(home, "audit.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line)["audit"])
                except Exception:
                    pass
    return out


def run_frugalflow(home, work, *args):
    env = {"PATH": "/usr/bin:/bin", "HOME": work}
    return subprocess.run(
        [sys.executable, FRUGALFLOW] + list(args) + ["--home", home],
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=30,
    )


def main():
    failures = 0
    check_num = 0

    def check(num, ok, desc, got):
        nonlocal failures
        if ok:
            print(f"PASS {num} {desc}: {got}")
        else:
            print(f"FAIL {num} {desc}: {got}")
            failures += 1

    tmp = tempfile.mkdtemp(prefix="e2e-orch-")
    try:
        # Case 1: active mode, 40-line .py without receipt -> allow, audit
        # keeps the trace with the label receipt_not_required.
        check_num += 1
        home = os.path.join(tmp, "h1")
        work = os.path.join(tmp, "w1")
        os.makedirs(home)
        os.makedirs(work)
        setup_home(home, "active")
        decision, reason = run_hook(home, work, "Write",
                                    {"file_path": os.path.join(work, "big.py"), "content": BIG_PY})
        audit = read_audit(home)
        ok = decision == "allow" and audit and audit[-1] == "receipt_not_required"
        check(check_num, ok, "active: 40-line .py without receipt allows",
              f"decision {decision}, audit {audit[-1] if audit else None}")

        # Case 2: orchestrator mode, the same write -> deny, reason names a receipt.
        check_num += 1
        home = os.path.join(tmp, "h2")
        work = os.path.join(tmp, "w2")
        os.makedirs(home)
        os.makedirs(work)
        setup_home(home, "orchestrator")
        decision, reason = run_hook(home, work, "Write",
                                    {"file_path": os.path.join(work, "big.py"), "content": BIG_PY})
        ok = decision == "deny" and "receipt" in reason.lower()
        check(check_num, ok, "orchestrator: 40-line .py without receipt denies",
              f"decision {decision}, reason {reason[:60]!r}")

        # Case 3: active mode still refuses a write into FRUGALFLOW_HOME/guard.json.
        check_num += 1
        home = os.path.join(tmp, "h3")
        work = os.path.join(tmp, "w3")
        os.makedirs(home)
        os.makedirs(work)
        setup_home(home, "active")
        decision, reason = run_hook(home, work, "Write",
                                    {"file_path": os.path.join(home, "guard.json"), "content": "{}\n"})
        check(check_num, decision == "deny", "active: write into home/guard.json denies",
              f"decision {decision}")

        # Case 4: frugalflow mode orchestrator exits 0 and records the mode.
        check_num += 1
        home = os.path.join(tmp, "h4")
        work = os.path.join(tmp, "w4")
        os.makedirs(home)
        os.makedirs(work)
        setup_home(home, "active")
        r = run_frugalflow(home, work, "mode", "orchestrator")
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            mode = json.load(f)["switch"]["mode"]
        check(check_num, r.returncode == 0 and mode == "orchestrator",
              "frugalflow mode orchestrator exits 0",
              f"code {r.returncode}, mode {mode}")

        # Case 5: frugalflow mode bogus exits nonzero and keeps the old mode.
        check_num += 1
        r = run_frugalflow(home, work, "mode", "bogus")
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            mode = json.load(f)["switch"]["mode"]
        check(check_num, r.returncode != 0 and mode == "orchestrator",
              "frugalflow mode bogus exits nonzero",
              f"code {r.returncode}, mode {mode}")
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failures == 0:
        print(f"E2E ORCHESTRATOR MODE OK ({check_num} checks)")
        return 0
    print(f"E2E ORCHESTRATOR MODE FAILED ({failures} of {check_num})")
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main())
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
