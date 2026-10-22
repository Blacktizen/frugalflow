#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_summary.py - records a session summary at the end of a session and shows it once at the next start."""

import os
import sys
import json
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import ceilings
    IMPORT_ERROR = None
except Exception as _e:
    ceilings = None
    IMPORT_ERROR = _e

BIN = os.path.dirname(os.path.abspath(__file__))

USAGE = (
    "usage: session_summary.py --record TRACE [--home H] | --record-hook [--home H] | --show [--home H] | --notice | --autotest"
)

SILENT = "FrugalFlow: silent mode - run frugalflow report for details"

NOTICE = (
    "NAME      session_summary.py - records the frugalflow report summary at the end of a session and shows it once at the next start.\n"
    "READS     the TRACE transcript via report_cmd.py --summary; the hook payload on stdin with --record-hook (its transcript_path); FRUGALFLOW_HOME/preferences.json, else ~/.frugalflow (the switch and the display settings); the home's last_summary.json, written by --record; the home's guard.json and its audit log (the observed calls, for the proposal).\n"
    "WRITES    last_summary.json in the home when --record succeeds: the summary lines and seen false; --show flips seen to true once it has been shown; proposal.json in the home (the observe session count and whether the proposal was shown); nothing is written when the switch is off, silent, or the summary is hidden.\n"
    "EXAMPLE   python3 session_summary.py --record public/examples/report_trace.jsonl\n"
    "PITFALLS  2026-10-04 the summary is shown only once: --show marks last_summary.json seen, so the next start prints nothing until the next --record.\n"
)


def _home():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")


def _resolve_home(home):
    return home if home else _home()


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


def _parse(argv, allow_trace):
    trace = None
    home = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            if i + 1 >= len(argv):
                return (None, None, False)
            home = argv[i + 1]
            i += 2
        else:
            if not allow_trace:
                return (None, None, False)
            if trace is not None:
                return (None, None, False)
            trace = a
            i += 1
    if allow_trace and trace is None:
        return (None, None, False)
    return (trace, home, True)


def _summary_path(home):
    return os.path.join(home, "last_summary.json")


def _proposal_path(home):
    return os.path.join(home, "proposal.json")


