#!/usr/bin/env python3
"""read_quarantine.py – refuses reading a code file just produced by a delegation."""

import os
import sys
import subprocess
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_split
import shell_tokens
import receipt_rules
from example_defaults import setting

READERS = {
    "cat", "bat", "less", "more", "head", "tail", "nl", "od",
    "strings", "view", "vim", "nvim", "open", "xxd", "hexdump",
    "pygmentize",
}

PATTERN_READERS = {"sed", "awk", "grep", "rg", "egrep", "fgrep"}


def read_targets(command, cwd):
    result = []
    seen = set()
    parts = shell_split.split_command(command)
    for seg in parts["segments"]:
        toks = shell_tokens.tokenize(seg)
        if toks is None:
            continue
        toks = shell_tokens.strip_prefixes(toks)
        if not toks:
            continue
        head = os.path.basename(toks[0]).lower()
        if head == "cd" and len(toks) == 2:
            cwd = os.path.normpath(os.path.join(cwd, os.path.expanduser(toks[1])))
            continue
        if head not in READERS and head not in PATTERN_READERS:
            continue
        skip_pattern = head in PATTERN_READERS
        skip_next = False
        for a in toks[1:]:
            if skip_next:
                skip_next = False
                continue
            if shell_tokens.OPERATOR.fullmatch(a):
                skip_next = True
                continue
            if a == "<":
                continue
            if a.startswith("-"):
                continue
            if skip_pattern:
                skip_pattern = False
                continue
            if "/" in a or "." in a:
                p = os.path.normpath(os.path.join(cwd, os.path.expanduser(a)))
                if p not in seen:
                    seen.add(p)
                    result.append(p)
    return result


def produced(records, path, now, minutes):
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("kind") is not None:
            continue
        if not receipt_rules.same_target(path, r.get("target")):
            continue
        t = receipt_rules.to_time(r.get("time"), now.tzinfo)
        if t is None:
            continue
        delta = (now - t).total_seconds()
        if -120 <= delta <= minutes * 60:
            return True
    return False


def declared_read(records, path, now, minutes):
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("kind") != "read":
            continue
        if not receipt_rules.same_target(path, r.get("target")):
            continue
        reason = r.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 5:
            continue
        t = receipt_rules.to_time(r.get("time"), now.tzinfo)
        if t is None:
            continue
        delta = (now - t).total_seconds()
        if -120 <= delta <= minutes * 60:
            return True
    return False


def check(tool_name, tool_input, config, ctx):
    targets = []
    if tool_name == "Read":
        p = tool_input.get("file_path")
        if isinstance(p, str) and p:
            targets = [os.path.normpath(os.path.join(ctx["cwd"], os.path.expanduser(p)))]
        else:
            return (False, "", [])
    elif tool_name == "Bash":
        cmd = tool_input.get("command")
        if isinstance(cmd, str):
            targets = read_targets(cmd, ctx["cwd"])
        else:
            return (False, "", [])
    else:
        return (False, "", [])

    code = [
        t for t in targets
        if os.path.splitext(t)[1].lower() in config.get("code_extensions", [])
    ]
    if not code:
        return (False, "", [])

    records = ctx["records"]
    if records is None:
        return (
            True,
            "Read refused: the delegation log cannot be read, so the quarantine of "
            + code[0]
            + " cannot be checked. To fix: repair the delegation log file named in the settings.",
            code,
        )

    now = ctx["now"]
    minutes = setting(config, "guard", "quarantine_minutes")
    wmin = setting(config, "guard", "read_waiver_minutes")

    refused = [
        t for t in code
        if produced(records, t, now, minutes)
        and not declared_read(records, t, now, wmin)
    ]
    if refused:
        return (
            True,
            "Read refused: "
            + refused[0]
            + " was just produced by a delegation; run its test, do not read its code. "
            + "To fix: run the file or its --autotest, or declare the read in the delegation log (kind read, target, time, reason).",
            refused,
        )
    return (False, "", [])


NOTICE = (
    "NAME      read_quarantine.py - refuses reading a code file just produced by a delegation: run its test, do not read its code.\n"
    "READS     nothing: pure module; the caller passes the tool call, the settings and ctx (cwd, records of the delegation log or None, now).\n"
    "WRITES    nothing: check() returns (refuse, reason, targets); every refusal ends with \"To fix:\".\n"
    "EXAMPLE   python3 read_quarantine.py --notice\n"
    "PITFALLS  2026-09-26 the old check read the log itself and passed everything when it could not: an unreadable log now refuses the read of a code file.\n"
    "          A failed delegation may still have written its file: its output is quarantined like a successful one.\n"
)

USAGE = "usage: read_quarantine.py --notice | --autotest\n"


