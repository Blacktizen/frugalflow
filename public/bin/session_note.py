import os
import sys
import json
import tempfile
import shutil
import subprocess
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import session_log
import session_chain
import notes_rules

USAGE = "usage: session_note.py --session SESSION --target N --text TEXT [--state DONE|FAILED|DROPPED] | --notice | --autotest"

NOTICE = (
    "NAME      session_note.py - puts a comment, or a verdict (DONE, FAILED, DROPPED), on an action already in the session log, as one more sealed line.\n"
    "READS     --session, --target (the seq of the action), --text, --state; the session log found by session_log.py.\n"
    "WRITES    one sealed line at the end of the session log; a broken chain is refused, nothing written. Exit 0 added, 2 usage, 3 no log, 4 chain broken.\n"
    "EXAMPLE   python3 session_note.py --session 4f1c2a9e --target 120 --state DONE --text \"the fix held after a restart\"\n"
    "PITFALLS  2026-09-20 a decision without a verdict stayed open forever: the closing check now asks for one.\n"
    "          The note never edits the action it targets: it is appended, and the chain keeps both.\n"
)


def add_note(session, target, text, state=None):
    path = session_log.log_path(session)
    if not os.path.exists(path):
        return (3, "NO SESSION LOG " + session)
    ok, n, bad, reason = session_chain.verify(session_log.read_lines(path))
    if not ok:
        return (4, "SESSION LOG BROKEN: " + reason + ", nothing written")
    entry = {
        "ts": datetime.datetime.now().astimezone().isoformat(timespec="seconds"),
        "session": session,
        "event": "verdict" if state is not None else "comment",
        "target": target,
        "text": text,
    }
    if state is not None:
        entry["state"] = state
    line = session_log.append(session, entry)
    return (0, "NOTE ADDED seq " + str(line["seq"]) + " on " + str(target))


