#!/usr/bin/env python3
import os
import sys
import re
import json
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_log
import r1_rules
import notes_rules
import r1_guard

TITLE_ARG = re.compile(r"--title\s+(\"[^\"]*\"|'[^']*'|\S+)")


def title_of(command):
    match = TITLE_ARG.search(command)
    if not match:
        return "(no title)"
    value = match.group(1)
    if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
        return value[1:-1]
    return value


def digest(session, entries):
    executed = r1_rules.executed_commands(entries)
    notes = notes_rules.fold_notes(entries)
    gestures = sum(1 for entry, command in executed if r1_rules.gesture_in(command) != "")
    decisions = [(entry, command) for entry, command in executed if r1_rules.is_log_call(command)]
    lines = ["# Session " + session,
             "Events: " + str(len(entries)) + " - gestures: " + str(gestures) + " - decisions: " + str(len(decisions))]
    for entry, command in decisions:
        ts = entry.get("ts", "")
        clock = ts[11:16] if len(ts) >= 16 else "--:--"
        state = notes.get(entry.get("seq"), {}).get("state", notes_rules.OPEN)
        lines.append("- [" + clock + "] seq " + str(entry.get("seq")) + " " + title_of(command) + " (" + state + ")")
    return lines


def vault_touched_without_log(entries, vault):
    target = os.path.normpath(os.path.abspath(os.path.expanduser(vault)))
    touched = False
    logged = False
    for entry, command in r1_rules.executed_commands(entries):
        if r1_rules.gesture_in(command) != "" and os.path.normpath(entry.get("vault", "") or ".") == target:
            touched = True
        for value in r1_rules.log_vaults(command):
            path = os.path.expanduser(value)
            if not os.path.isabs(path):
                path = os.path.join(r1_rules.command_repo(command, entry.get("cwd", "")), path)
            if os.path.normpath(path) == target:
                logged = True
    return touched and not logged


def health(session, entries, vault=None):
    results = []
    code, msg = session_log.check(session)
    results.append(("chain", "" if code == 0 else msg))
    missing = r1_rules.missing_log(entries, r1_guard.exempt)
    results.append(("r1", "" if not missing else str(len(missing)) + " gesture(s) without a log entry"))
    open_seqs = notes_rules.decisions_without_verdict(entries)
    results.append(("verdicts", "" if not open_seqs else "no verdict for decisions " + ", ".join(str(seq) for seq in open_seqs)))
    if vault is not None:
        results.append(("vault", "gesture in this vault without a log entry to it" if vault_touched_without_log(entries, vault) else ""))
    return results


NOTICE = (
    "NAME      session_digest.py - the session log closing pass: a readable digest, then the health checks (chain and anchor, R1, verdicts, vault) and an exit code that says whether the session may close.\n"
    "READS     --session; --vault (optional); the session log and its anchor, through session_log.py.\n"
    "WRITES    nothing: the digest lines, one CHECK line per check, then SESSION HEALTHY (0) or SESSION NOT HEALTHY (6). Exit 2 usage, 3 no log.\n"
    "EXAMPLE   python3 session_digest.py --session 4f1c2a9e --vault ~/projects/demo/vault\n"
    "PITFALLS  2026-09-06 a closing made from memory at the end of the window: the log is read back instead.\n"
    "          A decision without a verdict keeps the session open: put one with session_note.py."
)


def print_usage():
    print("usage: session_digest.py --session SESSION [--vault DIR] | --notice | --autotest")


