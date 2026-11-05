#!/usr/bin/env python3
"""settings_cli_guard.py -- refuses shell commands that mutate FrugalFlow settings."""

import os
import subprocess
import sys

from shell_split import split_command
from shell_tokens import tokenize, strip_prefixes

REASON_TEXT = (
    "Guard refused: FrugalFlow settings belong to the user; "
    "the assistant never changes them ({segments}). "
    "To fix: ask the user to run this command in their own terminal."
)

FREE_ARGS = frozenset({"on", "off", "mode", "display", "init", "setup", "uninstall"})
HEREDOC_HEADS = frozenset({"bash", "sh", "zsh"})
SCRIPT_RUN_HEADS = frozenset({"frugalflow.py", "config_cmd.py"})
SCRIPT_INIT_HEADS = frozenset({"init_cmd.py", "setup_cmd.py", "uninstall_cmd.py"})
RUN_INIT_TOOLS = frozenset({
    "init_cmd", "setup_cmd", "uninstall_cmd",
    "init_cmd.py", "setup_cmd.py", "uninstall_cmd.py",
})
RUN_CONFIG_TOOLS = frozenset({"config_cmd", "config_cmd.py"})


def _basename(token):
    return os.path.basename(token)


def _is_python(token):
    base = _basename(token)
    return base in ("python", "python3") or base.startswith("python3.")


def _resolve_run(args):
    """Handle the 'run' subcommand prefix. Returns (changes_directly, remaining_args)."""
    if not args or args[0] != "run":
        return False, args
    if len(args) < 2:
        return False, []
    next_word = _basename(args[1])
    if next_word in RUN_CONFIG_TOOLS:
        return False, args[2:]
    if next_word in RUN_INIT_TOOLS:
        return True, []
    return False, []


def _rule4(args):
    """Rule 4: decide from the resolved argument list."""
    if not args:
        return False
    first = args[0]
    if first in FREE_ARGS:
        return True
    if first == "config" and "set" in args[1:]:
        return True
    if first == "memory" and len(args) >= 2 and args[1] == "decline":
        return True
    if first == "notes" and len(args) >= 2 and args[1] in ("add-pitfall", "merge", "measure"):
        return True
    return False


def segment_changes(tokens):
    """True if this token list (already strip_prefixed) changes FrugalFlow settings."""
    if not tokens:
        return False
    head = _basename(tokens[0])

    # Rule 5: bash/sh/zsh with -c -> recurse on the remainder
    if head in HEREDOC_HEADS:
        if len(tokens) >= 2 and tokens[1] == "-c":
            inner = " ".join(tokens[2:])
            if inner and changes_settings(inner):
                return True
        return False

    # Rule 5: eval -> recurse on the remainder joined by spaces
    if head == "eval":
        inner = " ".join(tokens[1:])
        if inner and changes_settings(inner):
            return True
        return False

    # Rule 7: python/python3/python3.N with -c
    if _is_python(tokens[0]) and len(tokens) >= 2 and tokens[1] == "-c":
        code = " ".join(tokens[2:])
        if "frugalflow" in code or "_cmd" in code:
            return True
        return False

    # Rule 2: python running a named script
    if _is_python(tokens[0]) and len(tokens) >= 2:
        second = _basename(tokens[1])
        if second in SCRIPT_RUN_HEADS:
            args = tokens[2:]
            changed, args = _resolve_run(args)
            if changed:
                return True
            return _rule4(args)
        if second in SCRIPT_INIT_HEADS:
            if len(tokens) >= 3 and tokens[2] in ("--notice", "--help"):
                return False
            return True
        return False

    # Rule 1: head is frugalflow
    if head == "frugalflow":
        args = tokens[1:]
        changed, args = _resolve_run(args)
        if changed:
            return True
        return _rule4(args)

    # 2026-11-05: `xargs frugalflow < f` passed: a launcher that runs its arguments as a
    # command hides the head. When in doubt, refuse.
    if head in LAUNCHER_HEADS and any(
        _basename(t) == "frugalflow" or _basename(t).endswith(("frugalflow.py", "_cmd.py"))
        for t in tokens[1:]
    ):
        return True

    # Rule 9: anything else is free
    return False


LAUNCHER_HEADS = {"xargs", "parallel", "watch", "timeout", "gtimeout", "nice", "find", "script", "caffeinate"}


