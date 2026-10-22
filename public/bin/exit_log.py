"""exit_log.py - runs a tool's main(), keeps a copy of what it prints on stdout and stderr, and logs every non-zero exit (a refusal, a failure, or a returned non-zero code) to that tool's block log, then exits with the tool's own code."""

import os
import sys
import json
import inspect
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import block_log


class Tee:
    """Wraps a stream, capturing all written text into the shared parts list."""

    def __init__(self, stream, parts):
        self.stream = stream
        self.parts = parts

    def write(self, text):
        self.parts.append(text)
        return self.stream.write(text)

    def flush(self):
        return self.stream.flush()

    def __getattr__(self, name):
        return getattr(self.stream, name)


def _wants_argv(main):
    # a positional parameter with no default means main takes argv.
    try:
        sig = inspect.signature(main)
    except (TypeError, ValueError):
        return False
    for param in sig.parameters.values():
        if param.kind in (param.POSITIONAL_ONLY, param.POSITIONAL_OR_KEYWORD):
            if param.default is param.empty:
                return True
    return False


def _record(tool, text, argv, version, home, number):
    try:
        block_log.record_block(
            tool,
            "exit_" + str(number),
            {"argv": list(argv), "cwd": os.getcwd()},
            text[-2000:],
            version,
            None,
            home=home,
        )
    except Exception as error:
        sys.stderr.write("BLOCK LOG FAILED: " + str(error) + "\n")


def run(main, tool, argv, version="", home=None):
    """Run main() with stdout and stderr teed; log non-zero exits to block_log; return None on a clean return."""
    parts = []
    tee_out = Tee(sys.stdout, parts)
    tee_err = Tee(sys.stderr, parts)
    sys.stdout = tee_out
    sys.stderr = tee_err
    try:
        if _wants_argv(main):
            result = main(list(argv))
        else:
            result = main()
    except SystemExit as e:
        code = e.code
        if code == 0 or code is None:
            raise
        number = code if isinstance(code, int) else 1
        text = "".join(parts)
        if not isinstance(code, int):
            text += str(code)
        _record(tool, text, argv, version, home, number)
        raise
    except Exception as e:
        # an uncaught exception is logged as exit_1, then re-raised untouched.
        text = "".join(parts) + "\n" + type(e).__name__ + ": " + str(e)
        _record(tool, text, argv, version, home, 1)
        raise
    finally:
        sys.stdout = tee_out.stream
        sys.stderr = tee_err.stream
    if isinstance(result, int) and not isinstance(result, bool) and result != 0:
        # a non-zero int returned by main is logged, then raised as SystemExit.
        text = "".join(parts)
        _record(tool, text, argv, version, home, result)
        raise SystemExit(result)
    return None


# --- fixtures for autotest ---

def main_refuse():
    print("NO RULES: x")
    sys.exit(4)

def main_ok_exit():
    print("VERIFIED")
    sys.exit(0)

def main_return():
    print("done")

def main_message():
    sys.exit("message text")

def main_stderr():
    # stderr is copied into the log while also going to the real stderr.
    sys.stderr.write("ERR line\n")
    print("OUT line")
    sys.exit(3)

def main_argv(argv):
    # a main that takes argv and returns its own code.
    print("ARGV=" + repr(argv))
    return 5 if argv == ["--x", "y"] else 6

def main_return2():
    # a non-zero int returned by main becomes an exit and a log line.
    print("RETURN TWO")
    return 2

def main_crash():
    # an uncaught exception is logged as exit_1 then re-raised.
    print("crashing")
    raise ValueError("boom crash")

ARGV = ["--role", "far"]
ARGV2 = ["--x", "y"]


NOTICE = (
    "NAME      exit_log.py - runs a tool's main(), keeps a copy of what it prints, and logs every non-zero exit (a refusal, a failure, or a non-zero code returned by main) to that tool's block log, then exits with the tool's own code.\n"
    "READS     nothing but what the tool prints while it runs.\n"
    "WRITES    one line per non-zero exit: a sys.exit code, a non-zero int that main returns, or an uncaught exception (logged as exit_1). stdout and stderr are copied into the line's reason; BLOCK LOG FAILED on stderr if that line cannot be written.\n"
    "EXAMPLE   python3 exit_log.py --notice\n"
    "PITFALLS  2026-10-02 every refusal must be logged, or the tools never learn from them: delegate.py refused for weeks without a single line.\n"
)


def _read_lines(home):
    path = os.path.join(home, "blocks", "t.jsonl")
    if not os.path.isfile(path):
        return None
    with open(path, "r") as f:
        return f.readlines()


