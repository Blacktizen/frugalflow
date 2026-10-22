#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the session summary: record at the end of a session, show once at the next start."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
TRACE = os.path.join(os.path.dirname(BIN), "examples", "report_trace.jsonl")

SUMMARY_LINE = "FrugalFlow - session summary"

USAGE = "usage: e2e_summary.py [--notice | --autotest]\n"

NOTICE = (
    "NAME      e2e_summary.py - end-to-end test of the session summary: creates a project in a clean environment and temporary folders, then records the summary at the end of a session and checks it is shown once at the next start.\n"
    "READS     the tools in ../bin (frugalflow.py, session_summary.py and the hooks they write) and the example trace ../examples/report_trace.jsonl; every step runs in a subprocess with a clean environment.\n"
    "WRITES    only in two temporary folders, always removed, even on failure. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_summary.py\n"
    "PITFALLS  2026-10-05 the summary is shown only once: the first SessionStart start prints it and marks it seen, so the second start prints nothing until the next record.\n"
)


def _ff(env, work, *args):
    """Run the real frugalflow.py in a clean environment, cwd = work."""
    cmd = [sys.executable, os.path.join(BIN, "frugalflow.py")]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=work)


def _load_settings(path):
    """Parse the settings file, or None if it is missing or not readable."""
    try:
        with open(path, encoding="utf-8") as handle:
            return json.load(handle)
    except Exception:
        return None


def _commands(cfg, event):
    """The list of hook command strings configured under a hook event."""
    cmds = []
    for group in cfg.get("hooks", {}).get(event, []):
        for entry in group.get("hooks", []):
            command = entry.get("command")
            if isinstance(command, str):
                cmds.append(command)
    return cmds


def _run_command(command, env, work, payload):
    """Run one hook command through a shell, feeding the payload on stdin."""
    return subprocess.run(command, shell=True, input=payload,
                          capture_output=True, text=True, env=env, cwd=work)


def main_run():
    H = tempfile.mkdtemp()
    W = tempfile.mkdtemp()
    results = []
    try:
        env = {"PATH": os.environ["PATH"], "HOME": H}
        settings = os.path.join(W, "demo", ".claude", "settings.json")
        last_summary = os.path.join(H, ".frugalflow", "last_summary.json")

        # Step 1: new-project
        r1 = _ff(env, W, "new-project", "demo")
        exists1 = os.path.isfile(settings)
        ok1 = r1.returncode == 0 and exists1
        results.append(("new-project", ok1,
                        "new-project demo exits 0 and writes W/demo/.claude/settings.json",
                        "exit %d, settings exists=%s" % (r1.returncode, exists1)))

        cfg = _load_settings(settings)

        # Step 2: hooks
        if cfg is None:
            ok2, got2 = False, "no settings file at " + settings
        else:
            has_show = any(c.endswith("session_summary.py --show") for c in _commands(cfg, "SessionStart"))
            has_record = any(c.endswith("session_summary.py --record-hook") for c in _commands(cfg, "SessionEnd"))
            ok2 = has_show and has_record
            got2 = "SessionStart --show=%s, SessionEnd --record-hook=%s" % (has_show, has_record)
        results.append(("hooks", ok2,
                        "a SessionStart command ends with --show and a SessionEnd command ends with --record-hook",
                        got2))

        # Step 3: record
        payload_end = json.dumps({"session_id": "e2e", "transcript_path": TRACE,
                                  "hook_event_name": "SessionEnd", "reason": "exit"})
        if cfg is None:
            ok3, got3 = False, "no settings file at " + settings
        else:
            end_cmds = _commands(cfg, "SessionEnd")
            codes = [_run_command(c, env, W, payload_end).returncode for c in end_cmds]
            exists3 = os.path.isfile(last_summary)
            ok3 = bool(end_cmds) and all(rc == 0 for rc in codes) and exists3
            got3 = "commands=%d exit codes=%s last_summary exists=%s" % (len(end_cmds), codes, exists3)
        results.append(("record", ok3,
                        "every SessionEnd command exits 0 and writes H/.frugalflow/last_summary.json",
                        got3))

        # Step 4: show-once
        payload_start = json.dumps({"session_id": "e2e2", "transcript_path": TRACE,
                                    "hook_event_name": "SessionStart", "source": "startup"})
        if cfg is None:
            ok4, got4 = False, "no settings file at " + settings
        else:
            start_cmds = _commands(cfg, "SessionStart")
            out1 = "".join(_run_command(c, env, W, payload_start).stdout for c in start_cmds)
            out2 = "".join(_run_command(c, env, W, payload_start).stdout for c in start_cmds)
            seen1 = SUMMARY_LINE in out1
            gone2 = SUMMARY_LINE not in out2
            ok4 = bool(start_cmds) and seen1 and gone2
            got4 = "commands=%d run1 shows line=%s, run2 shows line=%s" % (len(start_cmds), seen1, not gone2)
        results.append(("show-once", ok4,
                        "the SessionStart commands print the summary line once, then nothing on the second run",
                        got4))
    finally:
        shutil.rmtree(H, ignore_errors=True)
        shutil.rmtree(W, ignore_errors=True)

    lines = []
    for name, ok, expected, got in results:
        if ok:
            lines.append("PASS " + name)
        else:
            lines.append("FAIL " + name + " | expected " + expected + " got " + got)
    k = sum(1 for _name, ok, _exp, _got in results if not ok)
    if k == 0:
        lines.append("E2E SUMMARY OK")
    else:
        lines.append("E2E SUMMARY FAILED %d" % k)
    return (0 if k == 0 else 1, lines)