def changes_settings(command):
    """Return the list of faulty segment strings; empty means the command is free."""
    result = split_command(command)
    segments = result.get("segments", [])
    bodies = result.get("bodies", [])
    error = result.get("error")

    # Rule 8: unterminated structure containing frugalflow or _cmd.py
    if error is not None:
        if "frugalflow" in command or "_cmd.py" in command:
            return [command]
        return []

    faulty = []

    for seg in segments:
        raw = tokenize(seg)
        # xargs/parallel take the arguments from stdin: the subcommand cannot be known.
        names = [_basename(t) for t in raw]
        if ("xargs" in names or "parallel" in names) and any(
                n == "frugalflow" or n.endswith(("frugalflow.py", "_cmd.py")) for n in names):
            faulty.append(seg)
            continue
        toks = strip_prefixes(raw)
        if not toks:
            continue
        head = _basename(toks[0])

        relevant = False
        if head == "frugalflow":
            relevant = True
        elif head in HEREDOC_HEADS and len(toks) >= 2 and toks[1] == "-c":
            relevant = True
        elif head == "eval" or head in LAUNCHER_HEADS:
            relevant = True
        elif _is_python(toks[0]):
            if len(toks) >= 2 and toks[1] == "-c":
                relevant = True
            elif len(toks) >= 2 and _basename(toks[1]) in (SCRIPT_RUN_HEADS | SCRIPT_INIT_HEADS):
                relevant = True

        if relevant and segment_changes(toks):
            faulty.append(seg)

    # Rule 6: heredoc bodies opened by bash/sh/zsh
    for body_info in bodies:
        line = body_info["line"]
        body = body_info["body"]
        line_toks = tokenize(line)
        line_toks = strip_prefixes(line_toks)
        if not line_toks:
            continue
        line_head = _basename(line_toks[0])
        if line_head in HEREDOC_HEADS:
            if changes_settings(body):
                faulty.append(body)

    return faulty


def verdict(tool_name, tool_input):
    """Return (True, reason) if the Bash tool call changes settings, else (False, '')."""
    if tool_name != "Bash":
        return (False, "")
    command = tool_input.get("command", "")
    faulty = changes_settings(command)
    if not faulty:
        return (False, "")
    reason = REASON_TEXT.replace("{segments}", " ; ".join(faulty))
    return (True, reason)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

FIXTURE_FREE = [
    "frugalflow doctor",
    "frugalflow config",
    "frugalflow config --home /tmp/h",
    "frugalflow scan --staged",
    "frugalflow resume",
    "frugalflow notes show",
    "frugalflow --help",
    "frugalflow run session_banner",
    "frugalflow run config_cmd config",
    "python3 /opt/ff/bin/config_cmd.py --notice",
    "python3 /opt/ff/bin/setup_cmd.py --notice",
    "echo frugalflow off",
    "grep mode off notes.txt",
    "cat <<EOF\nfrugalflow off\nEOF",
]

FIXTURE_DIRECT = [
    "frugalflow off",
    "frugalflow on",
    "frugalflow mode observe",
    "frugalflow config set switch.mode observe",
    "frugalflow display statusline off",
    "frugalflow init --mode active",
    "frugalflow setup --yes",
    "frugalflow uninstall",
    "frugalflow memory decline /tmp/p",
    "frugalflow notes add-pitfall x",
]

FIXTURE_DISGUISED = [
    "FRUGALFLOW_HOME=/tmp/h frugalflow off",
    "sudo frugalflow off",
    "/opt/ff/bin/frugalflow mode active",
    "python3 /opt/ff/bin/frugalflow.py off",
    "python3 /opt/ff/bin/config_cmd.py mode observe",
    "frugalflow run config_cmd off",
    "frugalflow run setup_cmd --yes",
    "cd /tmp && frugalflow off",
    "echo $(frugalflow off)",
    "true; frugalflow off",
    'bash -c "frugalflow mode observe"',
    "eval frugalflow off",
    "python3 -c \"import subprocess; subprocess.run(['frugalflow','off'])\"",
    "bash <<EOF\nfrugalflow off\nEOF",
    'frugalflow off "',
]


# ---------------------------------------------------------------------------
# CLI and autotest helpers
# ---------------------------------------------------------------------------

def _run_check_subprocess(command):
    """Run --check in a child process; return (exit_code, first_stdout_line)."""
    script_dir = os.path.dirname(os.path.abspath(__file__))
    env = os.environ.copy()
    existing_pp = env.get("PYTHONPATH", "")
    if existing_pp:
        env["PYTHONPATH"] = script_dir + os.pathsep + existing_pp
    else:
        env["PYTHONPATH"] = script_dir
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--check", command],
        capture_output=True,
        text=True,
        env=env,
    )
    first_line = proc.stdout.splitlines()[0] if proc.stdout else ""
    return proc.returncode, first_line