def _autotest():
    home = tempfile.mkdtemp()
    original_stdout = sys.stdout
    original_stderr = sys.stderr
    all_passed = True

    # --- Test 1: main_refuse -> SystemExit(4), 1 line, rule=exit_4 ---
    try:
        run(main_refuse, "t", ARGV, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != 4 or lines is None or len(lines) != 1:
        sys.stdout.write("FAIL 1: expected SystemExit(4) and 1 line, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[0])
        if entry.get("rule") != "exit_4" or "NO RULES: x" not in entry.get("reason", "") or entry.get("input") != {"argv": ["--role", "far"], "cwd": os.getcwd()}:
            sys.stdout.write("FAIL 1: expected rule=exit_4 and reason with NO RULES: x, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 1: SystemExit(4), 1 line, rule=exit_4, reason contains NO RULES: x\n")

    # --- Test 2: main_ok_exit -> SystemExit(0), still 1 line ---
    try:
        run(main_ok_exit, "t", ARGV, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != 0 or lines is None or len(lines) != 1:
        sys.stdout.write("FAIL 2: expected SystemExit(0) and 1 line, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        sys.stdout.write("PASS 2: SystemExit(0), 1 line\n")

    # --- Test 3: main_return -> returns None, no exception, still 1 line ---
    result = run(main_return, "t", ARGV, home=home)
    lines = _read_lines(home)
    if result is not None or lines is None or len(lines) != 1:
        sys.stdout.write("FAIL 3: expected None and 1 line, got result=" + repr(result) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        sys.stdout.write("PASS 3: returned None, 1 line\n")

    # --- Test 4: main_message -> SystemExit("message text"), 2 lines, rule=exit_1 ---
    try:
        run(main_message, "t", ARGV, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != "message text" or lines is None or len(lines) != 2:
        sys.stdout.write("FAIL 4: expected SystemExit('message text') and 2 lines, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[1])
        if entry.get("rule") != "exit_1" or "message text" not in entry.get("reason", ""):
            sys.stdout.write("FAIL 4: expected rule=exit_1 and reason with message text, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 4: SystemExit('message text'), 2 lines, rule=exit_1, reason contains message text\n")

    # --- Test 5 (rule 1): main_stderr -> stderr copied into the log, exit_3, 3 lines ---
    try:
        run(main_stderr, "t", ARGV, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != 3 or lines is None or len(lines) != 3:
        sys.stdout.write("FAIL 5: expected SystemExit(3) and 3 lines, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[2])
        if entry.get("rule") != "exit_3" or "ERR line" not in entry.get("reason", "") or "OUT line" not in entry.get("reason", ""):
            sys.stdout.write("FAIL 5: expected rule=exit_3 and reason with both stderr and stdout, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 5: SystemExit(3), 3 lines, rule=exit_3, reason contains stdout AND stderr\n")

    # --- Test 6 (rule 2): main_argv(argv) -> called with argv, returns 5 -> exit_5, 4 lines ---
    try:
        run(main_argv, "t", ARGV2, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != 5 or lines is None or len(lines) != 4:
        sys.stdout.write("FAIL 6: expected SystemExit(5) and 4 lines, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[3])
        if entry.get("rule") != "exit_5" or repr(ARGV2) not in entry.get("reason", ""):
            sys.stdout.write("FAIL 6: expected rule=exit_5 and reason with argv, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 6: main(argv) returned 5, 4 lines, rule=exit_5, reason contains argv\n")

    # --- Test 7 (rule 3): main_return2 -> returns 2 -> SystemExit(2), exit_2, 5 lines ---
    try:
        run(main_return2, "t", ARGV, home=home)
        exit_code = "none"
    except SystemExit as e:
        exit_code = e.code
    lines = _read_lines(home)
    if exit_code != 2 or lines is None or len(lines) != 5:
        sys.stdout.write("FAIL 7: expected SystemExit(2) and 5 lines, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[4])
        if entry.get("rule") != "exit_2" or "RETURN TWO" not in entry.get("reason", ""):
            sys.stdout.write("FAIL 7: expected rule=exit_2 and reason with RETURN TWO, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 7: main returned 2, SystemExit(2), 5 lines, rule=exit_2, reason contains RETURN TWO\n")

    # --- Test 8 (rule 4): main_crash -> ValueError re-raised, exit_1 line, 6 lines ---
    try:
        run(main_crash, "t", ARGV, home=home)
        exit_code = "none"
    except ValueError as e:
        exit_code = "ValueError:" + str(e)
    lines = _read_lines(home)
    if exit_code != "ValueError:boom crash" or lines is None or len(lines) != 6:
        sys.stdout.write("FAIL 8: expected ValueError re-raised and 6 lines, got exit_code=" + repr(exit_code) + " lines=" + repr(len(lines) if lines is not None else None) + "\n")
        all_passed = False
    else:
        entry = json.loads(lines[5])
        if entry.get("rule") != "exit_1" or "boom crash" not in entry.get("reason", ""):
            sys.stdout.write("FAIL 8: expected rule=exit_1 and reason with boom crash, got rule=" + repr(entry.get("rule")) + "\n")
            all_passed = False
        else:
            sys.stdout.write("PASS 8: uncaught ValueError re-raised, 6 lines, rule=exit_1, reason contains boom crash\n")

    # --- Test 9: stdout and stderr identity restored, --notice subprocess ---
    stdout_ok = (sys.stdout is original_stdout)
    stderr_ok = (sys.stderr is original_stderr)
    notice_proc = subprocess.run(
        [sys.executable, __file__, "--notice"],
        capture_output=True,
        text=True,
    )
    notice_ok = (notice_proc.returncode == 0 and notice_proc.stdout.startswith("NAME      exit_log.py") and "stderr" in notice_proc.stdout and "return" in notice_proc.stdout)
    if not stdout_ok or not stderr_ok or not notice_ok:
        sys.stdout.write("FAIL 9: expected stdout/stderr identity and notice with stderr+return, got stdout_ok=" + str(stdout_ok) + " stderr_ok=" + str(stderr_ok) + " notice_rc=" + str(notice_proc.returncode) + "\n")
        all_passed = False
    else:
        sys.stdout.write("PASS 9: stdout and stderr identity restored, --notice exits 0 with stderr and return\n")

    shutil.rmtree(home)
    return 0 if all_passed else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stderr.write("usage: exit_log.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    main()
