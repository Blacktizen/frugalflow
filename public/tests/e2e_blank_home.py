#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the blank-HOME stranger."""

import os
import re
import sys
import shutil
import tempfile
import subprocess

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

USAGE = "usage: e2e_blank_home.py [--notice | --autotest]\n"

NOTICE = (
    "NAME      e2e_blank_home.py - end-to-end test of the blank-HOME stranger: runs the real frugalflow.py in a clean environment and temporary folders, then checks the real home stayed untouched.\n"
    "READS     the tools in ../bin (frugalflow.py and its subcommands) and the real home of the user running the test (~/.frugalflow and ~/.claude/settings.json).\n"
    "WRITES    only in two temporary folders, always removed, even on failure. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_blank_home.py\n"
    "PITFALLS  2026-10-04 a test run with the developer's own environment variables proves nothing for a stranger: every step runs with a clean environment.\n"
    "          2026-10-10 init now names files beside bin/ (examples/); the whole install folder, not bin/ alone, is excluded from the leak search.\n"
)


def _ff(env, work, *args):
    """Run the real frugalflow.py in a clean environment, cwd = work."""
    cmd = [sys.executable, os.path.join(BIN, "frugalflow.py")]
    cmd.extend(args)
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=work)


def _snap(real_home):
    """Snapshot the names and mtimes of the real home pieces the stranger must not touch."""
    snap = {}
    ff = os.path.join(real_home, ".frugalflow")
    if os.path.isdir(ff):
        entries = {}
        for root, _dirs, files in os.walk(ff):
            for name in files:
                path = os.path.join(root, name)
                entries[os.path.relpath(path, ff)] = os.path.getmtime(path)
        snap["frugalflow"] = entries
    elif os.path.exists(ff):
        snap["frugalflow"] = {"<file>": os.path.getmtime(ff)}
    settings = os.path.join(real_home, ".claude", "settings.json")
    if os.path.isfile(settings):
        snap["settings.json"] = os.path.getmtime(settings)
    return snap


def _snap_diff(before, after):
    """One short word describing which snapshotted piece changed."""
    changed = [key for key in sorted(set(before) | set(after)) if before.get(key) != after.get(key)]
    return "changed=" + ",".join(changed) if changed else "unexplained"


def _doctor_ok(proc):
    """doctor exits 0/1 and every FAIL/MISSING line carries a fix hint on the same line."""
    if proc.returncode not in (0, 1):
        return False, "exit %d not in (0, 1)" % proc.returncode
    lines = proc.stdout.splitlines()
    for line in lines:
        if ("FAIL" in line) or ("MISSING" in line):
            if not (("run" in line) or ("set" in line) or ("install" in line)):
                return False, "line without a fix hint: " + repr(line)
    return True, "exit %d, %d line(s), all FAIL/MISSING lines carry a fix hint" % (proc.returncode, len(lines))


def _leaks(text, home_base, real_home):
    """True if text carries the real home path or a macOS home path /<name> that is not the temp home; the install folder (the parent of BIN) is not a leak."""
    text = text.replace(os.path.dirname(BIN), "")
    if real_home and real_home in text:
        return True
    for match in re.finditer(r"/[U]sers/([^/\s]+)", text):
        if match.group(1) != home_base:
            return True
    return False


def _scan_strings(H, W, outputs):
    """Every string to inspect: the three steps' outputs, then each file path and content under H and W."""
    strings = list(outputs)
    for base in (H, W):
        for root, _dirs, files in os.walk(base):
            for name in files:
                path = os.path.join(root, name)
                strings.append(path)
                try:
                    with open(path, "r", encoding="utf-8", errors="ignore") as handle:
                        strings.append(handle.read())
                except OSError:
                    pass
    return strings