def _autotest():
    from datetime import datetime, timezone, timedelta

    NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
    CFG = {"code_extensions": [".py"], "quarantine_minutes": 60}
    REC = {
        "time": (NOW - timedelta(minutes=10)).isoformat(),
        "status": "success",
        "model_answered": "m",
        "target": "/w/new.py",
        "sha256": "x",
    }
    FAILED = dict(REC, status="failed", target="/w/failed.py")
    OLD = dict(REC, time=(NOW - timedelta(minutes=90)).isoformat(), target="/w/old.py")
    WAIVER = {
        "kind": "read",
        "target": "/w/new.py",
        "time": (NOW - timedelta(minutes=5)).isoformat(),
        "reason": "inspect one line",
    }
    EDIT = {
        "kind": "edit",
        "target": "/w/edited.py",
        "time": (NOW - timedelta(minutes=5)).isoformat(),
        "reason": "r",
    }
    RECORDS = [REC, FAILED, OLD]

    def R(tool, inp, records="default"):
        recs = RECORDS if records == "default" else records
        return check(tool, inp, CFG, {"cwd": "/w", "records": recs, "now": NOW})

    all_ok = True
    lines = []

    # --- Test 1 ---
    r1 = R("Read", {"file_path": "/w/new.py"})
    ok1 = (
        isinstance(r1, tuple)
        and len(r1) == 3
        and r1[0] is True
        and "To fix:" in r1[1]
        and "kind read" in r1[1]
        and r1[2] == ["/w/new.py"]
        and R("Read", {"file_path": "new.py"})[0] is True
        and R("Read", {"file_path": "/w/failed.py"})[0] is True
        and R("Read", {"file_path": "/w/old.py"})[0] is False
        and R("Read", {"file_path": "/w/other.py"})[0] is False
        and R("Read", {"file_path": "/w/new.md"})[0] is False
    )
    if ok1:
        lines.append("PASS test 1: read refusals for produced code files")
    else:
        lines.append("FAIL test 1: expected (True, reason with 'To fix:' and 'kind read', ['/w/new.py']), got %s" % (r1,))
        all_ok = False

    # --- Test 2 ---
    ok2 = (
        read_targets("cat a.py | grep -n x /w/b.py", "/w") == ["/w/a.py", "/w/b.py"]
        and read_targets("sed -n 1,20p new.py", "/w") == ["/w/new.py"]
        and read_targets("cd /x && head -n 20 new.py", "/w") == ["/x/new.py"]
        and read_targets("python3 new.py --autotest", "/w") == []
        and read_targets("grep -rn pattern", "/w") == []
        and read_targets("/usr/bin/tail -5 new.py 2>/dev/null", "/w") == ["/w/new.py"]
    )
    if ok2:
        lines.append("PASS test 2: read_targets extracts correct file paths")
    else:
        got = [
            read_targets("cat a.py | grep -n x /w/b.py", "/w"),
            read_targets("sed -n 1,20p new.py", "/w"),
            read_targets("cd /x && head -n 20 new.py", "/w"),
            read_targets("python3 new.py --autotest", "/w"),
            read_targets("grep -rn pattern", "/w"),
            read_targets("/usr/bin/tail -5 new.py 2>/dev/null", "/w"),
        ]
        lines.append("FAIL test 2: expected correct targets, got %s" % (got,))
        all_ok = False

    # --- Test 3 ---
    r3a = R("Bash", {"command": "cat new.py"})
    r3b = R("Bash", {"command": "cat new.md old.py"})
    r3c = R("Bash", {"command": "python3 new.py --autotest"})
    r3d = R("Bash", {"command": "sed -n 1,5p new.py failed.py"})
    ok3 = (
        isinstance(r3a, tuple) and len(r3a) == 3
        and r3a[0] is True and r3a[2] == ["/w/new.py"] and "To fix:" in r3a[1]
        and r3b[0] is False
        and r3c[0] is False
        and isinstance(r3d, tuple) and len(r3d) == 3
        and r3d[2] == ["/w/new.py", "/w/failed.py"]
    )
    if ok3:
        lines.append("PASS test 3: bash reader refusals and non-refusals")
    else:
        lines.append("FAIL test 3: expected refusal for cat new.py, pass for new.md/other, got %s / %s / %s / %s" % (r3a, r3b, r3c, r3d))
        all_ok = False

    # --- Test 4 ---
    r4a = R("Read", {"file_path": "/w/new.py"}, records=RECORDS + [WAIVER])
    r4b = R("Read", {"file_path": "/w/new.py"}, records=RECORDS + [dict(WAIVER, time=(NOW - timedelta(minutes=20)).isoformat())])
    r4c = R("Read", {"file_path": "/w/edited.py"}, records=[EDIT])
    r4d = R("Read", {"file_path": "/w/new.py"}, records=None)
    r4e = R("Read", {"file_path": "/w/a.md"}, records=None)
    r4f = R("Write", {"file_path": "/w/new.py", "content": "x"})
    r4g = R("Bash", {"command": 5})
    ok4 = (
        r4a[0] is False
        and r4b[0] is True
        and r4c[0] is False
        and r4d[0] is True and "cannot be read" in r4d[1]
        and r4e[0] is False
        and r4f == (False, "", [])
        and r4g == (False, "", [])
    )
    if ok4:
        lines.append("PASS test 4: waiver, stale waiver, edit, None records, non-code, other tools")
    else:
        lines.append("FAIL test 4: expected waiver pass, stale fail, edit pass, None fail, md pass, Write/Bash pass, got %s %s %s %s %s %s %s" % (r4a, r4b, r4c, r4d, r4e, r4f, r4g))
        all_ok = False

    # --- Test 5 ---
    proc1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True,
    )
    proc2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True,
    )
    ok5 = (
        proc1.returncode == 0
        and proc1.stdout.startswith("NAME      read_quarantine.py")
        and proc2.returncode == 2
        and proc2.stdout == "usage: read_quarantine.py --notice | --autotest\n"
    )
    if ok5:
        lines.append("PASS test 5: --notice prints notice (exit 0); no-arg prints usage (exit 2)")
    else:
        lines.append(
            "FAIL test 5: expected notice exit 0 / usage exit 2, got rc=%s out=%r / rc=%s out=%r"
            % (proc1.returncode, proc1.stdout[:40], proc2.returncode, proc2.stdout[:40])
        )
        all_ok = False

    for ln in lines:
        print(ln)

    if not all_ok:
        print("FAILURE")
        sys.exit(1)
    sys.exit(0)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        _autotest()
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "read_quarantine", sys.argv[1:])
