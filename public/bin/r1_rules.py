import os
import sys
import re
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_quotes

# Git global options pattern (repeating, optional)
GIT_GLOBAL = r"(?:\s+(?:-C\s+\S+|-c\s+\S+=\S+|--git-dir\s*=?\s*\S+|--work-tree\s*=?\s*\S+|--no-pager|--paginate|-P|--no-optional-locks|--bare))*"

GESTURES = [
    r"\bgit" + GIT_GLOBAL + r"\s+(?:commit|merge|push|rebase|reset|revert|cherry-pick|tag)\b",
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

APPENDED = re.compile(r"APPENDED entry \d+ to ([^\s\\\"]+)")

TITLE_ARG = re.compile(r'--title\s+("([^"]*)"|\'([^\']*)\'|(\S+))')


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


def landed_in(response):
    """Return the filename from an APPENDED response, or empty string if not found."""
    match = APPENDED.search(response)
    if match:
        return match.group(1)
    return ""


def title_of(command):
    """Return the --title value from a journal_add command, or empty string."""
    match = TITLE_ARG.search(command)
    if match:
        # Group 2: double-quoted content, Group 3: single-quoted content, Group 4: unquoted
        if match.group(2) is not None:
            return match.group(2)
        if match.group(3) is not None:
            return match.group(3)
        if match.group(4) is not None:
            return match.group(4)
    return ""


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


def missing_log(entries, exempt=None, landed=None):
    """Return list of gesture commands still waiting for a log entry.

    For each journal_add call when gestures are pending, calls landed(command, entry, since)
    where since is the ts of the FIRST pending gesture. If landed returns True, clears the wait list.
    Without landed, nothing is cleared.
    """
    # Build a map from tool_after id to response
    after_responses = {}
    for entry in entries:
        if entry.get("event") == "tool_after" and entry.get("tool") == "Bash":
            after_id = entry.get("id")
            if after_id:
                after_responses[after_id] = entry.get("response", "")

    result = []
    pending_since = None  # ts of the first pending gesture
    for entry, command in executed_commands(entries):
        if gesture_in(command) != "" and (exempt is None or exempt(command, entry) is False):
            result.append(" ".join(command.split())[:120])
            if pending_since is None:
                pending_since = entry.get("ts")
        if is_log_call(command):
            entry_id = entry.get("id")
            response = after_responses.get(entry_id, "")
            if pending_since is not None and landed is not None:
                if landed(command, entry, pending_since):
                    result = []
                    pending_since = None
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
        return {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "event": "tool_before", "tool": "Bash", "id": ident, "input": json.dumps({"command": command})}

    def after(ident, response=""):
        entry = {"event": "tool_after", "tool": "Bash", "id": ident}
        if response:
            entry["response"] = response
        return entry

    import datetime

    LOG = "python3 public/bin/journal_add.py --vault /w/vault --title t --field Decision=d"
    LOG_SUCCESS = 'APPENDED entry 1 to log.md'
    LOG_FAIL = 'missing page: log.md'
    RUN_GESTURE = [{"event": "prompt"}, before("a1", "git commit -m fix"), after("a1")]
    GESTURE_THEN_LOG = RUN_GESTURE + [before("b2", LOG), after("b2", LOG_SUCCESS)]
    LOG_THEN_GESTURE = [before("b2", LOG), after("b2", LOG_SUCCESS), before("c3", "git push"), after("c3")]
    NOT_RUN = [before("d4", "git push")]
    MENTION = RUN_GESTURE + [before("e5", "grep -n vault public/bin/journal_add.py"), after("e5")]
    GESTURE_THEN_LOG_FAIL = RUN_GESTURE + [before("f6", LOG), after("f6", LOG_FAIL)]

    failures = 0

    # Test 1: gesture_in with basic patterns
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

    # Test 2: is_log_call and log_vaults
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

    # Test 3: missing_log with basic scenarios (no landed provided = nothing clears)
    # landed function that mimics old behavior: checks APPENDED in response
    def landed_old(command, entry, since):
        after_responses = {}
        for e in entries:
            if e.get("event") == "tool_after" and e.get("tool") == "Bash":
                after_id = e.get("id")
                if after_id:
                    after_responses[after_id] = e.get("response", "")
        entry_id = entry.get("id")
        response = after_responses.get(entry_id, "")
        return bool(landed_in(response))

    expected3 = [["git commit -m fix"], ["git commit -m fix"], ["git push"], [], ["git commit -m fix"], [], ["git commit -m fix"]]
    got3 = [
        missing_log(RUN_GESTURE),
        missing_log(GESTURE_THEN_LOG),
        missing_log(LOG_THEN_GESTURE),
        missing_log(NOT_RUN),
        missing_log(MENTION),
        missing_log(RUN_GESTURE, exempt=lambda command, entry: True),
        missing_log(GESTURE_THEN_LOG_FAIL),
    ]
    if got3 == expected3:
        print("PASS 3 missing_log: expected " + repr(expected3) + " got " + repr(got3))
    else:
        print("FAIL 3 missing_log: expected " + repr(expected3) + " got " + repr(got3))
        failures += 1

    # Test 4: trace_only and command_repo
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

    # Test 5: subprocess notice/bogus
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

    # Test 6: landed_in and title_of
    expected6 = ["log.md", "", "my title", ""]
    got6 = [
        landed_in('APPENDED entry 1 to log.md'),
        landed_in('missing page: log.md'),
        title_of('python3 journal_add.py --title "my title" --field x=y'),
        title_of('python3 journal_add.py --field x=y'),
    ]
    if got6 == expected6:
        print("PASS 6 landed_in/title_of: expected " + repr(expected6) + " got " + repr(got6))
    else:
        print("FAIL 6 landed_in/title_of: expected " + repr(expected6) + " got " + repr(got6))
        failures += 1

    # Test 7: missing_log with explicit landed functions (true/false)
    def landed_true(command, entry, since):
        return True
    def landed_false(command, entry, since):
        return False

    RUN_GESTURE_7 = [{"event": "prompt"}, before("g1", "git commit -m fix"), after("g1")]
    GESTURE_THEN_LOG_7 = RUN_GESTURE_7 + [before("g2", LOG), after("g2", LOG_SUCCESS)]
    expected7 = [["git commit -m fix"], []]
    got7 = [
        missing_log(RUN_GESTURE_7, landed=landed_true),
        missing_log(GESTURE_THEN_LOG_7, landed=landed_true),
    ]
    if got7 == expected7:
        print("PASS 7 missing_log landed=true: expected " + repr(expected7) + " got " + repr(got7))
    else:
        print("FAIL 7 missing_log landed=true: expected " + repr(expected7) + " got " + repr(got7))
        failures += 1

    expected7b = [["git commit -m fix"], ["git commit -m fix"]]
    got7b = [
        missing_log(RUN_GESTURE_7, landed=landed_false),
        missing_log(GESTURE_THEN_LOG_7, landed=landed_false),
    ]
    if got7b == expected7b:
        print("PASS 7b missing_log landed=false: expected " + repr(expected7b) + " got " + repr(got7b))
    else:
        print("FAIL 7b missing_log landed=false: expected " + repr(expected7b) + " got " + repr(got7b))
        failures += 1

    # Test 8: git global options in gestures
    # gesture_in returns only the matched gesture portion, not the full command
    expected8 = [
        "git -c commit.gpgsign=false commit",
        "git --no-pager commit",
        "git -C a -C b commit",
        "",
    ]
    got8 = [
        gesture_in("git -c commit.gpgsign=false commit -m x"),
        gesture_in("git --no-pager commit -m x"),
        gesture_in("git -C a -C b commit -m x"),
        gesture_in("git -c k=v status"),
    ]
    if got8 == expected8:
        print("PASS 8 gesture_in git globals: expected " + repr(expected8) + " got " + repr(got8))
    else:
        print("FAIL 8 gesture_in git globals: expected " + repr(expected8) + " got " + repr(got8))
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