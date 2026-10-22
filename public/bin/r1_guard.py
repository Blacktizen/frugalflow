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

COMMIT = re.compile(r"\bgit\s+(?:-C\s+\S+\s+)?commit\b")

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
    missing = r1_rules.missing_log(load_entries(session), exempt)
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


def after(ident):
    return {"event": "tool_after", "tool": "Bash", "id": ident}


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
            session_log.append("s1", before("b2", LOG, base))
            session_log.append("s1", after("b2"))
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
        missing = r1_rules.missing_log(load_entries(session_id), exempt)
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
