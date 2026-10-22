#!/usr/bin/env python3
"""Claude Code hook: writes each session event as one sealed line, keeps the head apart, checks a log."""

import os
import sys
import json
import glob
import fcntl
import tempfile
import shutil
import subprocess
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_chain
import session_event


def sessions_root():
    val = os.environ.get("FRUGALFLOW_SESSIONS")
    if val:
        return val
    # FRUGALFLOW_HOME now routes the log; FRUGALFLOW_SESSIONS still wins.
    home = os.environ.get("FRUGALFLOW_HOME")
    if home:
        return os.path.join(home, "sessions")
    return os.path.join(os.path.expanduser("~"), ".frugalflow", "sessions")


def anchors_root():
    val = os.environ.get("FRUGALFLOW_ANCHORS")
    if val:
        return val
    return sessions_root().rstrip("/") + "-anchors"


def log_path(session):
    matches = sorted(glob.glob(os.path.join(sessions_root(), "*", session + ".jsonl")))
    if matches:
        return matches[0]
    return os.path.join(sessions_root(), datetime.datetime.now().strftime("%Y-%m-%d"), session + ".jsonl")


def anchor_path(session):
    return os.path.join(anchors_root(), session + ".head.json")


def read_lines(path):
    if not os.path.exists(path):
        return []
    with open(path, "r", encoding="utf-8") as fh:
        return [line.rstrip("\n") for line in fh]


def read_anchor(session):
    apath = anchor_path(session)
    if not os.path.exists(apath):
        return None
    with open(apath, "r", encoding="utf-8") as fh:
        return json.load(fh)


def find_vault(cwd):
    if not cwd:
        return ""
    current = os.path.abspath(cwd)
    while True:
        candidate = os.path.join(current, "vault")
        if os.path.isdir(candidate):
            return os.path.normpath(candidate)
        parent = os.path.dirname(current)
        if parent == current:
            return ""
        current = parent


def append(session, entry):
    path = log_path(session)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    handle = open(path, "a+", encoding="utf-8")
    try:
        fcntl.flock(handle, fcntl.LOCK_EX)
        handle.seek(0)
        lines = [line for line in handle if line.strip()]
        last = None
        if lines:
            last = json.loads(lines[-1])
        line = session_chain.seal(last, entry)
        handle.seek(0, 2)
        handle.write(session_chain.canonical(line) + "\n")
        handle.flush()
        fcntl.flock(handle, fcntl.LOCK_UN)
    finally:
        handle.close()
    os.makedirs(anchors_root(), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=anchors_root())
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmpf:
            tmpf.write(json.dumps({"seq": line["seq"], "hash": line["hash"]}))
        os.replace(tmp, anchor_path(session))
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise
    return line


def check(session):
    path = log_path(session)
    if not os.path.exists(path):
        return (3, "SESSION LOG MISSING " + session)
    lines = read_lines(path)
    ok, n, bad, reason = session_chain.verify(lines)
    if not ok:
        return (6, "SESSION LOG BROKEN: " + reason)
    anchor = read_anchor(session)
    if anchor is None and n > 0:
        return (6, "SESSION LOG BROKEN: anchor MISSING")
    verdict = session_chain.anchor_verdict(anchor, lines)
    if verdict in ("TRUNCATED", "REWRITTEN"):
        return (6, "SESSION LOG BROKEN: anchor " + verdict)
    return (0, "SESSION LOG OK " + str(n) + " lines, anchor " + verdict)


def run_hook(text):
    payload = json.loads(text)
    if not isinstance(payload, dict):
        raise ValueError("payload is not a JSON object")
    session = payload.get("session_id", "")
    if not session:
        raise ValueError("no session_id")
    transcript_lines = []
    if payload.get("hook_event_name") == "Stop":
        tpath = payload.get("transcript_path", "")
        if tpath and os.path.isfile(tpath):
            transcript_lines = read_lines(tpath)
    now = datetime.datetime.now().astimezone().isoformat(timespec="seconds")
    entry = session_event.build(payload, now, find_vault(payload.get("cwd", "")), transcript_lines)
    return append(session, entry)


