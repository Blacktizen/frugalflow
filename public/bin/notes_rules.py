import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import r1_rules

STATES = ("DONE", "FAILED", "DROPPED")
OPEN = "OPEN"


def valid_target(value):
    """Return True if value is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def fold_notes(entries):
    """Fold comment and verdict events into a notes dict keyed by target."""
    notes = {}
    for entry in entries:
        if entry.get("event") in ("comment", "verdict") and valid_target(entry.get("target")):
            target = entry["target"]
            if target not in notes:
                notes[target] = {"comments": [], "state": OPEN, "conclusion": ""}
            notes[target]["comments"].append(entry.get("text", ""))
            if entry["event"] == "verdict":
                notes[target]["state"] = entry.get("state", "")
                notes[target]["conclusion"] = entry.get("text", "")
    return notes


def decisions_without_verdict(entries):
    """Return sorted list of seq numbers for executed log calls lacking a verdict."""
    judged = set()
    for entry in entries:
        if entry.get("event") == "verdict" and valid_target(entry.get("target")):
            judged.add(entry["target"])
    kept = []
    for entry, command in r1_rules.executed_commands(entries):
        seq = entry.get("seq")
        if valid_target(seq) and r1_rules.is_log_call(command) and seq not in judged:
            kept.append(seq)
    return sorted(kept)


_NOTICE = (
    "NAME      notes_rules.py - reads back the comments and verdicts put on a session log action, and lists the decisions that never got a verdict.\n"
    "READS     nothing: pure module; the caller passes the log events, with r1_rules.py beside it.\n"
    "WRITES    nothing: fold_notes() returns the notes by target; decisions_without_verdict() the sequence numbers still open.\n"
    "EXAMPLE   python3 notes_rules.py --notice\n"
    "PITFALLS  2026-09-20 a decision without a verdict stayed open forever: its conclusion is now an event, never left empty by chance.\n"
    "          A later verdict replaces an earlier one; every comment is kept.\n"
)


def _autotest():
    """Run the five test cases; print one PASS/FAIL line per case; return exit code."""

    def before(seq, ident, command):
        return {"seq": seq, "event": "tool_before", "tool": "Bash", "id": ident, "input": json.dumps({"command": command})}

    def after(seq, ident):
        return {"seq": seq, "event": "tool_after", "tool": "Bash", "id": ident}

    LOG = "python3 public/bin/journal_add.py --vault /w/vault --title t --field Decision=d"
    NOISE = [{"event": "comment", "text": "no target"}, {"event": "comment", "target": "twelve", "text": "bad target"}, {"event": "comment", "target": True, "text": "bool target"}]
    TWO_VERDICTS = [
        {"event": "comment", "target": 12, "text": "first try"},
        {"event": "verdict", "target": 12, "state": "DONE", "text": "it works"},
        {"event": "comment", "target": 12, "text": "looked again"},
        {"event": "verdict", "target": 12, "state": "DROPPED", "text": "false green"},
    ]
    DECISIONS = [
        before(10, "a1", LOG), after(11, "a1"),
        before(20, "b2", LOG), after(21, "b2"),
        before(30, "c3", LOG),
        before(40, "d4", "git status"), after(41, "d4"),
        before(60, "f6", "grep -o journal_add.py j.jsonl"), after(61, "f6"),
        before(80, "h8", "cd /tmp && python3 bin/journal_add.py --title t"), after(81, "h8"),
    ]
    V10 = {"event": "verdict", "target": 10, "state": "DONE", "text": "held"}
    V99 = {"event": "verdict", "target": 99, "state": "DONE", "text": "targets nothing"}

    all_pass = True

    # Test 1
    guard = fold_notes([])
    if not isinstance(guard, dict):
        print("FAIL test1 fold_notes([]) is not a dict")
        return 1
    expected = ({}, {}, [])
    got = (fold_notes([]), fold_notes(NOISE), decisions_without_verdict([]))
    if got == expected:
        print("PASS test1 fold_notes and decisions_without_verdict on empty/noise")
    else:
        print("FAIL test1 expected=" + repr(expected) + " got=" + repr(got))
        all_pass = False

    # Test 2
    guard = fold_notes([])
    if not isinstance(guard, dict):
        print("FAIL test2 fold_notes([]) is not a dict")
        return 1
    expected = {12: {"comments": ["first try", "it works", "looked again", "false green"], "state": "DROPPED", "conclusion": "false green"}}
    got = fold_notes(TWO_VERDICTS)
    if got == expected:
        print("PASS test2 fold_notes on TWO_VERDICTS")
    else:
        print("FAIL test2 expected=" + repr(expected) + " got=" + repr(got))
        all_pass = False

    # Test 3
    guard = fold_notes([])
    if not isinstance(guard, dict):
        print("FAIL test3 fold_notes([]) is not a dict")
        return 1
    expected = {7: {"comments": ["noted"], "state": "OPEN", "conclusion": ""}}
    got = fold_notes([{"event": "comment", "target": 7, "text": "noted"}])
    if got == expected:
        print("PASS test3 fold_notes on single comment")
    else:
        print("FAIL test3 expected=" + repr(expected) + " got=" + repr(got))
        all_pass = False

    # Test 4
    guard = fold_notes([])
    if not isinstance(guard, dict):
        print("FAIL test4 fold_notes([]) is not a dict")
        return 1
    expected = ([10, 20, 80], [20, 80], [10, 20, 80])
    got = (
        decisions_without_verdict(DECISIONS),
        decisions_without_verdict(DECISIONS + [V10]),
        decisions_without_verdict(DECISIONS + [V99]),
    )
    if got == expected:
        print("PASS test4 decisions_without_verdict on DECISIONS")
    else:
        print("FAIL test4 expected=" + repr(expected) + " got=" + repr(got))
        all_pass = False

    # Test 5: subprocess
    guard = fold_notes([])
    if not isinstance(guard, dict):
        print("FAIL test5 fold_notes([]) is not a dict")
        return 1
    proc_notice = subprocess.run([sys.executable, __file__, "--notice"], capture_output=True, text=True)
    proc_bogus = subprocess.run([sys.executable, __file__, "--bogus"], capture_output=True, text=True)
    ok5 = (
        proc_notice.returncode == 0
        and proc_notice.stdout.startswith("NAME      notes_rules.py")
        and proc_bogus.returncode == 2
        and "usage: notes_rules.py" in proc_bogus.stdout
    )
    if ok5:
        print("PASS test5 subprocess --notice and --bogus")
    else:
        print(
            "FAIL test5 notice_rc=" + str(proc_notice.returncode)
            + " notice_out=" + repr(proc_notice.stdout[:80])
            + " bogus_rc=" + str(proc_bogus.returncode)
            + " bogus_out=" + repr(proc_bogus.stdout[:80])
        )
        all_pass = False

    return 0 if all_pass else 1


def _cli():
        if len(sys.argv) == 2 and sys.argv[1] == "--notice":
            sys.stdout.write(_NOTICE)
            sys.exit(0)
        elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
            sys.exit(_autotest())
        else:
            sys.stdout.write("usage: notes_rules.py --notice | --autotest\n")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "notes_rules", sys.argv[1:])
