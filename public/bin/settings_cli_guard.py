#!/usr/bin/env python3
"""settings_cli_guard.py -- refuses shell commands that mutate FrugalFlow settings."""

import os
import re
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
HEREDOC_HEADS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish"})
# 2026-11-12: "frugalflow" is the installed console script the hooks launch with -I.
SCRIPT_RUN_HEADS = frozenset({"frugalflow.py", "frugalflow", "config_cmd.py", "memory_cmd.py"})
SCRIPT_INIT_HEADS = frozenset({"init_cmd.py", "setup_cmd.py", "uninstall_cmd.py", "onboard_cmd.py"})
RUN_INIT_TOOLS = frozenset({
    "init_cmd", "setup_cmd", "uninstall_cmd",
    "init_cmd.py", "setup_cmd.py", "uninstall_cmd.py",
})
RUN_CONFIG_TOOLS = frozenset({"config_cmd", "config_cmd.py"})

# Readers: commands that only read/output data, never execute frugalflow
READER_HEADS = frozenset({
    "echo", "printf", "grep", "egrep", "rg", "cat", "head", "tail",
    "less", "more", "ls", "wc", "diff", "file", "stat",
})

# Python options that take a separate argument when not attached: -W ignore
PYTHON_ARG_OPTS = frozenset({"-X", "-W", "--check-hash-based-pycs"})

# Regex to detect frugalflow setting-changing subcommands in raw text
# Matches frugalflow or frugalflow.py followed by setting-changing subcommand
# Tolerates quotes and commas: 'frugalflow','off' or "frugalflow","off"
SETTING_SUBCOMMANDS = (
    r"(?:on|off|mode|display|init|setup|uninstall|config\s+set|memory\s+decline|"
    r"notes\s+(?:add-pitfall|merge|measure)|run\s+model_notes)"
)
FRUGALFLOW_SETTING_RE = re.compile(
    r"(?:frugalflow(?:\.py)?)[\"',\s]+" + SETTING_SUBCOMMANDS,
    re.IGNORECASE
)

# Head token that is a variable expansion: $F, ${F} (quotes are removed by tokenize).
# The command it runs is unknown until the shell resolves it.
VAR_HEAD_RE = re.compile(r"^\$[{]?[A-Za-z_][A-Za-z0-9_]*[}]?$")

# A setting-changing subcommand appearing anywhere in raw segment text
SETTING_SUB_RE = re.compile(r"\b(?:" + SETTING_SUBCOMMANDS + r")\b", re.IGNORECASE)

# Shell heads that take -c (or grouped option containing c)
SHELL_C_HEADS = frozenset({"bash", "sh", "zsh", "dash", "ksh", "fish"})

# Interpreter heads that take -e (code from command line)
INTERPRETER_E_HEADS = frozenset({"perl", "ruby", "node"})

# Non-reader interpreter heads for heredoc bodies
NON_READER_INTERPRETERS = frozenset({
    "python", "python3", "perl", "ruby", "node", "bash", "sh", "zsh", "dash", "ksh", "fish",
})


def _basename(token):
    return os.path.basename(token)


def _is_python(token):
    base = _basename(token)
    return base in ("python", "python3", "pypy", "pypy3") or base.startswith("python3.")


def _python_head_index(tokens):
    """Index of the python head token: python, python3, python3.N, pypy, pypy3,
    or the python of a 'uv run python' launcher; -1 when there is none."""
    if _is_python(tokens[0]):
        return 0
    if _basename(tokens[0]) == "uv" and len(tokens) > 2 and tokens[1] == "run" and _is_python(tokens[2]):
        return 2
    return -1


def _skip_python_opts(tokens, start=0):
    """Scan the python interpreter options after the head at index `start`.
    Every token starting with '-' before the first one that is not is an option:
    grouped options (-IS) and attached options (-Wignore) are options; -X, -W and
    --check-hash-based-pycs take a separate argument when not attached (-W ignore).
    -c and -m are returned as-is: the caller reads the code or module after them.
    Returns the index of the first token that is not an option: the -c/-m flag,
    or the script."""
    i = start + 1
    while i < len(tokens):
        tok = tokens[i]
        if tok in ("-c", "-m"):
            return i
        if not tok.startswith("-"):
            break
        if tok in PYTHON_ARG_OPTS and i + 1 < len(tokens) and not tokens[i + 1].startswith("-"):
            i += 2
        else:
            i += 1
    return i


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
    if first == "run" and len(args) >= 2 and _basename(args[1]) in ("model_notes", "model_notes.py"):
        return True
    return False


def _raw_text_changes_settings(text):
    """Check if raw text contains frugalflow/frugalflow.py followed by a setting-changing subcommand."""
    return bool(FRUGALFLOW_SETTING_RE.search(text))


def _head_is_variable_expansion(token):
    """True if the head token is a variable expansion ($F, ${F}, "$F"): the command is hidden."""
    return bool(VAR_HEAD_RE.match(token))


