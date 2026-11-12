#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""plugin_hook.py - the launcher the Claude Code plugin hooks call, one per hook event."""

import os
import sys

BIN = os.path.dirname(os.path.abspath(__file__))
if BIN not in sys.path:
    sys.path.insert(0, BIN)
# Closed list: a hook command can only launch one of these tools, nothing else.
TOOLS = ("session_log", "r1_guard", "session_summary", "session_banner", "usage_report", "guard_hook")

USAGE = (
    "usage: plugin_hook.py TOOL [ARGS] | --notice | --autotest\n"
    "  TOOL: one of " + ", ".join(TOOLS) + " (ARGS are passed through to the tool)\n"
)

NOTICE = (
    "NAME      plugin_hook.py - the launcher of the plugin hooks: seeds the FrugalFlow home once in observe mode, then runs the named tool.\n"
    "READS     FRUGALFLOW_HOME (else ~/.frugalflow); the config examples in ../config, only when the home does not exist yet; the hook payload on stdin.\n"
    "WRITES    only on the first run, when the home does not exist: the five FrugalFlow settings files in it, in observe mode, never CLAUDE.md, never a Claude Code settings.json; one line on stderr. Then it replaces its process with the tool, stdin included. Exit 2 when the tool is not in the closed list.\n"
    "EXAMPLE   echo '{\"tool_name\": \"Write\", \"tool_input\": {}}' | python3 plugin_hook.py guard_hook --hook\n"
    "PITFALLS  2026-11-13 a launcher that seeded on every run would overwrite settings the user edited: the home is seeded only when it does not exist; an existing home with a missing or broken guard.json stays a refusal, never a free pass.\n"
    "          2026-11-13 a hook command without -I let python run a planted .pth file before the guard: the tool runs with -I, like every FrugalFlow hook command.\n"
)

FIRST_RUN_LINE = ("FrugalFlow plugin: first run, settings written to {home} in observe mode "
                  "(nothing is blocked). frugalflow mode active turns enforcement on.")


def seed(home):
    """Write the five settings files once, in observe mode, reusing init's shared writer."""
    import init_cmd
    init_cmd.write_home_files(home, "observe", quiet=True)


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    if not argv or argv[0] not in TOOLS:
        sys.stderr.write(USAGE)
        return 2

    tool = argv[0]
    home = os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")
    if not os.path.exists(home):
        try:
            seed(home)
        except Exception as exc:
            sys.stderr.write("FrugalFlow plugin: seeding " + home + " failed: " + str(exc) + "\n")
        else:
            sys.stderr.write(FIRST_RUN_LINE.replace("{home}", home) + "\n")
    # An existing home, even an incomplete one, is never re-seeded: a missing or
    # broken guard.json there stays a refusal (the tool itself is fail-closed).
    target = os.path.join(BIN, tool + ".py")
    try:
        os.execv(sys.executable, [sys.executable, "-I", target] + argv[1:])
    except OSError as exc:
        sys.stderr.write("FrugalFlow plugin: cannot run " + target + ": " + str(exc) + "\n")
        return 2


def autotest():
    import json
    import subprocess
    import tempfile
    import shutil

    os.environ.pop("CLAUDECODE", None)
    script = os.path.abspath(__file__)
    base = tempfile.mkdtemp()
    results = []
    try:
        def run(home, *args, stdin_text=""):
            env = dict(os.environ)
            for key in list(env):
                if key.startswith("FRUGALFLOW_"):
                    del env[key]
            env["HOME"] = base
            env["FRUGALFLOW_HOME"] = home
            return subprocess.run([sys.executable, "-I", script] + list(args),
                                  input=stdin_text, capture_output=True, text=True,
                                  env=env, cwd=base, timeout=30)

        write_payload = json.dumps({
            "session_id": "autotest-plugin",
            "cwd": base,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_input": {"file_path": os.path.join(base, "sample.py"), "content": "x = 1\n"},
        })

        # Test 1: first launch seeds the home in observe mode: guard.json exists, no deny.
        home1 = os.path.join(base, "home1")
        r1 = run(home1, "guard_hook", "--hook", stdin_text=write_payload)
        ok1 = (r1.returncode == 0
               and os.path.isfile(os.path.join(home1, "guard.json"))
               and "deny" not in r1.stdout
               and "first run, settings written to " + home1 in r1.stderr)
        results.append(("1 first launch seeds the home, guard.json exists, no deny", ok1,
                        "rc=%d guard=%s deny=%s" % (r1.returncode, os.path.isfile(os.path.join(home1, "guard.json")), "deny" in r1.stdout)))

        # Test 2: a tool outside the closed list is refused with 2 and launches nothing.
        r2 = run(home1, "rm_rf", home1)
        ok2 = r2.returncode == 2 and os.path.isdir(home1)
        results.append(("2 a tool outside the closed list is 2 and launches nothing", ok2,
                        "rc=%d home_kept=%s" % (r2.returncode, os.path.isdir(home1))))

        # Test 3: an existing home without guard.json stays a refusal: the output says deny.
        home3 = os.path.join(base, "home3")
        os.makedirs(home3, exist_ok=True)
        r3 = run(home3, "guard_hook", "--hook", stdin_text=write_payload)
        ok3 = r3.returncode == 0 and "deny" in r3.stdout and "first run" not in r3.stderr
        results.append(("3 an existing home without guard.json says deny", ok3,
                        "rc=%d deny=%s" % (r3.returncode, "deny" in r3.stdout)))

        # Test 4: --notice prints the notice with exit 0; no argument is usage 2.
        r4 = subprocess.run([sys.executable, "-I", script, "--notice"], capture_output=True, text=True, timeout=30)
        r5 = subprocess.run([sys.executable, "-I", script], capture_output=True, text=True, timeout=30)
        ok4 = (r4.returncode == 0 and r4.stdout.startswith("NAME      plugin_hook.py")
               and r5.returncode == 2)
        results.append(("4 --notice exits 0 with the notice, no argument is 2", ok4,
                        "notice_rc=%d noargs_rc=%d" % (r4.returncode, r5.returncode)))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + " | " + detail)
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
