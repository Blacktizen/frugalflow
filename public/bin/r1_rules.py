import os
import sys
import re
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_quotes

GESTURES = [
    r"\bgit\s+(?:-C\s+\S+\s+)?(?:commit|merge|push|rebase|reset|revert|cherry-pick|tag)\b",
    r"\bgh\s+pr\s+(?:create|merge)\b",
    r"\bsystemctl\s+(?:start|stop|restart|enable|disable|daemon-reload)\b",
    r"\blaunchctl\s+(?:load|unload|bootstrap|bootout|enable|disable)\b",
    r"\bschtasks\s+/(?:create|change|delete)\b",
    r"\bcrontab\s+-[er]\b",
]
LOG_CALL = re.compile(r"(?:^|[;&|\n(]\s*)(?:\S*/)?python3?\s+\S*journal_add\.py(?:\s|$)")
VAULT_ARG = re.compile(r"--vault\s+(\S+)")
CD_ARG = re.compile(r"(?:^|[;&|\n]\s*)cd\s+(\"[^\"]*\"|'[^']*'|\S+)")
GIT_DIR_ARG = re.compile(r"\bgit\s+-C\s+(\"[^\"]*\"|'[^']*'|\S+)")


def effective_command(command):
    text = shell_quotes.extract_heredocs(command)[0]
    return shell_quotes.strip_comments(shell_quotes.mask_quotes(text))


def gesture_in(command):
    effective = effective_command(command)
    for pattern in GESTURES:
        match = re.search(pattern, effective)
        if match:
            return match.group(0)
    return ""


def is_log_call(command):
    return bool(LOG_CALL.search(effective_command(command)))


def strip_outer_quotes(value):
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def log_vaults(command):
    if not is_log_call(command):
        return []
    result = []
    for match in VAULT_ARG.finditer(command):
        value = match.group(1)
        value = strip_outer_quotes(value)
        if value.startswith("--"):
            continue
        if value not in result:
            result.append(value)
    return result


def command_repo(command, cwd):
    git_dirs = [strip_outer_quotes(match.group(1)) for match in GIT_DIR_ARG.finditer(command)]
    cds = [strip_outer_quotes(match.group(1)) for match in CD_ARG.finditer(command)]
    if git_dirs:
        target = git_dirs[-1]
    elif cds:
        target = cds[0]
    else:
        target = ""
    if target == "":
        return os.path.normpath(cwd)
    return os.path.normpath(os.path.join(cwd, os.path.expanduser(target)))


def executed_commands(entries):
    done = set()
    for entry in entries:
        if entry.get("event") == "tool_after":
            done.add(entry.get("id"))
    result = []
    for entry in entries:
        if entry.get("event") == "tool_before" and entry.get("tool") == "Bash" and entry.get("id") in done:
            try:
                payload = json.loads(entry.get("input", ""))
            except (json.JSONDecodeError, TypeError):
                continue
            if not isinstance(payload, dict):
                continue
            command = payload.get("command")
            if not isinstance(command, str):
                continue
            result.append((entry, command))
    return result


def missing_log(entries, exempt=None):
    result = []
    for entry, command in executed_commands(entries):
        if gesture_in(command) != "" and (exempt is None or exempt(command, entry) is False):
            result.append(" ".join(command.split())[:120])
        if is_log_call(command):
            result = []
    return result


def trace_only(files):
    if not files:
        return False
    for item in files:
        normalized = item.replace("\\", "/")
        if normalized != "vault/log.md" and not normalized.endswith("/vault/log.md"):
            return False
    return True


NOTICE = (
    "NAME      r1_rules.py - finds, in a session log, the state-changing shell commands that ran without a vault log entry after them.\n"
    "READS     nothing: pure module; the caller passes the log events and the commands, with shell_quotes.py beside it.\n"
    "WRITES    nothing: missing_log() returns the commands still waiting for a log entry; trace_only() says whether a commit only carries the vault log.\n"
    "EXAMPLE   python3 r1_rules.py --notice\n"
    "PITFALLS  2026-09-06 55 minutes and 5 commits went by without one log entry.\n"
    "          2026-09-19 a grep that named the log tool disarmed the guard: only a real call counts, never a mention.\n"
)