def run_autotest():
    base = tempfile.mkdtemp()
    try:
        os.environ["FRUGALFLOW_SESSIONS"] = os.path.join(base, "sessions")
        os.environ["FRUGALFLOW_ANCHORS"] = os.path.join(base, "anchors")
        env = dict(os.environ)
        vault = os.path.join(base, "proj", "vault")
        os.makedirs(vault)

        LOG = "python3 journal_add.py --vault " + vault + " --title \"parser fixed\" --field Decision=d"

        def fixture_before(ident, command, cwd, vault_dir):
            return {"ts": "2026-09-26T10:05:00+02:00", "cwd": cwd, "vault": vault_dir,
                    "event": "tool_before", "tool": "Bash", "id": ident,
                    "input": json.dumps({"command": command})}

        def fixture_after(ident):
            return {"ts": "2026-09-26T10:05:01+02:00", "event": "tool_after", "tool": "Bash", "id": ident}

        proofs = []

        # Proof 1: title_of
        try:
            assert title_of('python3 journal_add.py --vault v --title "parser fixed"') == "parser fixed"
            assert title_of("python3 journal_add.py --title short") == "short"
            assert title_of("ls") == "(no title)"
            proofs.append(("title_of", True, "expected exact matches, got all ok"))
        except AssertionError as exc:
            proofs.append(("title_of", False, "expected exact matches, got " + str(exc)))

        # Proof 2: gesture without log
        session_log.append("s1", fixture_before("a1", "git push", os.path.join(base, "proj"), vault))
        session_log.append("s1", fixture_after("a1"))

        proc = subprocess.run([sys.executable, __file__, "--session", "s1", "--vault", vault],
                              capture_output=True, text=True, env=env)
        out2 = proc.stdout
        expected2 = [
            proc.returncode == 6,
            "CHECK r1 FAIL 1 gesture(s) without a log entry" in out2,
            "CHECK vault FAIL gesture in this vault without a log entry to it" in out2,
            "SESSION NOT HEALTHY: 2 check(s) failed" in out2,
            out2 != "",
        ]
        proofs.append(("r1+vault fail", all(expected2),
                       "expected rc=6 with r1/vault FAIL, got rc=" + str(proc.returncode) + " out=" + out2))

        # Proof 3: log call then verdict
        session_log.append("s1", fixture_before("a2", LOG, os.path.join(base, "proj"), vault))
        session_log.append("s1", fixture_after("a2"))

        proc = subprocess.run([sys.executable, __file__, "--session", "s1", "--vault", vault],
                              capture_output=True, text=True, env=env)
        out3a = proc.stdout
        expected3a = [
            proc.returncode == 6,
            "CHECK verdicts FAIL no verdict for decisions 2" in out3a,
            "- [10:05] seq 2 parser fixed (OPEN)" in out3a,
            out3a != "",
        ]

        session_log.append("s1", {"event": "verdict", "target": 2, "state": "DONE", "text": "held"})

        proc = subprocess.run([sys.executable, __file__, "--session", "s1", "--vault", vault],
                              capture_output=True, text=True, env=env)
        out3b = proc.stdout
        expected3b = [
            proc.returncode == 0,
            "- [10:05] seq 2 parser fixed (DONE)" in out3b,
            "CHECK chain OK" in out3b,
            "CHECK r1 OK" in out3b,
            "CHECK verdicts OK" in out3b,
            "CHECK vault OK" in out3b,
            "SESSION HEALTHY" in out3b,
            out3b != "",
        ]
        proofs.append(("verdict flow", all(expected3a) and all(expected3b),
                       "expected rc=6 then rc=0 with verdict lines, got rc_a=" + str(proc.returncode) +
                       " out_a=" + out3a + " out_b=" + out3b))

        # Proof 4: chain broken
        sessions_dir = os.path.join(base, "sessions")
        journal_file = ""
        for sub in os.listdir(sessions_dir):
            candidate = os.path.join(sessions_dir, sub, "s1.jsonl")
            if os.path.exists(candidate):
                journal_file = candidate
                break
        with open(journal_file, "r") as fh:
            content = fh.read()
        content = content.replace("git push", "git pull")
        with open(journal_file, "w") as fh:
            fh.write(content)

        proc = subprocess.run([sys.executable, __file__, "--session", "s1"],
                              capture_output=True, text=True, env=env)
        out4 = proc.stdout
        chain_line = any(line.startswith("CHECK chain FAIL SESSION LOG BROKEN: line 0 was rewritten")
                         for line in out4.splitlines())
        proofs.append(("chain broken", proc.returncode == 6 and chain_line and out4 != "",
                       "expected rc=6 with chain FAIL, got rc=" + str(proc.returncode) + " out=" + out4))

        # Proof 5: cli variants
        proc = subprocess.run([sys.executable, __file__, "--session", "nope"],
                              capture_output=True, text=True, env=env)
        ok5a = proc.returncode == 3 and "NO SESSION LOG nope" in proc.stdout and proc.stdout != ""

        proc = subprocess.run([sys.executable, __file__, "--bogus"],
                              capture_output=True, text=True, env=env)
        ok5b = proc.returncode == 2 and "usage: session_digest.py" in proc.stdout and proc.stdout != ""

        proc = subprocess.run([sys.executable, __file__, "--notice"],
                              capture_output=True, text=True, env=env)
        ok5c = proc.returncode == 0 and proc.stdout.startswith("NAME      session_digest.py") and proc.stdout != ""

        proofs.append(("cli", ok5a and ok5b and ok5c,
                       "expected rc=3/rc=2/rc=0, got " +
                       "nope_out=" + proc.stdout))

        all_pass = True
        for name, passed, detail in proofs:
            if passed:
                print("PASS " + name)
            else:
                all_pass = False
                print("FAIL " + name + " " + detail)

        return 0 if all_pass else 1
    finally:
        shutil.rmtree(base)


def main():
    argv = sys.argv[1:]
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return run_autotest()
    if len(argv) < 1 or argv[0] != "--session":
        print_usage()
        return 2
    if len(argv) < 2:
        print_usage()
        return 2
    session = argv[1]
    vault = None
    if len(argv) >= 3:
        if argv[2] != "--vault":
            print_usage()
            return 2
        if len(argv) < 4:
            print_usage()
            return 2
        vault = argv[3]
        if len(argv) > 4:
            print_usage()
            return 2
    log_file = session_log.log_path(session)
    if not os.path.exists(log_file):
        print("NO SESSION LOG " + session)
        return 3
    entries = r1_guard.load_entries(session)
    for line in digest(session, entries):
        print(line)
    checks = health(session, entries, vault)
    failed = 0
    for name, detail in checks:
        if detail:
            failed += 1
            print("CHECK " + name + " FAIL " + detail)
        else:
            print("CHECK " + name + " OK")
    if failed == 0:
        print("SESSION HEALTHY")
        return 0
    print("SESSION NOT HEALTHY: " + str(failed) + " check(s) failed")
    return 6


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "session_digest", sys.argv[1:])
