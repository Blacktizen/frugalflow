#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the guided setup."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

BEGIN = "<!-- FRUGALFLOW begin -->"
END = "<!-- FRUGALFLOW end -->"
CONTENT = "\n".join("line %d" % i for i in range(60)) + "\n"

USAGE = "usage: e2e_setup.py [--notice | --autotest]\n"

NOTICE = (
    "NAME      e2e_setup.py - end-to-end test of the guided setup: runs frugalflow init, doctor, config, on, off and the guard hook in temporary folders.\n"
    "READS     the tools in ../bin: frugalflow.py, guard_hook.py and their neighbours.\n"
    "WRITES    only in temporary folders, always removed, even on failure. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_setup.py\n"
    "PITFALLS  2026-10-03 the guard only refuses in active mode; observe counts and lets pass, so the on/off step installs with --mode active on purpose.\n"
)


def ff(tmp, home, claude, *args):
    """Run frugalflow.py with the options its subcommand accepts."""
    env = dict(os.environ)
    env["HOME"] = tmp
    cmd = [sys.executable, os.path.join(BIN, "frugalflow.py")]
    cmd.extend(args)
    if args and args[0] in ("init", "doctor"):
        cmd += ["--home", home, "--claude-dir", claude,
                "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"]
    else:
        cmd += ["--home", home]
    return subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmp)


def guard(tmp, home, tool_name, tool_input):
    """Run guard_hook.py --hook against home; return the completed process."""
    env = dict(os.environ)
    env["HOME"] = tmp
    env["FRUGALFLOW_HOME"] = home
    env.pop("FRUGALFLOW_GUARD", None)
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
    return subprocess.run(
        [sys.executable, os.path.join(BIN, "guard_hook.py"), "--hook"],
        input=payload, capture_output=True, text=True, env=env, cwd=tmp)


def make_env(tmp, label):
    home = os.path.join(tmp, label, "home")
    claude = os.path.join(tmp, label, "claude")
    os.makedirs(claude, exist_ok=True)
    return home, claude


def _step1(tmp):
    home, claude = make_env(tmp, "s1")
    if ff(tmp, home, claude, "init").returncode != 0:
        return False
    if ff(tmp, home, claude, "init").returncode != 0:
        return False
    claude_md = os.path.join(claude, "CLAUDE.md")
    with open(claude_md, encoding="utf-8") as f:
        text = f.read()
    if text.count(BEGIN) != 1 or text.count(END) != 1:
        return False
    with open(os.path.join(claude, "settings.json"), encoding="utf-8") as f:
        raw = f.read()
    return raw.count("guard_hook.py") == 1


def _step2(tmp):
    home, claude = make_env(tmp, "s2")
    original = "alpha line\nbeta line\n"
    claude_md = os.path.join(claude, "CLAUDE.md")
    with open(claude_md, "w", encoding="utf-8", newline="") as f:
        f.write(original)
    if ff(tmp, home, claude, "init").returncode != 0:
        return False
    with open(claude_md, encoding="utf-8", newline="") as f:
        after = f.read()
    if not after.startswith(original):
        return False
    if after.count(BEGIN) != 1 or after.count(END) != 1:
        return False
    if ff(tmp, home, claude, "init", "--remove").returncode != 0:
        return False
    with open(claude_md, encoding="utf-8", newline="") as f:
        restored = f.read()
    return restored == original


def _step3(tmp):
    home, claude = make_env(tmp, "s3")
    if ff(tmp, home, claude, "init").returncode != 0:
        return False
    if ff(tmp, home, claude, "doctor").returncode != 0:
        return False
    os.remove(os.path.join(home, "guard.json"))
    return ff(tmp, home, claude, "doctor").returncode == 1


def _step4(tmp):
    home, claude = make_env(tmp, "s4")
    if ff(tmp, home, claude, "init", "--mode", "active").returncode != 0:
        return False
    call = {"file_path": "/w/big.py", "content": CONTENT}
    if ff(tmp, home, claude, "off").returncode != 0:
        return False
    g_off = guard(tmp, home, "Write", call)
    if g_off.returncode != 0 or g_off.stdout != "":
        return False
    if ff(tmp, home, claude, "on").returncode != 0:
        return False
    g_on = guard(tmp, home, "Write", call)
    return g_on.returncode == 0 and '"deny"' in g_on.stdout


def steps(tmp):
    labels = [
        "init twice leaves one block and one hook",
        "a filled CLAUDE.md keeps its head byte for byte and --remove restores it",
        "doctor exits 0 after init and 1 after guard.json is removed",
        "off lets a 60-line code write pass and on refuses it",
    ]
    fns = [_step1, _step2, _step3, _step4]
    results = []
    for label, fn in zip(labels, fns):
        try:
            ok = fn(tmp)
        except Exception:
            ok = False
        results.append((label, bool(ok)))
    return results