def _run_autotest():
    base = tempfile.mkdtemp()
    os.environ["FRUGALFLOW_SESSIONS"] = os.path.join(base, "sessions")
    os.environ["FRUGALFLOW_ANCHORS"] = os.path.join(base, "anchors")
    env = dict(os.environ)

    ACTION = {"ts": "2026-09-26T10:00:00+02:00", "event": "tool_before", "tool": "Bash", "id": "a1", "input": "{\"command\": \"git push\"}"}

    all_passed = True
    try:
        session_log.append("s1", ACTION)

        def count():
            lines = session_log.read_lines(session_log.log_path("s1"))
            return sum(1 for line in lines if line.strip())

        def run_cmd(argv):
            proc = subprocess.run(
                [sys.executable, __file__] + argv,
                capture_output=True,
                text=True,
                env=env,
            )
            return proc.returncode, proc.stdout

        # --- test 1 ---
        expected = 1
        actual = count()
        if actual == expected:
            print("PASS test 1: count == " + str(expected) + ", got " + str(actual))
        else:
            print("FAIL test 1: expected count " + str(expected) + ", got " + str(actual))
            all_passed = False

        # --- test 2a ---
        code_a, out_a = run_cmd(["--session", "s1", "--target", "0", "--text", "looked at it"])
        expected_code_a = 0
        expected_prefix_a = "NOTE ADDED seq 1 on 0"
        expected_count_a = 2
        actual_count_a = count()
        if code_a == expected_code_a and out_a.startswith(expected_prefix_a) and actual_count_a == expected_count_a:
            print("PASS test 2a: exit " + str(expected_code_a) + ", starts with '" + expected_prefix_a + "', count " + str(expected_count_a))
        else:
            print("FAIL test 2a: expected exit " + str(expected_code_a) + " prefix '" + expected_prefix_a + "' count " + str(expected_count_a) + ", got exit " + str(code_a) + " stdout '" + out_a.strip() + "' count " + str(actual_count_a))
            all_passed = False

        # --- test 2b ---
        code_b, out_b = run_cmd(["--session", "s1", "--target", "0", "--state", "DONE", "--text", "held"])
        journal_path = session_log.log_path("s1")
        journal_lines = session_log.read_lines(journal_path)
        non_empty = [line for line in journal_lines if line.strip()]
        last_entry = json.loads(non_empty[-1])
        expected_count_b = 3
        actual_count_b = count()
        if (
            code_b == 0
            and last_entry.get("event") == "verdict"
            and last_entry.get("state") == "DONE"
            and last_entry.get("target") == 0
            and actual_count_b == expected_count_b
        ):
            print("PASS test 2b: exit 0, event=verdict, state=DONE, target=0, count " + str(expected_count_b))
        else:
            print(
                "FAIL test 2b: expected exit 0 event=verdict state=DONE target=0 count "
                + str(expected_count_b)
                + ", got exit " + str(code_b)
                + " event=" + str(last_entry.get("event"))
                + " state=" + str(last_entry.get("state"))
                + " target=" + str(last_entry.get("target"))
                + " count " + str(actual_count_b)
            )
            all_passed = False

        # --- test 3a ---
        code_c, out_c = run_cmd(["--session", "nope", "--target", "0", "--text", "x"])
        if code_c == 3 and "NO SESSION LOG nope" in out_c:
            print("PASS test 3a: exit 3, contains 'NO SESSION LOG nope'")
        else:
            print("FAIL test 3a: expected exit 3 with 'NO SESSION LOG nope', got exit " + str(code_c) + " stdout '" + out_c.strip() + "'")
            all_passed = False

        # --- test 3b ---
        with open(journal_path, "rb") as fh:
            original = fh.read()
        tampered = original.replace(b"git push", b"git pull")
        with open(journal_path, "wb") as fh:
            fh.write(tampered)

        code_d, out_d = run_cmd(["--session", "s1", "--target", "0", "--text", "x"])
        with open(journal_path, "rb") as fh:
            after = fh.read()
        if code_d == 4 and "nothing written" in out_d and after == tampered:
            print("PASS test 3b: exit 4, contains 'nothing written', journal byte-for-byte unchanged")
        else:
            print(
                "FAIL test 3b: expected exit 4 'nothing written' journal unchanged, got exit "
                + str(code_d) + " stdout '" + out_d.strip() + "' journal_changed=" + str(after != tampered)
            )
            all_passed = False

        with open(journal_path, "wb") as fh:
            fh.write(original)

        # --- test 4 ---
        code_e, out_e = run_cmd(["--session", "s1", "--target", "zero", "--text", "x"])
        code_f, out_f = run_cmd(["--session", "s1", "--target", "0", "--state", "MAYBE", "--text", "x"])
        code_g, out_g = run_cmd(["--bogus"])
        expected_count_d = 3
        actual_count_d = count()
        if (
            code_e == 2
            and code_f == 2
            and code_g == 2
            and "usage: session_note.py" in out_g
            and actual_count_d == expected_count_d
        ):
            print("PASS test 4: all exit 2, usage shown, count " + str(expected_count_d))
        else:
            print(
                "FAIL test 4: expected all exit 2 usage count " + str(expected_count_d)
                + ", got exit " + str(code_e) + "/" + str(code_f) + "/" + str(code_g)
                + " count " + str(actual_count_d)
            )
            all_passed = False

        # --- test 5 ---
        code_h, out_h = run_cmd(["--notice"])
        if code_h == 0 and out_h.startswith("NAME      session_note.py"):
            print("PASS test 5: exit 0, starts with 'NAME      session_note.py'")
        else:
            print("FAIL test 5: expected exit 0 starts with 'NAME      session_note.py', got exit " + str(code_h) + " stdout '" + out_h.strip() + "'")
            all_passed = False

    finally:
        shutil.rmtree(base)

    return 0 if all_passed else 1


def main():
    args = sys.argv[1:]

    if not args:
        print(USAGE)
        sys.exit(2)

    if args[0] == "--notice":
        if len(args) > 1:
            print(USAGE)
            sys.exit(2)
        sys.stdout.write(NOTICE)
        sys.exit(0)

    if args[0] == "--autotest":
        if len(args) > 1:
            print(USAGE)
            sys.exit(2)
        sys.exit(_run_autotest())

    session = None
    target = None
    text = None
    state = None
    idx = 0
    while idx < len(args):
        if args[idx] == "--session":
            if idx + 1 >= len(args):
                print(USAGE)
                sys.exit(2)
            session = args[idx + 1]
            idx += 2
        elif args[idx] == "--target":
            if idx + 1 >= len(args):
                print(USAGE)
                sys.exit(2)
            target = args[idx + 1]
            idx += 2
        elif args[idx] == "--text":
            if idx + 1 >= len(args):
                print(USAGE)
                sys.exit(2)
            text = args[idx + 1]
            idx += 2
        elif args[idx] == "--state":
            if idx + 1 >= len(args):
                print(USAGE)
                sys.exit(2)
            state = args[idx + 1]
            idx += 2
        else:
            print(USAGE)
            sys.exit(2)

    if session is None or target is None or text is None:
        print(USAGE)
        sys.exit(2)

    if not target.isdigit():
        print(USAGE)
        sys.exit(2)

    if state is not None and state not in notes_rules.STATES:
        print(USAGE)
        sys.exit(2)

    code, message = add_note(session, int(target), text, state)
    print(message)
    sys.exit(code)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "session_note", sys.argv[1:])
