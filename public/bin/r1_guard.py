import os
import sys
import re
import json
import tempfile
import shutil
import subprocess
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_log
import r1_rules
import chain_rules

# Use GIT_GLOBAL from r1_rules for commit gesture matching
COMMIT = re.compile(r"\bgit" + r1_rules.GIT_GLOBAL + r"\s+commit\b")


def entry_landed(command, entry, since):
    """Return True if the journal_add call actually landed an entry with the given title.

    Conditions for at least one --vault directory:
    - title (--title) exists and since is parsable (ISO, datetime.fromisoformat)
    - the log.md (find all files named log.md under this directory) has a LAST sealed entry
      whose header is '## [YYYY-MM-DD HH:MM] <title>' with exactly this title
    - this last entry is dated after the gesture: its date YYYY-MM-DD HH:MM, converted to
      local minute, is >= the minute of the since field (same minute accepted)
    - chain_rules.verify(text) returns ok
    - any exception returns False
    The response output is NEVER read. The mtime is not used.
    """
    try:
        title = r1_rules.title_of(command)
        if not title:
            return False

        # Parse since as ISO datetime
        try:
            since_dt = datetime.datetime.fromisoformat(since)
        except Exception:
            return False

        # Convert since to local timezone, then floor to minute (naive for comparison with log entry)
        if since_dt.tzinfo is not None:
            since_dt = since_dt.astimezone()
        since_minute = since_dt.replace(second=0, microsecond=0, tzinfo=None)

        vaults = r1_rules.log_vaults(command)
        if not vaults:
            return False

        cwd = entry.get("cwd", "")
        for vault in vaults:
            vault_path = vault
            if not os.path.isabs(vault_path):
                vault_path = os.path.normpath(os.path.join(cwd, vault_path))

            # Find all log.md files under this vault
            log_files = []
            for root, dirs, files in os.walk(vault_path):
                for f in files:
                    if f == "log.md":
                        log_files.append(os.path.join(root, f))

            if not log_files:
                continue

            for log_file in log_files:
                try:
                    with open(log_file, "r", encoding="utf-8") as handle:
                        content = handle.read()
                except Exception:
                    continue

                # Verify chain
                ok, n, bad, reason = chain_rules.verify(content)
                if not ok:
                    continue

                # Get the last sealed entry
                entries_list = chain_rules.entries(content)
                if not entries_list:
                    continue

                last_entry = entries_list[-1]
                if last_entry["hash"] is None:
                    continue

                # Parse the header of the last entry: ## [YYYY-MM-DD HH:MM] <title>
                body = last_entry["body"]
                header_match = re.match(r"^## \[(\d{4}-\d{2}-\d{2} \d{2}:\d{2})\] (.+)$", body.split("\n")[0])
                if not header_match:
                    continue

                entry_time_str = header_match.group(1)
                entry_title = header_match.group(2)

                # Check exact title match
                if entry_title != title:
                    continue

                # Parse entry time and compare minutes (both naive local time)
                try:
                    entry_dt = datetime.datetime.strptime(entry_time_str, "%Y-%m-%d %H:%M")
                except Exception:
                    continue

                entry_minute = entry_dt.replace(second=0, microsecond=0)
                if entry_minute < since_minute:
                    continue

                # All conditions met
                return True

        return False
    except Exception:
        return False


USAGE = "usage: r1_guard.py [--session SESSION] | --notice | --autotest   (no argument: Stop hook mode, reads the hook payload on stdin)"

NOTICE = (
    "NAME      r1_guard.py - the end-of-turn hook: blocks the end of a turn while a state-changing command ran without a vault log entry after it.\n"
    "READS     the Stop hook payload on stdin; the session log (session_log.py); git log of the repository a commit touched, for the trace-only exemption.\n"
    "WRITES    a block decision on stdout; on a second stop in a row, one line to <sessions>/r1-missing.log instead. Exit 0 hook done or R1 OK, 1 guard down, 2 usage, 6 R1 missing.\n"
    "EXAMPLE   python3 r1_guard.py --session 4f1c2a9e\n"
    "PITFALLS  2026-09-06 55 minutes and 5 commits went by without one log entry, then 8 entries were dumped in 3 minutes.\n"
    "          A guard that crashes blocks, it never lets the turn end in silence; a commit that only carries vault/log.md is exempt, read from git."
)


def load_entries(session):
    entries = []
    for line in session_log.read_lines(session_log.log_path(session)):
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if not isinstance(obj, dict):
            continue
        entries.append(obj)
    return entries