def _autotest():
    def before(ident, command):
        return {"event": "tool_before", "tool": "Bash", "id": ident, "input": json.dumps({"command": command})}

    def after(ident):
        return {"event": "tool_after", "tool": "Bash", "id": ident}

    LOG = "python3 public/bin/journal_add.py --vault /w/vault --title t --field Decision=d"
    RUN_GESTURE = [{"event": "prompt"}, before("a1", "git commit -m fix"), after("a1")]
    GESTURE_THEN_LOG = RUN_GESTURE + [before("b2", LOG), after("b2")]
    LOG_THEN_GESTURE = [before("b2", LOG), after("b2"), before("c3", "git push"), after("c3")]
    NOT_RUN = [before("d4", "git push")]
    MENTION = RUN_GESTURE + [before("e5", "grep -n vault public/bin/journal_add.py"), after("e5")]

    failures = 0

    # Test 1
    expected1 = ["git commit", "git -C /repo push", "", "", "", ""]
    got1 = [
        gesture_in("git commit -m x"),
        gesture_in("git -C /repo push"),
        gesture_in("git status"),
        gesture_in("cat <<EOF > notes.txt\ngit commit -m x\nEOF"),
        gesture_in('echo "git push" > f'),
        gesture_in("ls # git push"),
    ]
    if got1 == expected1:
        print("PASS 1 gesture_in: expected " + repr(expected1) + " got " + repr(got1))
    else:
        print("FAIL 1 gesture_in: expected " + repr(expected1) + " got " + repr(got1))
        failures += 1

    # Test 2
    expected2 = [True, True, False, False, ["/a/vault", "/b/vault"], []]
    got2 = [
        is_log_call(LOG),
        is_log_call("cd /p && python3 journal_add.py --vault v"),
        is_log_call("grep -n vault public/bin/journal_add.py"),
        is_log_call('python3 -c "import journal_add.py"'),
        log_vaults('python3 journal_add.py --vault "/a/vault" --title t ; python3 journal_add.py --vault /b/vault --title u'),
        log_vaults("sed -n 1p journal_add.py --vault /a/vault"),
    ]
    if got2 == expected2:
        print("PASS 2 is_log_call/log_vaults: expected " + repr(expected2) + " got " + repr(got2))
    else:
        print("FAIL 2 is_log_call/log_vaults: expected " + repr(expected2) + " got " + repr(got2))
        failures += 1

    # Test 3
    expected3 = [["git commit -m fix"], [], ["git push"], [], ["git commit -m fix"], []]
    got3 = [
        missing_log(RUN_GESTURE),
        missing_log(GESTURE_THEN_LOG),
        missing_log(LOG_THEN_GESTURE),
        missing_log(NOT_RUN),
        missing_log(MENTION),
        missing_log(RUN_GESTURE, exempt=lambda command, entry: True),
    ]
    if got3 == expected3:
        print("PASS 3 missing_log: expected " + repr(expected3) + " got " + repr(got3))
    else:
        print("FAIL 3 missing_log: expected " + repr(expected3) + " got " + repr(got3))
        failures += 1

    # Test 4
    expected4 = [True, True, False, False, False, False, "/w", "/w/sub", "/b"]
    got4 = [
        trace_only(["vault/log.md"]),
        trace_only(["projects/demo/vault/log.md"]),
        trace_only(["vault/log.md", "bin/x.py"]),
        trace_only([]),
        trace_only(["vault/log.md.bak"]),
        trace_only(["myvault/log.md"]),
        command_repo("git commit -m x", "/w"),
        command_repo("cd sub && git commit -m x", "/w"),
        command_repo("cd /a && git -C /b commit -m x", "/w"),
    ]
    if got4 == expected4:
        print("PASS 4 trace_only/command_repo: expected " + repr(expected4) + " got " + repr(got4))
    else:
        print("FAIL 4 trace_only/command_repo: expected " + repr(expected4) + " got " + repr(got4))
        failures += 1

    # Test 5
    proc_notice = subprocess.run(
        [sys.executable, __file__, "--notice"],
        capture_output=True, text=True
    )
    proc_bogus = subprocess.run(
        [sys.executable, __file__, "--bogus"],
        capture_output=True, text=True
    )
    expected5 = True
    if proc_notice.returncode != 0:
        expected5 = False
    if not proc_notice.stdout.startswith("NAME      r1_rules.py"):
        expected5 = False
    if proc_bogus.returncode != 2:
        expected5 = False
    if "usage: r1_rules.py" not in proc_bogus.stdout:
        expected5 = False
    if expected5:
        print("PASS 5 subprocess: expected True got True")
    else:
        print("FAIL 5 subprocess: expected True got False notice_rc=" + str(proc_notice.returncode) + " bogus_rc=" + str(proc_bogus.returncode))
        failures += 1

    return 0 if failures == 0 else 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) > 1 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write("usage: r1_rules.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "r1_rules", sys.argv[1:])
