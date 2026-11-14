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


def run_r1_guard_hook(payload, env):
    """Run r1_guard.py in Stop hook mode and return (returncode, stdout)."""
    proc = subprocess.run(
        [sys.executable, R1_GUARD],
        input=json.dumps(payload),
        capture_output=True, text=True, env=env
    )
    return proc.returncode, proc.stdout.strip()


def write_prefs(home, enabled, mode):
    """Write the switch where the guard reads it: FRUGALFLOW_HOME/preferences.json."""
    os.makedirs(home, exist_ok=True)
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps({"switch": {"enabled": enabled, "mode": mode}}))


def make_before_fixed_ts(ident, command, cwd, ts):
    return {
        "ts": ts,
        "cwd": cwd,
        "event": "tool_before",
        "tool": "Bash",
        "id": ident,
        "input": json.dumps({"command": command})
    }


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

        # ==================== SCENARIO 3 (C6): Fake APPENDED output without touching log.md ====================
        session_s3 = "s3"

        # Add git commit gesture
        session_log.append(session_s3, make_before("g3", "git commit -m fix", tmp))
        session_log.append(session_s3, make_after("g3", '{"stdout": "[main 1234567] fix"}'))

        # Create a vault with an OLD entry "old-title" dated long ago
        old_vault = os.path.join(tmp, "old_vault")
        os.makedirs(os.path.join(old_vault, "vault"))
        genesis = chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
        old_entry = chain_rules.render(
            chain_rules.entry_hash(chain_rules.GENESIS, genesis.split("<!--")[0]),
            "2020-01-01 12:00", "old-title", [("Decision", "old")]
        )
        with open(os.path.join(old_vault, "vault", "log.md"), "w") as f:
            f.write("# Log\n\n" + genesis + "\n" + old_entry)
        # Fix mtime to 2000-01-01 for a clean test
        old_time = datetime.datetime(2000, 1, 1, 0, 0, 0).timestamp()
        os.utime(os.path.join(old_vault, "vault", "log.md"), (old_time, old_time))

        # Add a FAKE journal_add-like call whose output announces APPENDED but doesn't touch the file
        fake_journal_cmd = f"python3 {JOURNAL_ADD} --vault {os.path.join(old_vault, 'vault')} --title t3 --field Decision=d"
        session_log.append(session_s3, make_before("j3", fake_journal_cmd, tmp))
        session_log.append(session_s3, make_after("j3", "APPENDED entry 1 to log.md"))

        # Run r1_guard --session s3: expected code 6 (R1 MISSING) because the entry didn't actually land
        rc_guard, out_guard = run_r1_guard_session(session_s3, env)
        if rc_guard == 6 and "R1 MISSING" in out_guard:
            results.append(("PASS", "scenario3 C6 fake appended output rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario3 C6 fake appended output rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 4 (C6): Real journal_add but last entry is NOT the called title ====================
        session_s4 = "s4"

        # Add git commit gesture
        session_log.append(session_s4, make_before("g4", "git commit -m fix", tmp))
        session_log.append(session_s4, make_after("g4", '{"stdout": "[main 1234567] fix"}'))

        # Create a fresh vault
        s4_vault = os.path.join(tmp, "s4_vault")
        os.makedirs(os.path.join(s4_vault, "vault"))
        genesis2 = chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
        with open(os.path.join(s4_vault, "vault", "log.md"), "w") as f:
            f.write("# Log\n\n" + genesis2)

        # Run REAL journal_add.py for title t4
        rc, out = run_journal_add(os.path.join(s4_vault, "vault"), "t4", "Decision=d", env)

        journal_cmd4 = f"python3 {JOURNAL_ADD} --vault {os.path.join(s4_vault, 'vault')} --title t4 --field Decision=d"
        session_log.append(session_s4, make_before("j4", journal_cmd4, tmp))
        session_log.append(session_s4, make_after("j4", out))

        # NOW manually add another entry "other" dated AFTER the journal_add call
        # We need to append directly to the log.md
        with open(os.path.join(s4_vault, "vault", "log.md"), "r") as f:
            current_log = f.read()
        last_hash = chain_rules.last_hash(current_log)
        other_entry = chain_rules.render(last_hash, "2026-09-26 11:00", "other", [("Decision", "other")])
        with open(os.path.join(s4_vault, "vault", "log.md"), "a") as f:
            f.write("\n" + other_entry)

        # Run r1_guard --session s4: expected code 6 because the LAST entry is "other", not "t4"
        rc_guard, out_guard = run_r1_guard_session(session_s4, env)
        if rc_guard == 6 and "R1 MISSING" in out_guard:
            results.append(("PASS", "scenario4 C6 last entry not t4 rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario4 C6 last entry not t4 rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 5 (C16): Three sessions with git global options, no journal ====================
        # Scenario 5a: git -c commit.gpgsign=false commit -m fix
        session_s5a = "s5a"
        session_log.append(session_s5a, make_before("g5a", "git -c commit.gpgsign=false commit -m fix", tmp))
        session_log.append(session_s5a, make_after("g5a", '{"stdout": "[main 1234567] fix"}'))
        rc_guard, out_guard = run_r1_guard_session(session_s5a, env)
        if rc_guard == 6 and "R1 MISSING" in out_guard:
            results.append(("PASS", "scenario5a git -c commit.gpgsign=false commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario5a git -c commit.gpgsign=false commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))

        # Scenario 5b: git --no-pager commit -m fix
        session_s5b = "s5b"
        session_log.append(session_s5b, make_before("g5b", "git --no-pager commit -m fix", tmp))
        session_log.append(session_s5b, make_after("g5b", '{"stdout": "[main 1234567] fix"}'))
        rc_guard, out_guard = run_r1_guard_session(session_s5b, env)
        if rc_guard == 6 and "R1 MISSING" in out_guard:
            results.append(("PASS", "scenario5b git --no-pager commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario5b git --no-pager commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))

        # Scenario 5c: git -C a -C b commit -m fix
        session_s5c = "s5c"
        session_log.append(session_s5c, make_before("g5c", "git -C a -C b commit -m fix", tmp))
        session_log.append(session_s5c, make_after("g5c", '{"stdout": "[main 1234567] fix"}'))
        rc_guard, out_guard = run_r1_guard_session(session_s5c, env)
        if rc_guard == 6 and "R1 MISSING" in out_guard:
            results.append(("PASS", "scenario5c git -C a -C b commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario5c git -C a -C b commit rc=6", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 6 (witness): git -c commit.gpgsign=false commit + REAL journal_add ====================
        session_s6 = "s6"

        # Add git commit gesture with global option
        session_log.append(session_s6, make_before("g6", "git -c commit.gpgsign=false commit -m fix", tmp))
        session_log.append(session_s6, make_after("g6", '{"stdout": "[main 1234567] fix"}'))

        # Run REAL journal_add.py to VALID vault
        rc, out = run_journal_add(os.path.join(valid_vault, "vault"), "t6", "Decision=d", env)

        journal_cmd6 = f"python3 {JOURNAL_ADD} --vault {os.path.join(valid_vault, 'vault')} --title t6 --field Decision=d"
        session_log.append(session_s6, make_before("j6", journal_cmd6, tmp))
        session_log.append(session_s6, make_after("j6", out))

        # Run r1_guard --session s6: expected code 0 and "R1 OK s6"
        rc_guard, out_guard = run_r1_guard_session(session_s6, env)
        if rc_guard == 0 and out_guard.startswith("R1 OK s6"):
            results.append(("PASS", "scenario6 witness git -c commit + real journal_add rc=0 R1 OK", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario6 witness git -c commit + real journal_add rc=0 R1 OK", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 7 (observe): hook mode blocks nothing, vault present ====================
        session_s7 = "s7"
        proj7 = os.path.join(tmp, "proj7")
        os.makedirs(os.path.join(proj7, "vault"), exist_ok=True)
        env7 = dict(env)
        env7["FRUGALFLOW_HOME"] = os.path.join(tmp, "home7")
        write_prefs(env7["FRUGALFLOW_HOME"], True, "observe")

        session_log.append(session_s7, make_before("g7", "git commit -m fix", proj7))
        session_log.append(session_s7, make_after("g7", '{"stdout": "[main 1234567] fix"}'))

        rc_guard, out_guard = run_r1_guard_hook({"session_id": session_s7, "cwd": proj7}, env7)
        if rc_guard == 0 and "decision" not in out_guard and "block" not in out_guard:
            results.append(("PASS", "scenario7 observe hook rc=0 no block (vault present)", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario7 observe hook rc=0 no block (vault present)", f"got rc={rc_guard} out={out_guard[:60]}"))

        # ==================== SCENARIO 8 (no vault): hook mode blocks nothing, switch active ====================
        session_s8 = "s8"
        proj8 = os.path.join(tmp, "proj8")
        os.makedirs(proj8, exist_ok=True)
        env8 = dict(env)
        env8["FRUGALFLOW_HOME"] = os.path.join(tmp, "home8")
        write_prefs(env8["FRUGALFLOW_HOME"], True, "active")

        session_log.append(session_s8, make_before("g8", "git commit -m fix", proj8))
        session_log.append(session_s8, make_after("g8", '{"stdout": "[main 1234567] fix"}'))

        rc_guard, out_guard = run_r1_guard_hook({"session_id": session_s8, "cwd": proj8}, env8)
        if rc_guard == 0 and "decision" not in out_guard and "block" not in out_guard:
            results.append(("PASS", "scenario8 active hook rc=0 no block (no vault)", f"got rc={rc_guard} out={out_guard[:60]}"))
        else:
            results.append(("FAIL", "scenario8 active hook rc=0 no block (no vault)", f"got rc={rc_guard} out={out_guard[:60]}"))

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