def commit_files(repo, start, end):
    try:
        proc = subprocess.run(
            ["git", "-C", repo, "log", "--since=" + start, "--until=" + end, "--name-only", "--pretty=format:"],
            capture_output=True,
            text=True,
        )
        if proc.returncode != 0:
            return []
    except Exception:
        return []
    lines = []
    for raw in proc.stdout.splitlines():
        stripped = raw.strip()
        if stripped:
            lines.append(stripped)
    return lines


def exempt(command, entry):
    try:
        effective = r1_rules.effective_command(command)
        count = 0
        for pattern in r1_rules.GESTURES:
            count += len(re.findall(pattern, effective))
        if count != 1:
            return False
        if len(COMMIT.findall(effective)) != 1:
            return False
        moment = datetime.datetime.fromisoformat(entry["ts"])
        repo = r1_rules.command_repo(command, entry.get("cwd", ""))
        files = commit_files(
            repo,
            (moment - datetime.timedelta(seconds=5)).isoformat(),
            (moment + datetime.timedelta(seconds=120)).isoformat(),
        )
        return r1_rules.trace_only(files)
    except Exception:
        return False


def reason(missing):
    return "R1 MISSING: " + str(len(missing)) + " gesture(s) without a log entry: " + " | ".join(missing[-5:]) + ". Run journal_add.py --vault <project vault>, then finish."


def run_hook(text):
    payload = json.loads(text)
    session = payload["session_id"]
    missing = r1_rules.missing_log(load_entries(session), exempt, landed=entry_landed)
    if not missing:
        return ""
    if payload.get("stop_hook_active"):
        os.makedirs(session_log.sessions_root(), exist_ok=True)
        stamp = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
        line = stamp + " " + session + " " + reason(missing) + "\n"
        target = os.path.join(session_log.sessions_root(), "r1-missing.log")
        with open(target, "a") as handle:
            handle.write(line)
        return ""
    return json.dumps({"decision": "block", "reason": reason(missing)})


LOG = "python3 public/bin/journal_add.py --vault /w/vault --title t --field Decision=d"


def before(ident, command, cwd):
    return {"ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"), "cwd": cwd, "event": "tool_before", "tool": "Bash", "id": ident, "input": json.dumps({"command": command})}


def after(ident, response=""):
    entry = {"event": "tool_after", "tool": "Bash", "id": ident}
    if response:
        entry["response"] = response
    return entry