_NOTICE = (
    "NAME      session_log.py - the Claude Code hook that writes every session event as one sealed line of the session log, keeps the log head apart, and checks a log.\n"
    "READS     the hook payload on stdin; its transcript on Stop; FRUGALFLOW_SESSIONS (default $FRUGALFLOW_HOME/sessions, else ~/.frugalflow/sessions) and FRUGALFLOW_ANCHORS (default the same path + \"-anchors\").\n"
    "WRITES    one line to <sessions>/<date>/<session>.jsonl and the head to <anchors>/<session>.head.json; errors.log on failure. Exit 0 written or log OK, 1 hook down, 2 usage, 3 log missing, 6 log broken.\n"
    "EXAMPLE   python3 session_log.py --check 4f1c2a9e\n"
    "PITFALLS  2026-09-19 the log is the only proof of what the session did: a line rewritten, removed or cut at the end is reported, never repaired.\n"
    "          A failing hook exits 1 and writes errors.log: it never fails in silence.\n"
)

_USAGE = "usage: session_log.py [--check SESSION] | --notice | --autotest   (no argument: hook mode, reads the hook payload on stdin)"


def _autotest():
    START = {"session_id": "s1", "cwd": "", "hook_event_name": "SessionStart", "source": "startup"}
    BEFORE = {"session_id": "s1", "cwd": "", "hook_event_name": "PreToolUse", "tool_name": "Bash", "tool_use_id": "t1", "tool_input": {"command": "git status"}}

    base = tempfile.mkdtemp()
    # HOME and FRUGALFLOW_HOME are pinned to base so the new block lines stay inside the temporary working folder.
    base2 = tempfile.mkdtemp()
    env = dict(os.environ, HOME=base, FRUGALFLOW_HOME=os.path.join(base, "home"), FRUGALFLOW_SESSIONS=os.path.join(base, "sessions"), FRUGALFLOW_ANCHORS=os.path.join(base, "anchors"))
    results = []

    try:
        # Test 1: find_vault
        os.makedirs(os.path.join(base, "proj", "vault"))
        os.makedirs(os.path.join(base, "proj", "src", "deep"))
        expected_vault = os.path.normpath(os.path.join(base, "proj", "vault"))
        got_vault = find_vault(os.path.join(base, "proj", "src", "deep"))
        got_empty = find_vault("")
        if got_vault == expected_vault and got_empty == "":
            results.append("PASS 1: find_vault")
        else:
            results.append("FAIL 1: find_vault expected vault=" + expected_vault + " empty='' got vault=" + repr(got_vault) + " empty=" + repr(got_empty))

        # Test 2: hook mode writes two sealed lines
        proc_a = subprocess.run([sys.executable, os.path.abspath(__file__)], input=json.dumps(START), capture_output=True, text=True, env=env)
        proc_b = subprocess.run([sys.executable, os.path.abspath(__file__)], input=json.dumps(BEFORE), capture_output=True, text=True, env=env)
        log_matches = glob.glob(os.path.join(base, "sessions", "*", "s1.jsonl"))
        if log_matches:
            raw_lines = read_lines(log_matches[0])
            non_empty = [l for l in raw_lines if l.strip()]
            second = json.loads(non_empty[1]) if len(non_empty) >= 2 else {}
        else:
            non_empty = []
            second = {}
        cond = (
            proc_a.returncode == 0
            and proc_b.returncode == 0
            and len(non_empty) == 2
            and second.get("seq") == 1
            and second.get("event") == "tool_before"
            and second.get("session") == "s1"
        )
        if cond:
            results.append("PASS 2: hook mode writes 2 lines, seq=1, event=tool_before")
        else:
            results.append("FAIL 2: hook mode expected rc=0/0, 2 lines, seq=1, event=tool_before, session=s1 got rc=" + str(proc_a.returncode) + "/" + str(proc_b.returncode) + " lines=" + str(len(non_empty)) + " second=" + repr(second))

        # Test 3: --check s1 passes
        proc_c = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "s1"], capture_output=True, text=True, env=env)
        expected_prefix = "SESSION LOG OK 2 lines, anchor INTACT"
        if proc_c.returncode == 0 and proc_c.stdout.startswith(expected_prefix):
            results.append("PASS 3: --check s1 exits 0 with INTACT")
        else:
            results.append("FAIL 3: --check s1 expected rc=0 stdout starts with '" + expected_prefix + "' got rc=" + str(proc_c.returncode) + " stdout=" + repr(proc_c.stdout[:80]))

        # Test 4: alteration, truncation, unknown session
        log_file = log_matches[0]
        with open(log_file, "r", encoding="utf-8") as fh:
            original = fh.read()

        # 4a: rewrite first line
        modified = original.replace("startup", "resume", 1)
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write(modified)
        proc_d1 = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "s1"], capture_output=True, text=True, env=env)
        cond_4a = proc_d1.returncode == 6 and "SESSION LOG BROKEN: line 0 was rewritten" in proc_d1.stdout

        # 4b: truncate to first line only
        first_line = original.split("\n")[0] + "\n"
        with open(log_file, "w", encoding="utf-8") as fh:
            fh.write(first_line)
        proc_d2 = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "s1"], capture_output=True, text=True, env=env)
        cond_4b = proc_d2.returncode == 6 and "anchor TRUNCATED" in proc_d2.stdout

        # 4c: unknown session
        proc_d3 = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "unknown"], capture_output=True, text=True, env=env)
        cond_4c = proc_d3.returncode == 3 and "SESSION LOG MISSING unknown" in proc_d3.stdout

        if cond_4a and cond_4b and cond_4c:
            results.append("PASS 4: rewritten=6, truncated=6, unknown=3")
        else:
            details = "4a=" + str(cond_4a) + "(rc=" + str(proc_d1.returncode) + " out=" + repr(proc_d1.stdout[:60]) + ") 4b=" + str(cond_4b) + "(rc=" + str(proc_d2.returncode) + " out=" + repr(proc_d2.stdout[:60]) + ") 4c=" + str(cond_4c) + "(rc=" + str(proc_d3.returncode) + " out=" + repr(proc_d3.stdout[:60]) + ")"
            results.append("FAIL 4: expected rewritten=6, truncated=6, unknown=3 got " + details)

        # Test 5: --notice, --bogus, invalid JSON
        proc_e1 = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True, env=env)
        proc_e2 = subprocess.run([sys.executable, os.path.abspath(__file__), "--bogus"], capture_output=True, text=True, env=env)
        proc_e3 = subprocess.run([sys.executable, os.path.abspath(__file__)], input="not json", capture_output=True, text=True, env=env)
        cond_5 = (
            proc_e1.returncode == 0
            and proc_e1.stdout.startswith("NAME      session_log.py")
            and proc_e2.returncode == 2
            and "usage: session_log.py" in proc_e2.stdout
            and proc_e3.returncode == 1
            and "SESSION LOG DOWN: " in proc_e3.stderr
        )
        if cond_5:
            results.append("PASS 5: notice=0, bogus=2, bad-json=1")
        else:
            details = "notice_rc=" + str(proc_e1.returncode) + " bogus_rc=" + str(proc_e2.returncode) + " bad_rc=" + str(proc_e3.returncode) + " bad_err=" + repr(proc_e3.stderr[:60])
            results.append("FAIL 5: expected notice=0, bogus=2, bad-json=1 got " + details)

        # Test 6: FRUGALFLOW_HOME routes log and anchors; nothing under ~/.frugalflow; a clean hook writes no refusal line.
        home2 = os.path.join(base2, "home")
        env2 = dict(os.environ, HOME=base2, FRUGALFLOW_HOME=home2)
        env2.pop("FRUGALFLOW_SESSIONS", None)
        env2.pop("FRUGALFLOW_ANCHORS", None)
        proc_f = subprocess.run([sys.executable, os.path.abspath(__file__)], input=json.dumps(START), capture_output=True, text=True, env=env2)
        log2 = glob.glob(os.path.join(home2, "sessions", "*", "s1.jsonl"))
        anchor2 = glob.glob(os.path.join(home2, "sessions-anchors", "s1.head.json"))
        blocks2 = os.path.join(home2, "blocks", "session_log.jsonl")
        stray = os.path.exists(os.path.join(base2, ".frugalflow"))
        cond_6 = (
            proc_f.returncode == 0
            and len(log2) == 1
            and len(anchor2) == 1
            and not stray
            and len(read_lines(blocks2)) == 0
        )
        if cond_6:
            results.append("PASS 6: FRUGALFLOW_HOME routes log+anchor, no ~/.frugalflow, 0 refusal lines")
        else:
            results.append("FAIL 6: expected rc=0, 1 log under home/sessions, 1 anchor under home/sessions-anchors, no ~/.frugalflow, 0 block lines, got rc=" + str(proc_f.returncode) + " log=" + str(len(log2)) + " anchor=" + str(len(anchor2)) + " stray=" + str(stray) + " blocks=" + str(len(read_lines(blocks2))))

        # Test 7: refusals are logged exit_3, exit_2, exit_1; errors.log under home/sessions; notice stays silent.
        proc_g1 = subprocess.run([sys.executable, os.path.abspath(__file__), "--check", "unknown"], capture_output=True, text=True, env=env2)
        proc_g2 = subprocess.run([sys.executable, os.path.abspath(__file__), "--bogus"], capture_output=True, text=True, env=env2)
        proc_g3 = subprocess.run([sys.executable, os.path.abspath(__file__)], input="not json", capture_output=True, text=True, env=env2)
        proc_g4 = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True, env=env2)
        rules = []
        for line in read_lines(blocks2):
            try:
                rules.append(json.loads(line).get("rule"))
            except ValueError:
                rules.append(None)
        cond_7 = (
            proc_g1.returncode == 3
            and proc_g2.returncode == 2
            and proc_g3.returncode == 1
            and proc_g4.returncode == 0
            and "SESSION LOG DOWN: " in proc_g3.stderr
            and os.path.isfile(os.path.join(home2, "sessions", "errors.log"))
            and rules == ["exit_3", "exit_2", "exit_1"]
            and "FRUGALFLOW_HOME" in proc_g4.stdout
        )
        if cond_7:
            results.append("PASS 7: check-unknown=3 exit_3, bogus=2 exit_2, bad-json=1 exit_1 + errors.log, notice=0 no line")
        else:
            results.append("FAIL 7: expected rc 3/2/1/0, SESSION LOG DOWN on bad-json stderr, errors.log under home/sessions, rules ['exit_3', 'exit_2', 'exit_1'], notice with FRUGALFLOW_HOME, got rc=" + str(proc_g1.returncode) + "/" + str(proc_g2.returncode) + "/" + str(proc_g3.returncode) + "/" + str(proc_g4.returncode) + " err=" + repr(proc_g3.stderr[:60]) + " errors.log=" + str(os.path.isfile(os.path.join(home2, "sessions", "errors.log"))) + " rules=" + repr(rules) + " notice_home=" + str("FRUGALFLOW_HOME" in proc_g4.stdout))

    finally:
        shutil.rmtree(base, ignore_errors=True)
        shutil.rmtree(base2, ignore_errors=True)

    for line in results:
        print(line)
    return 0 if all(r.startswith("PASS") for r in results) else 1


def _main():
    args = sys.argv[1:]
    if len(args) == 0:
        text = sys.stdin.read()
        try:
            run_hook(text)
        except Exception as exc:
            msg = "SESSION LOG DOWN: " + str(exc)
            print(msg, file=sys.stderr)
            try:
                err_path = os.path.join(sessions_root(), "errors.log")
                os.makedirs(os.path.dirname(err_path), exist_ok=True)
                with open(err_path, "a", encoding="utf-8") as ef:
                    ef.write(datetime.datetime.now().isoformat(timespec="seconds") + " " + msg + "\n")
            except Exception:
                pass
            sys.exit(1)
        sys.exit(0)
    elif args[0] == "--check":
        if len(args) < 2:
            print(_USAGE)
            sys.exit(2)
        code, message = check(args[1])
        print(message)
        sys.exit(code)
    elif args[0] == "--notice":
        print(_NOTICE, end="")
        sys.exit(0)
    elif args[0] == "--autotest":
        sys.exit(_autotest())
    else:
        print(_USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_main, "session_log", sys.argv[1:])
