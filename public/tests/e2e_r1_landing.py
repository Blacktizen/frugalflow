#!/usr/bin/env python3
"""End-to-end test for r1_guard landing behavior.

This test verifies that r1_guard only clears the missing-log list when
journal_add.py actually succeeds (exit 0 AND entry appended).
"""

import os
import sys
import json
import tempfile
import shutil
import subprocess
import datetime

# Determine repo root from FF_ROOT env var or from this file's location
if "FF_ROOT" in os.environ:
    REPO_ROOT = os.environ["FF_ROOT"]
else:
    # This file is at public/tests/e2e_r1_landing.py, so repo root is parent of public/
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BIN_DIR = os.path.join(REPO_ROOT, "public", "bin")
R1_GUARD = os.path.join(BIN_DIR, "r1_guard.py")
JOURNAL_ADD = os.path.join(BIN_DIR, "journal_add.py")
SESSION_LOG = os.path.join(BIN_DIR, "session_log.py")

# Add bin directory to path for chain_rules and session_log imports
sys.path.insert(0, BIN_DIR)
import session_log
import chain_rules


def run_journal_add(vault, title, field, env):
    """Run journal_add.py and return (returncode, stdout)."""
    proc = subprocess.run(
        [sys.executable, JOURNAL_ADD, "--vault", vault, "--title", title, "--field", field],
        capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout.strip()


def make_before(ident, command, cwd):
    return {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "cwd": cwd,
        "event": "tool_before",
        "tool": "Bash",
        "id": ident,
        "input": json.dumps({"command": command})
    }


def make_after(ident, response=""):
    entry = {"event": "tool_after", "tool": "Bash", "id": ident}
    if response:
        entry["response"] = response
    return entry


def run_r1_guard_session(session, env):
    """Run r1_guard.py --session <session> and return (returncode, stdout)."""
    proc = subprocess.run(
        [sys.executable, R1_GUARD, "--session", session],
        capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout.strip()


def main():
    # Create temp directory for the test
    tmp = tempfile.mkdtemp()
    sessions_dir = os.path.join(tmp, "sessions")
    anchors_dir = os.path.join(tmp, "anchors")
    os.makedirs(sessions_dir, exist_ok=True)
    os.makedirs(anchors_dir, exist_ok=True)

    # Set environment variables in os.environ so session_log uses them
    os.environ["FRUGALFLOW_SESSIONS"] = sessions_dir
    os.environ["FRUGALFLOW_ANCHORS"] = anchors_dir

    env = dict(os.environ)

    results = []

    try:
        # Create a valid vault with a genesis entry
        valid_vault = os.path.join(tmp, "vault")
        os.makedirs(os.path.join(valid_vault, "vault"))
        # Write a genesis entry to log.md
        genesis_entry = chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
        with open(os.path.join(valid_vault, "vault", "log.md"), "w") as f:
            f.write("# Log\n\n" + genesis_entry)

        # ==================== SCENARIO 1: journal_add to ABSENT vault (should FAIL) ====================
        session_s1 = "s1"

        # Add git commit gesture using session_log.append
        session_log.append(session_s1, make_before("g1", "git commit -m fix", tmp))
        session_log.append(session_s1, make_after("g1", '{"stdout": "[main 1234567] fix"}'))

        # Run journal_add to ABSENT vault (doesn't exist)
        absent_vault = os.path.join(tmp, "absent_vault")
        rc, out = run_journal_add(absent_vault, "t1", "Decision=d", env)

        # Add journal_add tool_before and tool_after with REAL output
        journal_cmd = f"python3 {JOURNAL_ADD} --vault {absent_vault} --title t1 --field Decision=d"
        session_log.append(session_s1, make_before("j1", journal_cmd, tmp))
        session_log.append(session_s1, make_after("j1", out))

        # Run r1_guard --session s1: expected code 6 (R1 MISSING)
        rc_guard, out_guard = run_r1_guard_session(session_s1, env)
        expected_rc = 6
        if rc_guard == expected_rc and "R1 MISSING" in out_guard:
            results.append(("PASS", f"scenario1 absent_vault rc={expected_rc}", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", f"scenario1 absent_vault rc={expected_rc}", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 2: journal_add to VALID vault (should SUCCEED) ====================
        session_s2 = "s2"

        # Add git commit gesture using session_log.append
        session_log.append(session_s2, make_before("g2", "git commit -m fix", tmp))
        session_log.append(session_s2, make_after("g2", '{"stdout": "[main 1234567] fix"}'))

        # Run journal_add to VALID vault
        rc, out = run_journal_add(os.path.join(valid_vault, "vault"), "t2", "Decision=d", env)

        # Add journal_add tool_before and tool_after with REAL output
        journal_cmd2 = f"python3 {JOURNAL_ADD} --vault {os.path.join(valid_vault, 'vault')} --title t2 --field Decision=d"
        session_log.append(session_s2, make_before("j2", journal_cmd2, tmp))
        session_log.append(session_s2, make_after("j2", out))

        # Run r1_guard --session s2: expected code 0 and output starting with "R1 OK s2"
        rc_guard, out_guard = run_r1_guard_session(session_s2, env)
        expected_rc2 = 0
        if rc_guard == expected_rc2 and out_guard.startswith("R1 OK s2"):
            results.append(("PASS", f"scenario2 valid_vault rc={expected_rc2} R1 OK", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", f"scenario2 valid_vault rc={expected_rc2} R1 OK", f"got rc={rc_guard} out={out_guard[:60]}"))

    finally:
        # Print results
        all_pass = True
        for status, expected, got in results:
            print(f"{status} {expected} [{got}]")
            if status == "FAIL":
                all_pass = False

        # Cleanup
        shutil.rmtree(tmp, ignore_errors=True)

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()