def _copy_public():
    """Copy the whole public folder to a scratch folder and return the copy path."""
    pub = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    dst = tempfile.mkdtemp()
    shutil.copytree(pub, os.path.join(dst, "public"))
    return os.path.join(dst, "public")


def _run_copy(pub):
    """Run the copy's e2e_summary.py with no arguments."""
    return subprocess.run([sys.executable, os.path.join(pub, "tests", "e2e_summary.py")],
                          capture_output=True, text=True)


def _patch(path, old, new):
    """Replace a verbatim string inside one file of a copy."""
    with open(path, "r", encoding="utf-8") as handle:
        text = handle.read()
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text.replace(old, new))


def _autotest():
    script = os.path.abspath(__file__)
    failures = 0

    def run(args):
        return subprocess.run([sys.executable, script] + args, capture_output=True, text=True)

    # Proof 1: the clean-environment run passes on the intact tools
    r = run([])
    lines = r.stdout.splitlines()
    npass = sum(1 for l in lines if l.startswith("PASS "))
    nfail = sum(1 for l in lines if l.startswith("FAIL "))
    expected1 = "code 0, at least 4 PASS lines, no FAIL line, last line E2E SUMMARY OK"
    got1 = "code %d pass=%d fail=%d last=%r" % (r.returncode, npass, nfail, lines[-1] if lines else "")
    ok1 = (r.returncode == 0 and npass >= 4 and nfail == 0
           and bool(lines) and lines[-1] == "E2E SUMMARY OK")
    if ok1:
        print("PASS 1 expected %s | got %s" % (expected1, got1))
    else:
        failures += 1
        print("FAIL 1 expected %s | got %s" % (expected1, got1))

    # Proof 2: --notice follows the contract, an unknown argument is usage 2
    rc_notice = run(["--notice"]).returncode
    rc_check = subprocess.run([sys.executable, os.path.join(BIN, "notice_check.py"), script],
                              capture_output=True, text=True).returncode
    r2 = run(["--nimporte"])
    usage_ok = r2.returncode == 2 and r2.stdout == USAGE
    expected2 = "--notice exits 0 and passes notice_check, unknown arg exits 2 with the usage line"
    got2 = "notice=%d check=%d usage=%s" % (rc_notice, rc_check, usage_ok)
    ok2 = rc_notice == 0 and rc_check == 0 and usage_ok
    if ok2:
        print("PASS 2 expected %s | got %s" % (expected2, got2))
    else:
        failures += 1
        print("FAIL 2 expected %s | got %s" % (expected2, got2))

    # Proof 3: a copy where show never prints the lines fails show-once
    pub = _copy_public()
    _patch(os.path.join(pub, "bin", "session_summary.py"),
           "def show(argv):", "def show(argv):\n    return 0")
    r3 = _run_copy(pub)
    lines3 = r3.stdout.splitlines()
    expected3 = "broken show: code 1, a line starting FAIL show-once, last line E2E SUMMARY FAILED"
    got3 = "code %d last=%r has_fail_show=%s" % (
        r3.returncode, lines3[-1] if lines3 else "",
        any(l.startswith("FAIL show-once") for l in lines3))
    ok3 = (r3.returncode == 1
           and any(l.startswith("FAIL show-once") for l in lines3)
           and bool(lines3) and lines3[-1].startswith("E2E SUMMARY FAILED"))
    if ok3:
        print("PASS 3 expected %s | got %s" % (expected3, got3))
    else:
        failures += 1
        print("FAIL 3 expected %s | got %s" % (expected3, got3))

    # Proof 4: a copy where record hooks point to a no-op flag fails record
    pub = _copy_public()
    _patch(os.path.join(pub, "bin", "frugalflow.py"), "--record-hook", "--record-nothing")
    r4 = _run_copy(pub)
    lines4 = r4.stdout.splitlines()
    expected4 = "broken record: code 1, a line starting FAIL record, last line E2E SUMMARY FAILED"
    got4 = "code %d last=%r has_fail_record=%s" % (
        r4.returncode, lines4[-1] if lines4 else "",
        any(l.startswith("FAIL record") for l in lines4))
    ok4 = (r4.returncode == 1
           and any(l.startswith("FAIL record") for l in lines4)
           and bool(lines4) and lines4[-1].startswith("E2E SUMMARY FAILED"))
    if ok4:
        print("PASS 4 expected %s | got %s" % (expected4, got4))
    else:
        failures += 1
        print("FAIL 4 expected %s | got %s" % (expected4, got4))

    # Proof 5: the test file exists and is not empty
    size = os.path.getsize(script) if os.path.isfile(script) else -1
    expected5 = "the test file exists and is not empty"
    got5 = "isfile=%s size=%d" % (os.path.isfile(script), size)
    ok5 = os.path.isfile(script) and size > 0
    if ok5:
        print("PASS 5 expected %s | got %s" % (expected5, got5))
    else:
        failures += 1
        print("FAIL 5 expected %s | got %s" % (expected5, got5))

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        code, lines = main_run()
        for line in lines:
            print(line)
        sys.exit(code)
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