def autotest():
    base = tempfile.mkdtemp()
    os.environ["FRUGALFLOW_SESSIONS"] = os.path.join(base, "sessions")
    os.environ["FRUGALFLOW_ANCHORS"] = os.path.join(base, "anchors")
    env = dict(os.environ)
    results = []

    try:
        repo = os.path.join(base, "repo")
        os.makedirs(os.path.join(repo, "vault"))
        subprocess.run(["git", "init", "-q"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "config", "user.email", "t@t"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "config", "user.name", "t"], cwd=repo, check=True, env=env)

        s1_ok = True
        try:
            session_log.append("s1", before("b1", "git push", base))
            session_log.append("s1", after("b1"))
        except Exception:
            s1_ok = False

        # Test 1
        if not s1_ok:
            results.append(("FAIL", "test1 exempt trace/trace+push", "s1 log missing"))
        else:
            with open(os.path.join(repo, "vault", "log.md"), "w") as handle:
                handle.write("x\n")
            subprocess.run(["git", "add", "vault/log.md"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "commit", "-q", "-m", "trace"], cwd=repo, check=True, env=env)
            r1 = exempt("git commit -m trace", before("a1", "git commit -m trace", repo))
            r2 = exempt("git commit -m trace && git push", before("a2", "git commit -m trace && git push", repo))
            if r1 is True and r2 is False:
                results.append(("PASS", "test1 exempt trace=True trace+push=False", "True/False"))
            else:
                results.append(("FAIL", "test1 exempt trace=True trace+push=False", "got " + str(r1) + "/" + str(r2)))

        # Test 2
        if not s1_ok:
            results.append(("FAIL", "test2 exempt code=False", "s1 log missing"))
        else:
            with open(os.path.join(repo, "code.py"), "w") as handle:
                handle.write("y\n")
            subprocess.run(["git", "add", "code.py"], cwd=repo, check=True, env=env)
            subprocess.run(["git", "commit", "-q", "-m", "code"], cwd=repo, check=True, env=env)
            r3 = exempt("git commit -m code", before("a3", "git commit -m code", repo))
            if r3 is False:
                results.append(("PASS", "test2 exempt code=False", "False"))
            else:
                results.append(("FAIL", "test2 exempt code=False", "got " + str(r3)))

        # Test 3
        if not s1_ok:
            results.append(("FAIL", "test3 hook block + r1-missing.log", "s1 log missing"))
        else:
            payload_a = json.dumps({"session_id": "s1"})
            proc_a = subprocess.run([sys.executable, __file__], input=payload_a, capture_output=True, text=True, env=env)
            payload_b = json.dumps({"session_id": "s1", "stop_hook_active": True})
            proc_b = subprocess.run([sys.executable, __file__], input=payload_b, capture_output=True, text=True, env=env)
            miss_log_path = os.path.join(base, "sessions", "r1-missing.log")
            line_count = 0
            if os.path.exists(miss_log_path):
                with open(miss_log_path) as handle:
                    line_count = len(handle.readlines())
            ok_a = proc_a.returncode == 0 and '"decision": "block"' in proc_a.stdout and "R1 MISSING: 1 gesture(s)" in proc_a.stdout
            ok_b = proc_b.returncode == 0 and proc_b.stdout == "" and line_count == 1
            if ok_a and ok_b:
                results.append(("PASS", "test3 hook block + r1-missing.log 1 line", "0/block/0//1"))
            else:
                results.append(("FAIL", "test3 hook block + r1-missing.log 1 line",
                                "a:" + str(proc_a.returncode) + " b:" + str(proc_b.returncode) + " lines:" + str(line_count)))

        # Test 4
        if not s1_ok:
            results.append(("FAIL", "test4 session 6 then 0 then hook empty", "s1 log missing"))
        else:
            proc_4a = subprocess.run([sys.executable, __file__, "--session", "s1"], capture_output=True, text=True, env=env)
            ok_4a = proc_4a.returncode == 6 and "R1 MISSING: 1" in proc_4a.stdout

            # Create a valid vault with a proper log.md for the real journal_add.py call
            valid_vault = os.path.join(base, "valid_vault")
            os.makedirs(os.path.join(valid_vault, "vault"))
            # Write a genesis entry to log.md so journal_add.py can append to it
            genesis_entry = chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
            with open(os.path.join(valid_vault, "vault", "log.md"), "w") as handle:
                handle.write("# Log\n\n" + genesis_entry)

            # Run REAL journal_add.py to the valid vault and capture its output
            journal_add_path = os.path.join(os.path.dirname(__file__), "journal_add.py")
            proc_journal = subprocess.run(
                [sys.executable, journal_add_path, "--vault", os.path.join(valid_vault, "vault"), "--title", "t1", "--field", "Decision=d"],
                capture_output=True, text=True, env=env
            )
            journal_output = proc_journal.stdout.strip()

            session_log.append("s1", before("b2", "python3 " + journal_add_path + " --vault " + os.path.join(valid_vault, "vault") + " --title t1 --field Decision=d", base))
            session_log.append("s1", after("b2", journal_output))

            proc_4b = subprocess.run([sys.executable, __file__, "--session", "s1"], capture_output=True, text=True, env=env)
            ok_4b = proc_4b.returncode == 0 and "R1 OK s1" in proc_4b.stdout
            proc_4c = subprocess.run([sys.executable, __file__], input=json.dumps({"session_id": "s1"}), capture_output=True, text=True, env=env)
            ok_4c = proc_4c.returncode == 0 and proc_4c.stdout == ""
            if ok_4a and ok_4b and ok_4c:
                results.append(("PASS", "test4 session 6->0 hook empty", "6/0/empty"))
            else:
                results.append(("FAIL", "test4 session 6->0 hook empty",
                                "4a:" + str(proc_4a.returncode) + " 4b:" + str(proc_4b.returncode) + " 4c:" + str(proc_4c.returncode)))

        # Test 5
        if not s1_ok:
            results.append(("FAIL", "test5 notice/bogus/bad-json", "s1 log missing"))
        else:
            proc_5a = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True, env=env)
            ok_5a = proc_5a.returncode == 0 and proc_5a.stdout.startswith("NAME      r1_guard.py")
            proc_5b = subprocess.run([sys.executable, __file__, "--bogus"], capture_output=True, text=True, env=env)
            ok_5b = proc_5b.returncode == 2 and "usage: r1_guard.py" in proc_5b.stdout
            proc_5c = subprocess.run([sys.executable, __file__], input="not json", capture_output=True, text=True, env=env)
            ok_5c = proc_5c.returncode == 1 and "block" in proc_5c.stdout and "R1 GUARD DOWN: " in proc_5c.stderr
            if ok_5a and ok_5b and ok_5c:
                results.append(("PASS", "test5 notice/bogus/bad-json", "0/2/1"))
            else:
                results.append(("FAIL", "test5 notice/bogus/bad-json",
                                "5a:" + str(proc_5a.returncode) + " 5b:" + str(proc_5b.returncode) + " 5c:" + str(proc_5c.returncode)))

        # Test 6: entry_landed with explicit true/false scenarios
        # Create a vault with a genesis entry and a sealed entry
        test_vault = os.path.join(base, "test_vault")
        os.makedirs(os.path.join(test_vault, "vault"))
        genesis_entry = chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
        entry1 = chain_rules.render(chain_rules.entry_hash(chain_rules.GENESIS, genesis_entry.split("<!--")[0]), "2026-09-26 10:00", "my title", [("Decision", "d")])
        with open(os.path.join(test_vault, "vault", "log.md"), "w") as handle:
            handle.write("# Log\n\n" + genesis_entry + "\n" + entry1)

        # entry_landed should return True for matching title and time
        test_entry = {"ts": "2026-09-26T09:59:00+02:00", "cwd": base}
        test_command = "python3 journal_add.py --vault " + os.path.join(test_vault, "vault") + " --title \"my title\" --field Decision=d"
        r6a = entry_landed(test_command, test_entry, "2026-09-26T09:59:00+02:00")

        # entry_landed should return False for non-matching title
        test_command2 = "python3 journal_add.py --vault " + os.path.join(test_vault, "vault") + " --title \"other title\" --field Decision=d"
        r6b = entry_landed(test_command2, test_entry, "2026-09-26T09:59:00+02:00")

        # entry_landed should return False for time before gesture
        test_entry3 = {"ts": "2026-09-26T10:01:00+02:00", "cwd": base}
        r6c = entry_landed(test_command, test_entry3, "2026-09-26T10:01:00+02:00")

        if r6a is True and r6b is False and r6c is False:
            results.append(("PASS", "test6 entry_landed true/false/false", "True/False/False"))
        else:
            results.append(("FAIL", "test6 entry_landed true/false/false", "got " + str(r6a) + "/" + str(r6b) + "/" + str(r6c)))

        # Test 7: git global options in exempt (commit gesture recognition)
        # Wait to ensure previous commits are outside the 5-second time window
        import time
        time.sleep(6)
        # These should be recognized as commit gestures (exempt checks trace_only)
        with open(os.path.join(repo, "vault", "log.md"), "w") as handle:
            handle.write("y\n")
        subprocess.run(["git", "add", "vault/log.md"], cwd=repo, check=True, env=env)
        subprocess.run(["git", "commit", "-q", "-m", "trace2"], cwd=repo, check=True, env=env)

        r7a = exempt("git -c commit.gpgsign=false commit -m trace", before("a7a", "git -c commit.gpgsign=false commit -m trace", repo))
        r7b = exempt("git --no-pager commit -m trace", before("a7b", "git --no-pager commit -m trace", repo))
        # This should NOT be a commit gesture
        r7c = exempt("git -c k=v status", before("a7c", "git -c k=v status", repo))

        if r7a is True and r7b is True and r7c is False:
            results.append(("PASS", "test7 exempt git globals", "True/True/False"))
        else:
            results.append(("FAIL", "test7 exempt git globals", "got " + str(r7a) + "/" + str(r7b) + "/" + str(r7c)))

    finally:
        for status, expected, got in results:
            print(status + " " + expected + " [" + got + "]")
        shutil.rmtree(base, ignore_errors=True)

    all_pass = all(status == "PASS" for status, _, _ in results)
    sys.exit(0 if all_pass else 1)


def main():
    args = sys.argv[1:]

    if not args:
        text = sys.stdin.read()
        try:
            out = run_hook(text)
            if out:
                print(out)
            sys.exit(0)
        except Exception as exc:
            suppress_stdout = False
            try:
                payload = json.loads(text)
                if payload.get("stop_hook_active"):
                    suppress_stdout = True
            except Exception:
                pass
            if not suppress_stdout:
                print(json.dumps({"decision": "block", "reason": "R1 GUARD DOWN: " + str(exc)}))
            print("R1 GUARD DOWN: " + str(exc), file=sys.stderr)
            sys.exit(1)

    if args[0] == "--session":
        if len(args) < 2:
            print(USAGE)
            sys.exit(2)
        session_id = args[1]
        missing = r1_rules.missing_log(load_entries(session_id), exempt, landed=entry_landed)
        if not missing:
            print("R1 OK " + session_id)
            sys.exit(0)
        else:
            print(reason(missing))
            sys.exit(6)

    if args[0] == "--notice":
        print(NOTICE)
        sys.exit(0)

    if args[0] == "--autotest":
        autotest()
        return

    print(USAGE)
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "r1_guard", sys.argv[1:])