def _is_shell_with_c_option(head, tokens):
    """Check if shell head has a grouped option containing 'c' (e.g., bash -lc, dash -c)."""
    if head not in SHELL_C_HEADS:
        return False
    for tok in tokens[1:]:
        if tok == "-c":
            return True
        if tok.startswith("-") and "c" in tok[1:] and not tok.startswith("--"):
            return True
    return False


def _is_interpreter_with_e_option(head, tokens):
    """Check if interpreter head has -e option (code from command line)."""
    if head not in INTERPRETER_E_HEADS:
        return False
    for i, tok in enumerate(tokens[1:]):
        if tok == "-e" and i + 1 < len(tokens) - 1:
            return True
        if tok.startswith("-e") and len(tok) > 2:
            return True
    return False


def _is_non_reader_interpreter(head):
    """Check if the head is a non-reader interpreter for heredoc bodies."""
    base = _basename(head)
    # Check for python/python3 variants
    if base in ("python", "python3") or base.startswith("python3."):
        return True
    return base in NON_READER_INTERPRETERS


def segment_changes(tokens):
    """True if this token list (already strip_prefixed) changes FrugalFlow settings."""
    if not tokens:
        return False
    head = _basename(tokens[0])

    # Rule 5: shell with -c -> recurse on the remainder
    if _is_shell_with_c_option(head, tokens):
        # Find the -c option and get everything after it
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-c" or (tok.startswith("-") and "c" in tok[1:] and not tok.startswith("--")):
                inner = " ".join(tokens[i+1:])
                if inner and changes_settings(inner):
                    return True
                break
        return False

    # Rule 5: eval -> recurse on the remainder joined by spaces
    if head == "eval":
        inner = " ".join(tokens[1:])
        if inner and changes_settings(inner):
            return True
        return False

    # Rule 7: python/python3/python3.N/pypy with options, -c, -m or a script
    pidx = _python_head_index(tokens)
    if pidx >= 0:
        # Scan the python options first
        idx = _skip_python_opts(tokens, pidx)
        if idx < len(tokens):
            # -c: the code after it is executed
            if tokens[idx] == "-c" and idx + 1 < len(tokens):
                code = " ".join(tokens[idx+1:])
                if "frugalflow" in code or "_cmd" in code:
                    return True
                return False
            # -m module
            if tokens[idx] == "-m" and idx + 1 < len(tokens):
                module = tokens[idx+1]
                if "frugalflow" in module:
                    # Treat as running frugalflow script
                    inner_args = tokens[idx+2:]
                    changed, inner_args = _resolve_run(inner_args)
                    if changed:
                        return True
                    return _rule4(inner_args)
                return False
            # A setting script run through the interpreter
            script = _basename(tokens[idx])
            if script in SCRIPT_RUN_HEADS:
                args = tokens[idx+1:]
                if script == "memory_cmd.py":
                    args = ["memory"] + args
                changed, args = _resolve_run(args)
                if changed:
                    return True
                return _rule4(args)
            if script in SCRIPT_INIT_HEADS:
                if len(tokens) > idx + 1 and tokens[idx+1] in ("--notice", "--help"):
                    return False
                return True
        return False

    # Rule 2: interpreter with -e (perl -e, ruby -e, node -e)
    if _is_interpreter_with_e_option(head, tokens):
        # Get the code after -e
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-e" and i + 1 < len(tokens):
                code = " ".join(tokens[i+1:])
                if _raw_text_changes_settings(code):
                    return True
                break
            if tok.startswith("-e") and len(tok) > 2:
                code = tok[2:] + " " + " ".join(tokens[i+1:])
                if _raw_text_changes_settings(code):
                    return True
                break
        return False

    # Rule 1: head is frugalflow
    if head == "frugalflow":
        args = tokens[1:]
        changed, args = _resolve_run(args)
        if changed:
            return True
        return _rule4(args)

    # Direct execution of a setting script: /opt/ff/bin/config_cmd.py off
    if head in SCRIPT_RUN_HEADS:
        args = tokens[1:]
        if head == "memory_cmd.py":
            args = ["memory"] + args
        changed, args = _resolve_run(args)
        if changed:
            return True
        return _rule4(args)
    if head in SCRIPT_INIT_HEADS:
        if len(tokens) > 1 and tokens[1] in ("--notice", "--help"):
            return False
        return True

    # git -c alias.x='!frugalflow off' x
    if head == "git":
        # Check for -c option with alias containing frugalflow setting change
        for i, tok in enumerate(tokens[1:], 1):
            if tok == "-c" and i + 1 < len(tokens):
                config_val = tokens[i+1]
                if _raw_text_changes_settings(config_val):
                    return True
            elif tok.startswith("-c") and len(tok) > 2:
                config_val = tok[2:]
                if _raw_text_changes_settings(config_val):
                    return True

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

    # Check for pipe to shell (e.g., echo 'frugalflow off' | sh)
    # and here-string to shell (e.g., sh <<< 'frugalflow off')
    if _command_feeds_shell_via_pipe_or_herestring(command):
        if _raw_text_changes_settings(command):
            faulty.append(command)
            return faulty

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
        # Reader heads (echo, printf, grep, etc.) are never relevant unless they feed a shell
        # (which is handled above via _command_feeds_shell_via_pipe_or_herestring)
        if head not in READER_HEADS:
            if head == "frugalflow":
                relevant = True
            elif _is_shell_with_c_option(head, toks):
                relevant = True
            elif head == "eval":
                relevant = True
            elif head in LAUNCHER_HEADS:
                relevant = True
            elif _python_head_index(toks) >= 0:
                # Check after scanning the python options
                idx = _skip_python_opts(toks, _python_head_index(toks))
                if idx < len(toks):
                    if toks[idx] == "-c":
                        relevant = True
                    elif toks[idx] == "-m" and idx + 1 < len(toks) and "frugalflow" in toks[idx+1]:
                        relevant = True
                    elif _basename(toks[idx]) in (SCRIPT_RUN_HEADS | SCRIPT_INIT_HEADS):
                        relevant = True
            elif _is_interpreter_with_e_option(head, toks):
                relevant = True
            elif head in (SCRIPT_RUN_HEADS | SCRIPT_INIT_HEADS):
                # A setting script run directly: /opt/ff/bin/config_cmd.py off
                relevant = True
            elif head == "git":
                relevant = True

        if relevant and segment_changes(toks):
            faulty.append(seg)
        # Also check raw text for cases where tokenization might miss things.
        # 2026-11-12: a git -m message is text git never executes: git is judged
        # by its options (the -c alias check above), not by its raw text.
        elif head != "git" and _raw_text_changes_settings(seg) and head not in READER_HEADS:
            faulty.append(seg)
        # A segment headed by a variable expansion ($F off) hides the command:
        # when the command text names frugalflow and the segment carries a
        # setting-changing subcommand, refuse. Reading subcommands stay free.
        elif _head_is_variable_expansion(toks[0]) and "frugalflow" in command and SETTING_SUB_RE.search(seg):
            faulty.append(seg)

    # Rule 6: heredoc bodies opened by non-reader interpreters
    for body_info in bodies:
        line = body_info["line"]
        body = body_info["body"]
        line_toks = tokenize(line)
        line_toks = strip_prefixes(line_toks)
        if not line_toks:
            continue
        line_head = _basename(line_toks[0])
        # Check if the heredoc is given to a non-reader interpreter
        if _is_non_reader_interpreter(line_head):
            if changes_settings(body):
                faulty.append(body)
        # Also check the original HEREDOC_HEADS for backward compatibility
        elif line_head in HEREDOC_HEADS:
            if changes_settings(body):
                faulty.append(body)

    return faulty


