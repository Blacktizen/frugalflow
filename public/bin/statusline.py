#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""statusline.py - the FrugalFlow status line segment."""

import os
import sys
import json
import datetime
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import ceilings
    IMPORT_ERROR = None
except Exception as _e:
    ceilings = None
    IMPORT_ERROR = _e

DOT = " \u00b7 "

NOTICE = (
    "NAME      statusline.py - prints one status line: the user's own line, then the FrugalFlow segment, and never more.\n"
    "READS     stdin (ignored except to forward it); FRUGALFLOW_HOME/preferences.json, else ~/.frugalflow (the switch and the display settings); FRUGALFLOW_HOME/guard.json and the audit log it names, for the avoidable call count.\n"
    "WRITES    nothing: one line on stdout, always exit 0, never raises; an unreadable home means on, active, everything shown.\n"
    "EXAMPLE   python3 statusline.py --inner \"printf 'mine'\"\n"
    "PITFALLS  2026-10-04 the segment adds to the user's status line, it never replaces it; the inner command gets three seconds and its first line only.\n"
)


def _home():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")


def _read_prefs(home):
    try:
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    return doc


def _switch(doc):
    if ceilings is None:
        return (True, "active")
    try:
        return ceilings.switch_state(doc if doc is not None else {})
    except Exception:
        return (True, "active")


def _display(doc):
    if ceilings is None:
        return {"statusline": True, "turn_line": True, "summary": True}
    try:
        return ceilings.display_state(doc if doc is not None else {})
    except Exception:
        return {"statusline": True, "turn_line": True, "summary": True}


def _avoidable(home):
    try:
        with open(os.path.join(home, "guard.json"), encoding="utf-8") as f:
            settings = json.load(f)
    except Exception:
        return 0
    if not isinstance(settings, dict):
        return 0
    log = settings.get("audit_log")
    if not isinstance(log, str):
        return 0
    path = os.path.expanduser(log)
    if not os.path.isabs(path):
        path = os.path.join(home, path)
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except Exception:
        return 0
    today = datetime.date.today()
    count = 0
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except ValueError:
            continue
        if not isinstance(entry, dict):
            continue
        audit = entry.get("audit")
        if not isinstance(audit, str) or not audit.startswith("observed"):
            continue
        stamp = entry.get("time")
        if not isinstance(stamp, str):
            continue
        try:
            when = datetime.datetime.fromisoformat(stamp)
        except ValueError:
            continue
        if when.date() == today:
            count += 1
    return count