def _do_check():
    command = sys.argv[2]
    faulty = changes_settings(command)
    if not faulty:
        print("FREE")
        sys.exit(0)
    print("REFUSED: " + " ; ".join(faulty))
    sys.exit(10)


def _do_notice():
    print("NAME      settings_cli_guard.py - refuses a shell command, run by the assistant, that changes FrugalFlow settings.")
    print("READS     the command string of a Bash tool call.")
    print("WRITES    nothing: FREE (exit 0) or REFUSED: <segments> (exit 10).")
    print("EXAMPLE   python3 settings_cli_guard.py --check 'frugalflow off'")
    print("PITFALLS  2026-11-05 the assistant could turn the guard off with frugalflow off; the settings belong to the user.")
    print("          2026-11-05 xargs frugalflow passed: the subcommand came from stdin; a launcher naming frugalflow is refused.")
    sys.exit(0)


def _do_autotest():
    force_fail = os.environ.get("SCG_FORCE_FAIL", "") == "1"
    free_fixture = list(FIXTURE_FREE)
    if force_fail:
        free_fixture.append("frugalflow off")

    results = []

    # Test 1: FIXTURE_FREE -> exit 0 + FREE
    passed = 0
    total = len(free_fixture)
    for cmd in free_fixture:
        code, line = _run_check_subprocess(cmd)
        if code == 0 and line == "FREE":
            passed += 1
    results.append((passed, total, "fixture-free"))

    # Test 2: FIXTURE_DIRECT -> exit 10 + REFUSED: ...
    passed = 0
    total = len(FIXTURE_DIRECT)
    for cmd in FIXTURE_DIRECT:
        code, line = _run_check_subprocess(cmd)
        if code == 10 and line.startswith("REFUSED: "):
            passed += 1
    results.append((passed, total, "fixture-direct"))

    # Test 3: FIXTURE_DISGUISED -> exit 10 + REFUSED: ...
    passed = 0
    total = len(FIXTURE_DISGUISED)
    for cmd in FIXTURE_DISGUISED:
        code, line = _run_check_subprocess(cmd)
        if code == 10 and line.startswith("REFUSED: "):
            passed += 1
    results.append((passed, total, "fixture-disguised"))

    # Test 4: verdict unit test
    r1 = verdict("Write", {"file_path": "/tmp/a", "content": "x"})
    r2 = verdict("Bash", {"command": "frugalflow off"})
    ok4 = True
    if r1 != (False, ""):
        ok4 = False
    if not r2[0]:
        ok4 = False
    if not r2[1].startswith("Guard refused: FrugalFlow settings belong to the user;"):
        ok4 = False
    if "(frugalflow off)" not in r2[1]:
        ok4 = False
    results.append((1 if ok4 else 0, 1, "verdict"))

    # Test 5: exit code 1 via SCG_FORCE_FAIL subprocess
    if force_fail:
        results.append((1, 1, "exit-code-1"))
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        env = os.environ.copy()
        existing_pp = env.get("PYTHONPATH", "")
        if existing_pp:
            env["PYTHONPATH"] = script_dir + os.pathsep + existing_pp
        else:
            env["PYTHONPATH"] = script_dir
        env["SCG_FORCE_FAIL"] = "1"
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--autotest"],
            capture_output=True,
            text=True,
            env=env,
        )
        results.append((1 if proc.returncode == 1 else 0, 1, "exit-code-1"))

    # Print one line per test; determine overall exit code
    all_ok = True
    for passed, total, label in results:
        if passed == total:
            print("PASS %s: expected %d/%d, got %d/%d" % (label, total, total, passed, total))
        else:
            print("FAIL %s: expected %d/%d, got %d/%d" % (label, total, total, passed, total))
            all_ok = False

    if not all_ok:
        sys.exit(1)
    sys.exit(0)


def main():
    if len(sys.argv) < 2:
        _do_notice()
    flag = sys.argv[1]
    if flag == "--check" and len(sys.argv) >= 3:
        _do_check()
    elif flag == "--autotest":
        _do_autotest()
    elif flag == "--notice":
        _do_notice()
    else:
        print("Usage: settings_cli_guard.py [--check COMMAND | --autotest | --notice]")
        sys.exit(2)


if __name__ == "__main__":
    main()
