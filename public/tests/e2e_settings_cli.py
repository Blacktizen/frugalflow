#!/usr/bin/env python3
"""E2E test for settings CLI guard and CLAUDECODE TTY check."""

import json
import os
import subprocess
import sys
import tempfile
import shutil

_THROWAWAY_HOME = None


def throwaway_home():
    """Create (once) a throwaway HOME under /tmp, distinct from the real user home."""
    global _THROWAWAY_HOME
    if _THROWAWAY_HOME is None:
        _THROWAWAY_HOME = tempfile.mkdtemp(prefix="e2e_settings_cli_home_", dir="/tmp")
    return _THROWAWAY_HOME


def run_guard_check(command, home=None):
    """Run settings_cli_guard.py --check on a command."""
    env = os.environ.copy()
    env["HOME"] = throwaway_home()
    env.pop("CLAUDECODE", None)
    if home:
        env["FRUGALFLOW_HOME"] = home
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(script_dir, "..", "bin")
    env["PYTHONPATH"] = bin_dir + (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else bin_dir
    proc = subprocess.run(
        [sys.executable, os.path.join(bin_dir, "settings_cli_guard.py"), "--check", command],
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.returncode, proc.stdout.strip()


def run_frugalflow(args, home=None, env_extra=None, stdin_data=None):
    """Run frugalflow.py with given args and environment."""
    env = os.environ.copy()
    env["HOME"] = throwaway_home()
    # Drop CLAUDECODE unless the test itself sets it via env_extra below.
    env.pop("CLAUDECODE", None)
    if home:
        env["FRUGALFLOW_HOME"] = home
    if env_extra:
        env.update(env_extra)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(script_dir, "..", "bin")
    env["PYTHONPATH"] = bin_dir + (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else bin_dir
    proc = subprocess.run(
        [sys.executable, os.path.join(bin_dir, "frugalflow.py")] + args,
        capture_output=True,
        text=True,
        env=env,
        input=stdin_data,
    )
    return proc.returncode, proc.stdout, proc.stderr


def setup_home(home, mode="active"):
    """Create minimal FrugalFlow home with preferences and guard.json."""
    os.makedirs(home, exist_ok=True)
    # preferences.json
    prefs = {
        "schema_version": "1",
        "verbosity": {"final_answer_words": 120, "step_message_words": 30},
        "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 50000},
        "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
        "grouping": {"independent_calls_same_turn": True},
        "switch": {"enabled": True, "mode": mode},
        "display": {"statusline": True, "turn_line": True, "summary": True, "banner": True},
    }
    with open(os.path.join(home, "preferences.json"), "w") as f:
        json.dump(prefs, f)
    # guard.json
    guard = {
        "code_extensions": [".py"],
        "delegation_logs": [os.path.join(home, "delegations.jsonl")],
        "audit_log": os.path.join(home, "audit.jsonl"),
        "max_lines": 3,
    }
    with open(os.path.join(home, "guard.json"), "w") as f:
        json.dump(guard, f)
    # delegations.jsonl
    open(os.path.join(home, "delegations.jsonl"), "w").close()


def test_settings_cli_guard_refused():
    """Test that settings_cli_guard refuses the new bypass cases."""
    print("=== Testing settings_cli_guard REFUSED cases ===")
    refused_cases = [
        "python3 -I /x/public/bin/frugalflow.py off",
        "python3 -u /x/public/bin/frugalflow.py mode observe",
        "python3 -m frugalflow_app.bin.frugalflow off",
        "/x/public/bin/frugalflow.py off",
        "bash -lc 'frugalflow off'",
        "dash -c 'frugalflow off'",
        "ksh -c 'frugalflow off'",
        "fish -c 'frugalflow off'",
        "echo 'frugalflow off' | sh",
        "sh <<< 'frugalflow off'",
        "perl -e 'system \"frugalflow off\"'",
        "ruby -e 'system \"frugalflow off\"'",
        "node -e 'require(\"child_process\").execSync(\"frugalflow off\")'",
        "git -c alias.x='!frugalflow off' x",
        "F=frugalflow; $F off",
        # 2026-11-12 (D1): python options are scanned, not skipped from a closed list.
        "python3 -Wignore /opt/ff/bin/config_cmd.py off",
        "python3 -q /opt/ff/bin/init_cmd.py --mode observe",
        "python3 -P /opt/ff/bin/setup_cmd.py --yes",
        "python3 -bb /opt/ff/bin/uninstall_cmd.py",
        "python3 -IS /opt/ff/bin/onboard_cmd.py --mode active",
        "python3 -W ignore /opt/ff/bin/frugalflow.py off",
        "uv run python /opt/ff/bin/config_cmd.py off",
        "/opt/ff/bin/config_cmd.py off",
        "/opt/ff/bin/init_cmd.py --mode observe",
        # 2026-11-12 (D12): code fed to an interpreter stays refused.
        "python3 <<'EOF'\nimport subprocess\nsubprocess.run(['frugalflow','off'])\nEOF",
        "python3 -c \"import subprocess; subprocess.run(['frugalflow','off'])\"",
        "echo 'frugalflow off' | python3",
        # 2026-11-12 (F1): a command substitution, a link or an alias hides the head.
        "$(echo frugalflow) off",
        "`echo frugalflow` off",
        "$(which frugalflow) mode observe",
        "ln -s /opt/ff/bin/frugalflow /tmp/ff && /tmp/ff off",
        "alias f=frugalflow; f off",
        # 2026-11-12 (G1): a plain assignment in the same command is resolved
        # first; an executed or hidden head with a setting word anywhere refuses.
        "F=off; frugalflow $F",
        "CMD='frugalflow off'; $CMD",
        "CMD=frugalflow; ARG=off; $CMD $ARG",
        "echo frugalflow off | xargs bash -c",
        'bash -c "$(echo frugalflow off)"',
        'eval "$(echo frugalflow off)"',
        "ln -s $(which frugalflow) /tmp/ff && /tmp/ff off",
        # 2026-11-12 (G1): a link made at a full path, called by its base name through PATH.
        "ln -s $(which frugalflow) /opt/ff/bin/ff && ff off",
        # 2026-11-12 (H1): the subcommand is a command substitution: only an
        # `echo <literal words>` substitution is judged; any other is refused.
        "frugalflow $(echo off)",
        "frugalflow `echo off`",
        "frugalflow $(cat x)",
        "frugalflow $(echo mode) observe",
        "frugalflow run $(echo config_cmd) off",
        "python3 /opt/ff/bin/frugalflow.py $(echo off)",
    ]
    failed = 0
    for cmd in refused_cases:
        code, out = run_guard_check(cmd)
        if code == 10 and out.startswith("REFUSED:"):
            print(f"  PASS: {cmd[:60]}...")
        else:
            print(f"  FAIL: {cmd[:60]}... -> code={code}, out={out[:80]}")
            failed += 1
    return failed


def test_settings_cli_guard_free():
    """Test that settings_cli_guard allows the free witnesses."""
    print("=== Testing settings_cli_guard FREE cases ===")
    free_cases = [
        "frugalflow status",
        "frugalflow doctor",
        "frugalflow config",
        "frugalflow config --home /tmp/h",
        "frugalflow scan --staged",
        "frugalflow resume",
        "frugalflow notes show",
        "frugalflow --help",
        "frugalflow --notice",
        "frugalflow run session_banner",
        "frugalflow run config_cmd config",
        "python3 -I x/frugalflow.py doctor",
        "python3 x/config_cmd.py --notice",
        "echo frugalflow off",
        "grep mode off notes.txt",
        "cat <<EOF\nfrugalflow off\nEOF",
        "grep -n frugalflow README.md",
        "F=frugalflow; $F status",
        # 2026-11-12 (D12): a git -m message or an echo/grep argument is text, not code.
        "git commit -m 'doc: explain frugalflow off'",
        "echo 'frugalflow off'",
        "grep 'frugalflow off' notes.txt",
        # 2026-11-12 (D1): scanned options before a read-only script stay free.
        "python3 -W ignore /opt/ff/bin/config_cmd.py --notice",
        "uv run python /opt/ff/bin/frugalflow.py doctor",
        "/opt/ff/bin/config_cmd.py --notice",
        "/opt/ff/bin/init_cmd.py --notice",
        # 2026-11-12 (F1): a substitution or a link naming no FrugalFlow tool stays free.
        "$(echo echo) hello",
        "ln -s /opt/a /tmp/b",
        # 2026-11-12 (G1): text, a reader and a reading subcommand stay free.
        "grep -rn 'frugalflow off' docs",
        "F=hello; echo $F",
        "ls | xargs wc -l",
        "S=status; frugalflow $S",
        # 2026-11-12 (H1): an echo substitution of literal words is judged by those words.
        "frugalflow $(echo status)",
        "frugalflow $(echo doctor)",
        "python3 /opt/ff/bin/frugalflow.py $(echo doctor)",
    ]
    failed = 0
    for cmd in free_cases:
        code, out = run_guard_check(cmd)
        if code == 0 and out == "FREE":
            print(f"  PASS: {cmd[:60]}...")
        else:
            print(f"  FAIL: {cmd[:60]}... -> code={code}, out={out[:80]}")
            failed += 1
    return failed


def test_claudecode_tty_check():
    """Test CLAUDECODE=1 with non-TTY stdin/stdout blocks setting changes."""
    print("=== Testing CLAUDECODE TTY check ===")
    failed = 0

    with tempfile.TemporaryDirectory() as home:
        setup_home(home, "active")

        # Test cases that should be blocked (exit 3) with CLAUDECODE=1 and non-TTY
        blocked_commands = [
            ["off"],
            ["on"],
            ["mode", "observe"],
            ["display", "statusline", "off"],
            ["init", "--mode", "observe"],
            ["setup", "--yes"],
            ["uninstall"],
            ["config", "set", "switch.mode", "observe"],
            ["memory", "decline", "/tmp/test"],
            ["notes", "add-pitfall", "test"],
            ["notes", "merge"],
            ["notes", "measure"],
            ["run", "model_notes"],
        ]

        for cmd in blocked_commands:
            code, stdout, stderr = run_frugalflow(
                cmd, home=home, env_extra={"CLAUDECODE": "1"}, stdin_data="x"
            )
            if code == 3 and "Refused: this command changes a FrugalFlow setting; run it yourself in a terminal." in stdout:
                print(f"  PASS (blocked): frugalflow {' '.join(cmd)} -> exit 3")
            else:
                print(f"  FAIL (should block): frugalflow {' '.join(cmd)} -> code={code}, stdout={stdout[:80]}, stderr={stderr[:80]}")
                failed += 1

        # Test cases that should NOT be blocked by CLAUDECODE
        # They may fail for other reasons (missing vault, etc.) but not due to CLAUDECODE TTY check
        # We check that the output doesn't contain the CLAUDECODE block message
        allowed_commands = [
            ["status"],
            ["doctor"],
            ["config"],
            ["config", "--home", "/tmp/h"],
            ["scan", "--staged"],
            ["resume"],
            ["notes", "show"],
            ["--help"],
            ["--notice"],
            ["run", "session_banner"],
            ["run", "config_cmd", "config"],
        ]

        for cmd in allowed_commands:
            code, stdout, stderr = run_frugalflow(
                cmd, home=home, env_extra={"CLAUDECODE": "1"}, stdin_data="x"
            )
            if "Refused: this command changes a FrugalFlow setting; run it yourself in a terminal." not in stdout:
                print(f"  PASS (not blocked): frugalflow {' '.join(cmd)} -> exit {code}")
            else:
                print(f"  FAIL (should not block): frugalflow {' '.join(cmd)} -> code={code}, stdout={stdout[:80]}")
                failed += 1

        # Test that without CLAUDECODE, setting changes work (exit 0)
        print("  Testing without CLAUDECODE (should work)...")
        code, stdout, stderr = run_frugalflow(["off"], home=home, env_extra={"CLAUDECODE": "0"})
        if code == 0:
            print(f"  PASS (no CLAUDECODE): frugalflow off -> exit 0")
        else:
            print(f"  FAIL (no CLAUDECODE): frugalflow off -> code={code}, stdout={stdout[:80]}, stderr={stderr[:80]}")
            failed += 1

        # Test that with CLAUDECODE but TTY (simulated), it would work
        # We can't easily simulate TTY in subprocess, but we verified non-TTY blocks

    return failed


def run_cmd_script(script, args, home=None, env_extra=None, stdin_data=None):
    """Run a *_cmd.py script directly with given args and environment."""
    env = os.environ.copy()
    env["HOME"] = throwaway_home()
    env.pop("CLAUDECODE", None)
    if home:
        env["FRUGALFLOW_HOME"] = home
    if env_extra:
        env.update(env_extra)
    script_dir = os.path.dirname(os.path.abspath(__file__))
    bin_dir = os.path.join(script_dir, "..", "bin")
    env["PYTHONPATH"] = bin_dir + (os.pathsep + env["PYTHONPATH"]) if env.get("PYTHONPATH") else bin_dir
    proc = subprocess.run(
        [sys.executable, os.path.join(bin_dir, script)] + args,
        capture_output=True,
        text=True,
        env=env,
        input=stdin_data,
    )
    return proc.returncode, proc.stdout, proc.stderr


def test_cmd_scripts_direct_claudecode():
    """Test the CLAUDECODE TTY check when a *_cmd.py script runs directly."""
    print("=== Testing direct *_cmd.py under CLAUDECODE ===")
    failed = 0
    block_message = "Refused: this command changes a FrugalFlow setting; run it yourself in a terminal."

    with tempfile.TemporaryDirectory() as home:
        setup_home(home, "active")

        # Setting-changing direct calls must be blocked (exit 3, same message).
        blocked_calls = [
            ("config_cmd.py", ["off"]),
            ("config_cmd.py", ["config", "set", "switch.mode", "observe"]),
            ("init_cmd.py", ["--mode", "observe"]),
            ("setup_cmd.py", ["--yes"]),
            ("uninstall_cmd.py", []),
            ("onboard_cmd.py", ["--yes"]),
        ]
        for script, args in blocked_calls:
            code, stdout, stderr = run_cmd_script(
                script, args, home=home, env_extra={"CLAUDECODE": "1"}, stdin_data="x"
            )
            if code == 3 and block_message in stdout:
                print(f"  PASS (blocked): {script} {' '.join(args)} -> exit 3")
            else:
                print(f"  FAIL (should block): {script} {' '.join(args)} -> code={code}, stdout={stdout[:80]}, stderr={stderr[:80]}")
                failed += 1

        # Read-only direct calls must not be blocked.
        allowed_calls = [
            ("config_cmd.py", ["config"]),
            ("config_cmd.py", ["--notice"]),
            ("init_cmd.py", ["--notice"]),
            ("setup_cmd.py", ["--notice"]),
            ("uninstall_cmd.py", ["--notice"]),
            ("onboard_cmd.py", ["--notice"]),
        ]
        for script, args in allowed_calls:
            code, stdout, stderr = run_cmd_script(
                script, args, home=home, env_extra={"CLAUDECODE": "1"}, stdin_data="x"
            )
            if block_message not in stdout:
                print(f"  PASS (not blocked): {script} {' '.join(args)} -> exit {code}")
            else:
                print(f"  FAIL (should not block): {script} {' '.join(args)} -> code={code}, stdout={stdout[:80]}")
                failed += 1

        # Without CLAUDECODE, a direct setting change works (exit 0).
        code, stdout, stderr = run_cmd_script("config_cmd.py", ["off"], home=home)
        if code == 0:
            print("  PASS (no CLAUDECODE): config_cmd.py off -> exit 0")
        else:
            print(f"  FAIL (no CLAUDECODE): config_cmd.py off -> code={code}, stdout={stdout[:80]}, stderr={stderr[:80]}")
            failed += 1

    return failed


def test_claudecode_no_file_modification():
    """Test that blocked commands don't modify preference files."""
    print("=== Testing no file modification on blocked commands ===")
    failed = 0

    with tempfile.TemporaryDirectory() as home:
        setup_home(home, "active")

        # Read initial preferences
        prefs_path = os.path.join(home, "preferences.json")
        with open(prefs_path, "r") as f:
            initial_prefs = f.read()

        # Try to change setting with CLAUDECODE=1 and non-TTY
        code, stdout, stderr = run_frugalflow(
            ["off"], home=home, env_extra={"CLAUDECODE": "1"}, stdin_data="x"
        )

        # Read preferences again
        with open(prefs_path, "r") as f:
            final_prefs = f.read()

        if code == 3 and initial_prefs == final_prefs:
            print("  PASS: preferences.json unchanged after blocked command")
        else:
            print(f"  FAIL: code={code}, prefs changed={initial_prefs != final_prefs}")
            failed += 1

    return failed


def main():
    subprocess_home = throwaway_home()
    real_home = os.path.expanduser("~")
    if os.path.realpath(subprocess_home) == os.path.realpath(real_home):
        print("E2E SETTINGS CLI TEST ABORTED: the throwaway HOME equals the real user home; refusing to run.")
        shutil.rmtree(subprocess_home, ignore_errors=True)
        sys.exit(2)

    total_failed = 0
    try:
        total_failed += test_settings_cli_guard_refused()
        total_failed += test_settings_cli_guard_free()
        total_failed += test_claudecode_tty_check()
        total_failed += test_cmd_scripts_direct_claudecode()
        total_failed += test_claudecode_no_file_modification()
    finally:
        # Delete the throwaway HOME at the end, even when a test fails.
        shutil.rmtree(subprocess_home, ignore_errors=True)

    if total_failed == 0:
        print("\n=== ALL E2E TESTS PASSED ===")
        sys.exit(0)
    else:
        print(f"\n=== {total_failed} E2E TEST(S) FAILED ===")
        sys.exit(1)


if __name__ == "__main__":
    main()