def _inner(command, stdin_text):
    try:
        proc = subprocess.run(
            ["/bin/sh", "-c", command],
            input=stdin_text,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except Exception:
        return ""
    if proc.returncode != 0:
        return ""
    lines = proc.stdout.splitlines()
    if not lines:
        return ""
    return lines[0].rstrip()


def _autotest():
    import tempfile
    import time

    script = os.path.abspath(__file__)

    def prefs(mode, statusline=True):
        doc = {"schema_version": "1",
               "verbosity": {"final_answer_words": 150, "step_message_words": 35},
               "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 60000},
               "splitting": {"max_proofs_per_task": 5, "max_brief_lines": 140},
               "grouping": {"independent_calls_same_turn": True},
               "switch": {"enabled": True, "mode": mode},
               "display": {"statusline": statusline, "turn_line": True, "summary": True}}
        return doc

    def write_home(home, doc):
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(doc, f)
        with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
            f.write('{"code_extensions": [".py"], "delegation_logs": ["delegations.jsonl"], "audit_log": "audit.jsonl"}')
        now = datetime.datetime.now().astimezone().isoformat()
        old = (datetime.datetime.now().astimezone() - datetime.timedelta(days=2)).isoformat()
        lines = [json.dumps({"time": now, "decision": "allow", "audit": "observed:x"}) for _ in range(3)]
        lines.append(json.dumps({"time": now, "decision": "allow", "audit": "receipt"}))
        lines.append(json.dumps({"time": old, "decision": "allow", "audit": "observed:old"}))
        lines.append("pas du json")  # lang-ok: the exact fixture line, not English
        with open(os.path.join(home, "audit.jsonl"), "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")

    def run(home, *args):
        env = dict(os.environ)
        env["HOME"] = home
        env["FRUGALFLOW_HOME"] = home
        start = time.monotonic()
        r = subprocess.run([sys.executable, script] + list(args),
                           input="", capture_output=True, text=True, env=env)
        elapsed = time.monotonic() - start
        return (r.returncode, r.stdout, elapsed)

    results = []

    # Proof 1: active mode, no inner command.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_home(home, prefs("active"))
        code, out, _ = run(home)
        ok = code == 0 and out == "FrugalFlow" + DOT + "active\n"
        results.append(("1 active mode prints the active segment", ok,
                        "rc=%d line=%r" % (code, out) if not ok else ""))

    # Proof 2: observe mode counts today's avoidable calls.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_home(home, prefs("observe"))
        code, out, _ = run(home)
        expected = "FrugalFlow" + DOT + "observe" + DOT + "avoidable calls today: 3\n"
        ok = code == 0 and out == expected
        results.append(("2 observe mode counts 3 avoidable calls today", ok,
                        "rc=%d line=%r" % (code, out) if not ok else ""))

    # Proof 3: the inner command's first line is kept.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_home(home, prefs("active"))
        code, out, _ = run(home, "--inner", "printf 'mine'")
        expected = "mine | FrugalFlow" + DOT + "active\n"
        ok = code == 0 and out == expected
        results.append(("3 inner first line is joined to the segment", ok,
                        "rc=%d line=%r" % (code, out) if not ok else ""))

    # Proof 4: a slow inner command gives up after its deadline.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_home(home, prefs("active"))
        code, out, elapsed = run(home, "--inner", "sleep 20")
        expected = "FrugalFlow" + DOT + "active\n"
        ok = code == 0 and out == expected and elapsed < 8
        results.append(("4 a 20 s inner command is dropped before 8 s", ok,
                        "rc=%d line=%r elapsed=%.1f" % (code, out, elapsed) if not ok else ""))

    # Proof 5: display.statusline off keeps only the inner line.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        write_home(home, prefs("active", statusline=False))
        code, out, _ = run(home, "--inner", "printf 'mine'")
        ok = code == 0 and out == "mine\n"
        results.append(("5 display.statusline off prints the inner line only", ok,
                        "rc=%d line=%r" % (code, out) if not ok else ""))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + (" | " + detail if detail else ""))
            all_pass = False
    return 0 if all_pass else 1


def main(argv):
    command = None
    i = 0
    while i < len(argv):
        if argv[i] == "--inner":
            if i + 1 < len(argv):
                command = argv[i + 1]
                i += 2
            else:
                command = ""
                i += 1
        else:
            i += 1
    stdin_text = ""
    try:
        stdin_text = sys.stdin.read()
    except Exception:
        pass
    useful = _inner(command, stdin_text) if command is not None else ""
    home = _home()
    doc = _read_prefs(home)
    enabled, mode = _switch(doc)
    display = _display(doc)
    if not enabled:
        segment = "FrugalFlow" + DOT + "off"
    else:
        segment = "FrugalFlow" + DOT + mode
        if mode == "observe":
            segment = segment + DOT + "avoidable calls today: " + str(_avoidable(home))
    if not display["statusline"]:
        print(useful)
    elif useful:
        print(useful + " | " + segment)
    else:
        print(segment)
    return 0


if __name__ == "__main__":
    try:
        if len(sys.argv) == 2 and sys.argv[1] == "--notice":
            sys.stdout.write(NOTICE)
            sys.exit(0)
        if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
            sys.exit(_autotest())
        sys.exit(main(sys.argv[1:]))
    except Exception:
        print("")
        sys.exit(0)
