#!/usr/bin/env python3
"""session_share.py - reads the delegation logs and returns the WINDOW, CLAUDE and DELEGATED lines of a session's token receipt."""

import os
import sys
import json
import shutil
import tempfile
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import share_rules

NOTICE = (
    "NAME      session_share.py - reads the delegation logs and returns the WINDOW, CLAUDE and DELEGATED lines of a session's token receipt.\n"
    "READS     the delegation logs named in FRUGALFLOW_DELEGATION_LOGS (path separator), else FRUGALFLOW_HOME or ~/.frugalflow/delegations.jsonl; FRUGALFLOW_WINDOW_LIMIT, 300 000 by default.\n"
    "WRITES    nothing: session_line() values are printed by usage_report.py; exit 2 on an unknown option.\n"
    "EXAMPLE   python3 session_share.py --autotest\n"
    "PITFALLS  2026-09-26 the receipt showed 71 181 tokens while the window held 216 000; the window and the delegated part are now printed too.\n"
)

USAGE = "usage: session_share.py [--notice | --autotest]\n"


def log_paths(environ):
    """Return the list of delegation log file paths derived from the environment dict."""
    delegation_logs = environ.get("FRUGALFLOW_DELEGATION_LOGS", "")
    if delegation_logs:
        return [part for part in delegation_logs.split(os.pathsep) if part]
    home = environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow")
    return [os.path.join(home, "delegations.jsonl")]


def read_entries(paths):
    """Read JSONL files and return a flat list of decoded dicts, skipping bad lines and missing files."""
    entries = []
    for path in paths:
        try:
            with open(path, "r", encoding="utf-8") as handle:
                for line in handle:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        decoded = json.loads(stripped)
                    except (json.JSONDecodeError, ValueError):
                        continue
                    if isinstance(decoded, dict):
                        entries.append(decoded)
        except OSError:
            continue
    return entries


def session_lines(objs, msgs, totals, environ, offset_minutes):
    """Compute and return the three receipt lines (WINDOW, CLAUDE, DELEGATED) via share_rules."""
    stamps = [
        item["timestamp"]
        for item in objs
        if item is not None and isinstance(item, dict) and item.get("timestamp")
    ]
    if stamps:
        start = share_rules.local_time(min(stamps), offset_minutes)
        end = share_rules.local_time(max(stamps), offset_minutes)
    else:
        start = ""
        end = ""

    try:
        limit = int(environ.get("FRUGALFLOW_WINDOW_LIMIT", "300000"))
    except (TypeError, ValueError):
        limit = 300000

    entries = read_entries(log_paths(environ))
    deleg = share_rules.delegated(entries, start, end)
    window = share_rules.window(msgs)
    return share_rules.report_lines(
        window, limit,
        totals["output"], totals["cache_read"], totals["messages"],
        deleg,
    )


def local_offset():
    """Return the current UTC offset in whole minutes."""
    return int(datetime.now().astimezone().utcoffset().total_seconds() // 60)


def _autotest():
    """Run the four test cases; return 0 if all pass, 1 otherwise."""
    fixtures_log_lines = (
        '{"time": "2026-09-26T19:10:00", "model_answered": "qwen3.8-27b", "tokens_in": 1000, "tokens_out": 500, "status": "success"}\n'
        'not json\n'
        '{"time": "2026-09-26T08:00:00", "model_answered": "qwen3.8-27b", "tokens_in": 9, "tokens_out": 9, "status": "success"}\n'
    )
    fixtures_objs = [
        None,
        {"timestamp": "2026-09-26T17:00:00.000Z"},
        {"timestamp": "2026-09-26T17:30:00.000Z"},
    ]
    fixtures_msgs = [
        {"usage": {"input_tokens": 1, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 9}}
    ]
    fixtures_totals = {"output": 500, "cache_read": 1000, "messages": 1}

    tmp_dir = tempfile.mkdtemp()
    all_passed = True
    try:
        log_file = os.path.join(tmp_dir, "a.jsonl")
        with open(log_file, "w", encoding="utf-8") as handle:
            handle.write(fixtures_log_lines)

        # --- Test 1: log_paths ---
        expected_1a = ["x.jsonl", "y.jsonl"]
        got_1a = log_paths({"FRUGALFLOW_DELEGATION_LOGS": "x.jsonl" + os.pathsep + "y.jsonl"})
        expected_1b = [os.path.join(tmp_dir, "delegations.jsonl")]
        got_1b = log_paths({"FRUGALFLOW_HOME": tmp_dir})
        if got_1a == expected_1a and got_1b == expected_1b:
            print("PASS 1 log_paths: expected %s got %s" % (expected_1a, got_1a))
        else:
            all_passed = False
            print("FAIL 1 log_paths: expected %s got %s | expected %s got %s" % (expected_1a, got_1a, expected_1b, got_1b))

        # --- Test 2: read_entries ---
        missing_file = os.path.join(tmp_dir, "missing.jsonl")
        entries_read = read_entries([log_file, missing_file])
        if len(entries_read) == 2:
            print("PASS 2 read_entries: expected 2 entries got %d" % len(entries_read))
        else:
            all_passed = False
            print("FAIL 2 read_entries: expected 2 entries got %d" % len(entries_read))

        # --- Test 3: session_lines ---
        expected_3 = [
            "WINDOW 1 010 of 2 020 (50.0 %)",
            "CLAUDE written 500 | context reread 1 000 over 1 turns",
            "DELEGATED 1 calls (1 ok) | sent 1 000 | received 500 | qwen3.8-27b 1 | delegated share of written tokens 50.0 %",
        ]
        environ_3 = {"FRUGALFLOW_DELEGATION_LOGS": log_file, "FRUGALFLOW_WINDOW_LIMIT": "2020"}
        got_3 = session_lines(fixtures_objs, fixtures_msgs, fixtures_totals, environ_3, 120)
        environ_3b = {"FRUGALFLOW_DELEGATION_LOGS": missing_file}
        got_3b = session_lines(fixtures_objs, fixtures_msgs, fixtures_totals, environ_3b, 120)
        if got_3 == expected_3 and got_3b and len(got_3b) > 2 and got_3b[2].startswith("DELEGATED 0 calls"):
            print("PASS 3 session_lines: third line %s" % got_3[2])
        else:
            all_passed = False
            print("FAIL 3 session_lines: expected %s got %s | missing-file third line got %s" % (
                expected_3, got_3,
                got_3b[2] if got_3b and len(got_3b) > 2 else None,
            ))

        # --- Test 4: subprocess relaunch ---
        script_path = os.path.abspath(__file__)
        proc_notice = subprocess.run(
            [sys.executable, script_path, "--notice"],
            capture_output=True, text=True,
        )
        proc_bogus = subprocess.run(
            [sys.executable, script_path, "--bogus"],
            capture_output=True, text=True,
        )
        if (
            proc_notice.returncode == 0
            and proc_notice.stdout.startswith("NAME      session_share.py")
            and proc_bogus.returncode == 2
            and proc_bogus.stdout == USAGE
        ):
            print("PASS 4 subprocess: notice code %d, bogus code %d" % (proc_notice.returncode, proc_bogus.returncode))
        else:
            all_passed = False
            print("FAIL 4 subprocess: notice code %d (stdout %r), bogus code %d (stdout %r)" % (
                proc_notice.returncode, proc_notice.stdout[:50],
                proc_bogus.returncode, proc_bogus.stdout[:50],
            ))

    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    return 0 if all_passed else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "session_share", sys.argv[1:])