def main_run(parent):
    tmp = tempfile.mkdtemp(dir=parent)
    try:
        results = steps(tmp)
    finally:
        shutil.rmtree(tmp)
    lines = []
    for i, (label, ok) in enumerate(results, 1):
        if ok:
            lines.append("PASS {} {}".format(i, label))
        else:
            lines.append("FAIL {} {}".format(i, label))
    k = sum(1 for _, ok in results if not ok)
    if k == 0:
        lines.append("E2E SETUP OK")
    else:
        failed = [label for label, ok in results if not ok]
        lines.append("E2E SETUP FAILED: " + "; ".join(failed))
    code = 0 if k == 0 else 1
    return (code, lines)


def _autotest():
    script = os.path.abspath(__file__)
    failures = 0

    # Proof 1: --notice
    r = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    expected1 = "code 0 and stdout starts NAME      e2e_setup.py"
    got1 = "code {} stdout starts {}".format(r.returncode, repr(r.stdout[:30]))
    ok1 = (r.returncode == 0 and r.stdout.startswith("NAME      e2e_setup.py"))
    if not r.stdout:
        ok1 = False
    if ok1:
        print("PASS 1 expected {} | got {}".format(expected1, got1))
    else:
        failures += 1
        print("FAIL 1 expected {} | got {}".format(expected1, got1))

    # Proof 2: --bogus
    r = subprocess.run([sys.executable, script, "--bogus"], capture_output=True, text=True)
    expected2 = "code 2 and stdout == usage line"
    got2 = "code {} stdout == {}".format(r.returncode, repr(r.stdout))
    ok2 = (r.returncode == 2 and r.stdout == USAGE)
    if not r.stdout:
        ok2 = False
    if ok2:
        print("PASS 2 expected {} | got {}".format(expected2, got2))
    else:
        failures += 1
        print("FAIL 2 expected {} | got {}".format(expected2, got2))

    # Proof 3: main_run cleans up
    tmp_parent = tempfile.mkdtemp()
    try:
        main_run(tmp_parent)
        got3 = "listdir={}".format(os.listdir(tmp_parent))
        ok3 = (os.listdir(tmp_parent) == [])
    except Exception as e:
        got3 = "exception: {}".format(e)
        ok3 = False
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)
    expected3 = "parent dir empty after main_run"
    if ok3:
        print("PASS 3 expected {} | got {}".format(expected3, got3))
    else:
        failures += 1
        print("FAIL 3 expected {} | got {}".format(expected3, got3))

    # Proof 4: main_run return structure
    tmp_parent2 = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent2)
        got4 = "code={} len(lines)={} first4_ok={} last_start={}".format(
            code, len(lines),
            all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:4]),
            repr(lines[4][:11]) if len(lines) > 4 else "N/A")
        ok4 = (
            code in (0, 1)
            and len(lines) == 5
            and all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:4])
            and lines[4].startswith("E2E SETUP ")
        )
    except Exception as e:
        got4 = "exception: {}".format(e)
        ok4 = False
    finally:
        shutil.rmtree(tmp_parent2, ignore_errors=True)
    expected4 = "code in (0,1), 5 lines: 4 PASS/FAIL + 1 E2E SETUP"
    if ok4:
        print("PASS 4 expected {} | got {}".format(expected4, got4))
    else:
        failures += 1
        print("FAIL 4 expected {} | got {}".format(expected4, got4))

    # Proof 5: consistency of FAIL count, last line, and code
    tmp_parent3 = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent3)
        k = sum(1 for l in lines[:4] if l.startswith("FAIL "))
        failed_labels = [l.split(" ", 2)[2] for l in lines[:4] if l.startswith("FAIL ")]
        if k == 0:
            expected_last = "E2E SETUP OK"
            expected_code = 0
        else:
            expected_last = "E2E SETUP FAILED: " + "; ".join(failed_labels)
            expected_code = 1
        got5 = "k={} last={} code={}".format(k, lines[4], code)
        ok5 = (lines[4] == expected_last and code == expected_code)
    except Exception as e:
        got5 = "exception: {}".format(e)
        ok5 = False
    finally:
        shutil.rmtree(tmp_parent3, ignore_errors=True)
    expected5 = "FAIL count matches last line and exit code"
    if ok5:
        print("PASS 5 expected {} | got {}".format(expected5, got5))
    else:
        failures += 1
        print("FAIL 5 expected {} | got {}".format(expected5, got5))

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        code, lines = main_run(None)
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