# 2026-11-12: a string piped to an interpreter or fed to it with <<< is executed
# code, not text: echo 'frugalflow off' | python3 is a setting change.
FEED_HEADS_RE = r"(?:python3?(?:\.\d+)?|pypy3?|perl|ruby|node|bash|sh|zsh|dash|ksh|fish)"


def _command_feeds_shell_via_pipe_or_herestring(command):
    """Check if the command pipes to a shell/interpreter or feeds one with a here-string."""
    # Pipe to shell or interpreter: ... | sh, ... | python3, etc.
    # Here-string: sh <<< '...', python3 <<< '...'
    if re.search(r'\|\s*' + FEED_HEADS_RE + r'(\s|$)', command):
        return True
    if re.search(r'\b' + FEED_HEADS_RE + r'\s*<<<', command):
        return True
    return False


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
    "python3 -I /opt/ff/bin/frugalflow run guard_hook --hook",
    "python3 -I /opt/ff/bin/frugalflow run statusline",
    "echo frugalflow off",
    "grep mode off notes.txt",
    "cat <<EOF\nfrugalflow off\nEOF",
    "git commit -m 'doc: explain frugalflow off'",
    "echo 'frugalflow off'",
    "grep 'frugalflow off' notes.txt",
    "python3 -W ignore /opt/ff/bin/config_cmd.py --notice",
    "uv run python /opt/ff/bin/frugalflow.py doctor",
    "/opt/ff/bin/config_cmd.py --notice",
    "/opt/ff/bin/init_cmd.py --notice",
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
    "python3 -I /opt/ff/bin/frugalflow off",
    "python3 -I /opt/ff/bin/frugalflow init --mode active",
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
    "python3 -Wignore /opt/ff/bin/config_cmd.py off",
    "python3 -q /opt/ff/bin/init_cmd.py --mode observe",
    "python3 -P /opt/ff/bin/setup_cmd.py --yes",
    "python3 -bb /opt/ff/bin/uninstall_cmd.py",
    "python3 -IS /opt/ff/bin/onboard_cmd.py --mode active",
    "python3 -W ignore /opt/ff/bin/frugalflow.py off",
    "uv run python /opt/ff/bin/config_cmd.py off",
    "/opt/ff/bin/config_cmd.py off",
    "/opt/ff/bin/init_cmd.py --mode observe",
    "python3 <<'EOF'\nimport subprocess\nsubprocess.run(['frugalflow','off'])\nEOF",
    "echo 'frugalflow off' | python3",
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
    print("          2026-11-12 the hooks launch the installed console script with -I; python3 -I <path>/frugalflow off is refused like frugalflow.py off.")
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