def main_run():
    real_home = os.path.expanduser("~")
    H = tempfile.mkdtemp()
    W = tempfile.mkdtemp()
    results = []
    try:
        env = {"PATH": os.environ["PATH"], "HOME": H}
        home_base = os.path.basename(H)
        outputs = []
        before = _snap(real_home)

        # Step 1: init
        r1 = _ff(env, W, "init", "--mode", "observe")
        outputs.append(r1.stdout)
        outputs.append(r1.stderr)
        ok1 = r1.returncode == 0
        results.append(("init", ok1, "init --mode observe exits 0", "exit %d" % r1.returncode))

        # Step 2: doctor
        r2 = _ff(env, W, "doctor")
        outputs.append(r2.stdout)
        outputs.append(r2.stderr)
        ok2, got2 = _doctor_ok(r2)
        results.append(("doctor", ok2,
                        "doctor exits 0 or 1 and every FAIL/MISSING line carries a fix hint", got2))

        # Step 3: new-project
        r3 = _ff(env, W, "new-project", "demo")
        outputs.append(r3.stdout)
        outputs.append(r3.stderr)
        demo = os.path.join(W, "demo")
        ok3 = r3.returncode == 0 and os.path.isdir(demo)
        results.append(("new-project", ok3,
                        "new-project demo exits 0 and creates the folder demo under W",
                        "exit %d, demo under W exists=%s" % (r3.returncode, os.path.isdir(demo))))

        # Step 4: stays-home
        after = _snap(real_home)
        ok4 = before == after
        got4 = "real home unchanged" if ok4 else "real home changed: " + _snap_diff(before, after)
        results.append(("stays-home", ok4,
                        "no file created or changed in the real home (~/.frugalflow, ~/.claude/settings.json)",
                        got4))

        # Step 5: no-private-path
        found = None
        for text in _scan_strings(H, W, outputs):
            if _leaks(text, home_base, real_home):
                found = text
                break
        ok5 = found is None
        got5 = "%d string(s) free of the real home" % len(outputs) if ok5 else \
            "leak: " + found[:120].replace("\n", " ")
        results.append(("no-private-path", ok5,
                        "no file under H or W and no step 1-3 output carries the real home path",
                        got5))
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
        lines.append("E2E BLANK HOME OK")
    else:
        lines.append("E2E BLANK HOME FAILED %d" % k)
    return (0 if k == 0 else 1, lines)


def _autotest():
    script = os.path.abspath(__file__)
    failures = 0

    def run(args):
        return subprocess.run([sys.executable, script] + args, capture_output=True, text=True)

    # Proof 1: --notice
    r = run(["--notice"])
    expected1 = "code 0 and stdout starts NAME      e2e_blank_home.py"
    got1 = "code {} stdout starts {}".format(r.returncode, repr(r.stdout[:30]))
    ok1 = (r.returncode == 0 and r.stdout.startswith("NAME      e2e_blank_home.py"))
    if not r.stdout:
        ok1 = False
    if ok1:
        print("PASS 1 expected {} | got {}".format(expected1, got1))
    else:
        failures += 1
        print("FAIL 1 expected {} | got {}".format(expected1, got1))

    # Proof 2: an unknown argument is usage 2
    r = run(["--bogus"])
    expected2 = "code 2 and stdout == the usage line"
    got2 = "code {} stdout {}".format(r.returncode, repr(r.stdout))
    ok2 = (r.returncode == 2 and r.stdout == USAGE)
    if not r.stdout:
        ok2 = False
    if ok2:
        print("PASS 2 expected {} | got {}".format(expected2, got2))
    else:
        failures += 1
        print("FAIL 2 expected {} | got {}".format(expected2, got2))

    # Proof 3: the clean-environment run passes on the intact tools
    r = run([])
    lines = r.stdout.splitlines()
    expected3 = "code 0, five PASS lines, last line E2E BLANK HOME OK"
    got3 = "code {} nlines={} last={}".format(
        r.returncode, len(lines), repr(lines[-1]) if lines else "EMPTY")
    ok3 = (r.returncode == 0
           and len(lines) == 6
           and all(l.startswith("PASS ") for l in lines[:5])
           and lines[5] == "E2E BLANK HOME OK")
    if ok3:
        print("PASS 3 expected {} | got {}".format(expected3, got3))
    else:
        failures += 1
        print("FAIL 3 expected {} | got {}".format(expected3, got3))

    # Proof 4: the run returns one PASS/FAIL line per step plus the E2E line
    r = run([])
    lines = r.stdout.splitlines()
    expected4 = "code in (0,1), 6 lines: five PASS/FAIL + one E2E BLANK HOME"
    got4 = "code {} nlines={} first5_ok={} last_start={}".format(
        r.returncode, len(lines),
        all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:5]),
        repr(lines[5][:11]) if len(lines) > 5 else "N/A")
    ok4 = (r.returncode in (0, 1)
           and len(lines) == 6
           and all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:5])
           and lines[5].startswith("E2E BLANK HOME "))
    if ok4:
        print("PASS 4 expected {} | got {}".format(expected4, got4))
    else:
        failures += 1
        print("FAIL 4 expected {} | got {}".format(expected4, got4))

    # Proof 5: the FAIL count matches the last line and the exit code
    r = run([])
    lines = r.stdout.splitlines()
    k = sum(1 for l in lines[:5] if l.startswith("FAIL "))
    if k == 0:
        exp_last, exp_code = "E2E BLANK HOME OK", 0
    else:
        exp_last, exp_code = "E2E BLANK HOME FAILED " + str(k), 1
    expected5 = "FAIL count %d matches the last line and the exit code" % k
    got5 = "k={} last={} code={}".format(
        k, repr(lines[5]) if len(lines) > 5 else "N/A", r.returncode)
    ok5 = (len(lines) > 5 and lines[5] == exp_last and r.returncode == exp_code)
    if ok5:
        print("PASS 5 expected {} | got {}".format(expected5, got5))
    else:
        failures += 1
        print("FAIL 5 expected {} | got {}".format(expected5, got5))

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