def _read_proposal(home):
    try:
        with open(_proposal_path(home), encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        data = None
    if not isinstance(data, dict):
        data = {}
    obs = data.get("observe_sessions")
    if not isinstance(obs, int) or isinstance(obs, bool):
        obs = 0
    return {"observe_sessions": obs, "proposed": data.get("proposed") is True}


def _write_proposal(home, state):
    try:
        os.makedirs(home, exist_ok=True)
        with open(_proposal_path(home), "w", encoding="utf-8") as f:
            json.dump(
                {"observe_sessions": state["observe_sessions"], "proposed": state["proposed"]},
                f,
            )
    except Exception:
        pass


def _observed_calls(home):
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
        if isinstance(audit, str) and audit.startswith("observed"):
            count += 1
    return count


def record(argv):
    trace, home, ok = _parse(argv, allow_trace=True)
    if not ok:
        print(USAGE)
        return 2
    home_dir = _resolve_home(home)
    doc = _read_prefs(home_dir)
    enabled, mode = _switch(doc)
    if not enabled or mode == "silent" or not _display(doc)["summary"]:
        return 0
    proc = subprocess.run(
        [sys.executable, os.path.join(BIN, "report_cmd.py"), trace, "--summary"],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        return proc.returncode
    lines = [l for l in proc.stdout.splitlines() if l.strip() != ""]
    doc = {"lines": lines, "seen": False}
    try:
        os.makedirs(home_dir, exist_ok=True)
        with open(_summary_path(home_dir), "w", encoding="utf-8") as f:
            json.dump(doc, f)
    except Exception:
        return 1
    if mode == "observe":
        state = _read_proposal(home_dir)
        state["observe_sessions"] = state["observe_sessions"] + 1
        _write_proposal(home_dir, state)
    return 0


def record_hook(argv):
    home = None
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            home = argv[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2
    text = sys.stdin.read()
    try:
        payload = json.loads(text)
    except Exception:
        return 0
    if not isinstance(payload, dict):
        return 0
    tpath = payload.get("transcript_path")
    if not isinstance(tpath, str) or tpath == "":
        return 0
    if not os.path.isfile(tpath):
        return 0
    args = [tpath]
    if home is not None:
        args.append("--home")
        args.append(home)
    return record(args)


def show(argv):
    trace, home, ok = _parse(argv, allow_trace=False)
    if not ok:
        print(USAGE)
        return 2
    home_dir = _resolve_home(home)
    doc = _read_prefs(home_dir)
    enabled, mode = _switch(doc)
    display = _display(doc)
    if not enabled:
        return 0
    if mode == "silent":
        print(SILENT)
        return 0
    if not display["summary"]:
        return 0
    path = _summary_path(home_dir)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        return 0
    if not isinstance(data, dict) or data.get("seen") is not False:
        return 0
    lines = data.get("lines")
    if not isinstance(lines, list):
        return 0
    for line in lines:
        print(line)
    if mode == "observe":
        state = _read_proposal(home_dir)
        calls = _observed_calls(home_dir)
        if state["observe_sessions"] >= 3 and not state["proposed"] and calls > 0:
            print(
                "  proposal: %d avoidable calls observed over %d sessions [observed]; to act on them: frugalflow mode active"
                % (calls, state["observe_sessions"])
            )
            state["proposed"] = True
            _write_proposal(home_dir, state)
    data["seen"] = True
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f)
    except Exception:
        return 1
    return 0


def main(argv):
    if not argv:
        print(USAGE)
        return 2
    if argv[0] == "--record":
        return record(argv[1:])
    if argv[0] == "--record-hook":
        return record_hook(argv[1:])
    if argv[0] == "--show":
        return show(argv[1:])
    print(USAGE)
    return 2


def _autotest():
    import tempfile

    script = os.path.abspath(__file__)
    examples = os.path.join(os.path.dirname(BIN), "examples")
    trace = os.path.join(examples, "report_trace.jsonl")

    SUMMARY_LINES = [
        "FrugalFlow - session summary",
        "  4 turns - 90 500 context reread - startup: 10 000 per turn",
        "  costliest: turn 2, +30 010 tokens after Read: big.log",
        "  details: frugalflow report",
    ]

    def run(args, home):
        env = dict(os.environ)
        if home:
            env["HOME"] = home
            env["FRUGALFLOW_HOME"] = home
        else:
            env.pop("FRUGALFLOW_HOME", None)
        r = subprocess.run([sys.executable, script] + list(args),
                           capture_output=True, text=True, env=env)
        return (r.returncode, r.stdout)

    def read_summary(home):
        try:
            with open(os.path.join(home, "last_summary.json"), encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return None

    results = []

    # Proof 1: record on the example trace writes the summary, seen false.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        code, out = run(["--record", trace, "--home", home], home)
        data = read_summary(home)
        ok = code == 0 and isinstance(data, dict) and data.get("seen") is False and data.get("lines") == SUMMARY_LINES
        results.append(("1 record on the example trace stores the four lines and seen false", ok,
                        "code=%d data=%r" % (code, data) if not ok else ""))

    # Proof 1b: record-hook with the example payload stores the summary.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        payload = json.dumps(
            {"session_id": "s", "transcript_path": trace,
             "hook_event_name": "SessionEnd", "reason": "exit"}
        )
        env = dict(os.environ)
        env["HOME"] = home
        env["FRUGALFLOW_HOME"] = home
        r = subprocess.run([sys.executable, script, "--record-hook", "--home", home],
                           input=payload, capture_output=True, text=True, env=env)
        data = read_summary(home)
        ok = (r.returncode == 0 and r.stdout == "" and isinstance(data, dict)
              and data.get("seen") is False and data.get("lines") == SUMMARY_LINES)
        results.append(("record-hook stores the four lines and seen false", ok,
                        "code=%d out=%r data=%r" % (r.returncode, r.stdout, data) if not ok else ""))

    # Proof 1c: record with the switch off exits 0 and writes nothing.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            f.write('{"switch": {"enabled": false, "mode": "active"}}')
        code, out = run(["--record", trace, "--home", home], home)
        data = read_summary(home)
        ok = code == 0 and data is None
        results.append(("1c record with the switch off exits 0 and writes nothing", ok,
                        "code=%d data=%r" % (code, data) if not ok else ""))

    # Proof 2: record on a missing trace fails and writes nothing.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        missing = os.path.join(tmp, "missing.jsonl")
        code, out = run(["--record", missing, "--home", home], home)
        data = read_summary(home)
        ok = code == 2 and data is None
        results.append(("2 record on a missing trace exits 2 and writes nothing", ok,
                        "code=%d data=%r" % (code, data) if not ok else ""))

    # Proof 3: show twice with no preferences; the first prints, the second is quiet, seen true.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home, exist_ok=True)
        with open(_summary_path(home), "w", encoding="utf-8") as f:
            json.dump({"lines": SUMMARY_LINES, "seen": False}, f)
        expected = "\n".join(SUMMARY_LINES) + "\n"
        code1, out1 = run(["--show", "--home", home], home)
        code2, out2 = run(["--show", "--home", home], home)
        seen = read_summary(home)
        ok = code1 == 0 and out1 == expected and code2 == 0 and out2 == "" and isinstance(seen, dict) and seen.get("seen") is True
        results.append(("3 show twice: first prints the lines, second is quiet, seen true", ok,
                        "c1=%d o1=%r c2=%d o2=%r seen=%r" % (code1, out1, code2, out2, seen) if not ok else ""))

    # Proof 4a: show with silent mode prints exactly the SILENT line.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump({"switch": {"enabled": True, "mode": "silent"}}, f)
        with open(_summary_path(home), "w", encoding="utf-8") as f:
            json.dump({"lines": SUMMARY_LINES, "seen": False}, f)
        code, out = run(["--show", "--home", home], home)
        ok = code == 0 and out == SILENT + "\n"
        results.append(("4a show with silent mode prints exactly the SILENT line", ok,
                        "code=%d out=%r" % (code, out) if not ok else ""))

    # Proof 4b: show with the summary display off prints nothing.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump({"switch": {"enabled": True, "mode": "observe"},
                       "display": {"statusline": True, "turn_line": True, "summary": False}}, f)
        with open(_summary_path(home), "w", encoding="utf-8") as f:
            json.dump({"lines": SUMMARY_LINES, "seen": False}, f)
        code, out = run(["--show", "--home", home], home)
        ok = code == 0 and out == ""
        results.append(("4b show with the summary display off prints nothing", ok,
                        "code=%d out=%r" % (code, out) if not ok else ""))

    # Proof 4c: observe mode, three record and show cycles; the proposal is printed once, at the third show.
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home, exist_ok=True)
        with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump({"switch": {"enabled": True, "mode": "observe"}}, f)
        with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
            json.dump({"audit_log": "audit.jsonl"}, f)
        with open(os.path.join(home, "audit.jsonl"), "w", encoding="utf-8") as f:
            f.write('{"audit": "observed:big_read"}\n{"audit": "observed:big_read"}\n')
        proposal = ("  proposal: 2 avoidable calls observed over 3 sessions [observed]; "
                    "to act on them: frugalflow mode active")
        outs = []
        for _ in range(3):
            c1, o1 = run(["--record", trace, "--home", home], home)
            c2, o2 = run(["--show", "--home", home], home)
            outs.append((c1, c2, o2))
        ok = (
            all(c1 == 0 and c2 == 0 for c1, c2, _ in outs)
            and all(SUMMARY_LINES[0] in o for _, _, o in outs)
            and proposal not in outs[0][2]
            and proposal not in outs[1][2]
            and outs[2][2].splitlines()[-1] == proposal
        )
        detail = "outs=%r" % (outs,) if not ok else ""
        results.append(("proposal the third observe cycle ends with the one-time proposal", ok, detail))

    # Proof 5a: no argument gives 2 and the usage line.
    with tempfile.TemporaryDirectory() as tmp:
        code, out = run([], tmp)
        ok = code == 2 and out == USAGE + "\n"
        results.append(("5a no argument exits 2 and prints the usage line", ok,
                        "code=%d out=%r" % (code, out) if not ok else ""))

    # Proof 5b: --notice follows the five-line contract.
    import notice_rules
    code, out = run(["--notice"], None)
    defects = notice_rules.check(out, "session_summary.py")
    ok = code == 0 and defects == []
    results.append(("5b --notice follows the five-line contract", ok,
                    "code=%d defects=%r" % (code, defects) if not ok else ""))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + (" | " + detail if detail else ""))
            all_pass = False
    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    sys.exit(main(sys.argv[1:]))


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "session_summary", sys.argv[1:])
