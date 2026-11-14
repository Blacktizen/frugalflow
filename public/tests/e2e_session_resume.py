#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_session_resume.py - end-to-end test: the SessionStart hook injects the resume."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
BIN = os.path.join(ROOT, "public", "bin")
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")
HOOK = os.path.join(BIN, "session_resume.py")

NOTICE = (
    "NAME      e2e_session_resume.py - end-to-end test of the resume injected at SessionStart: vault folder, no-vault folder, the 6000-character cap, the plugin path.\n"
    "READS     public/bin/frugalflow.py, public/bin/session_resume.py, hooks/hooks.json in the repository.\n"
    "WRITES    only in temporary folders (HOME, FRUGALFLOW_HOME, projects, pycache), always removed. Exit 0 when every check passes, 1 otherwise.\n"
    "EXAMPLE   python3 e2e_session_resume.py\n"
    "PITFALLS  2026-11-14 a machine with frugalflow on PATH makes the generated settings name the installed copy, not this repository: the test clears PATH so every hook command runs the repository bin.\n"
)

NEEDLE = "use sqlite"
CONTEXT_LIMIT = 6000
LONG_MARK = "OVERVIEWLONGMARK"


def make_env(base):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("FRUGALFLOW_") or key.startswith("GIT_") or key == "CLAUDECODE":
            del env[key]
    env["HOME"] = os.path.join(base, "home")
    env["FRUGALFLOW_HOME"] = os.path.join(env["HOME"], ".frugalflow")
    env["PATH"] = "/usr/bin:/bin"
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = os.path.join(base, "pycache")
    os.makedirs(env["HOME"], exist_ok=True)
    return env


def session_start_commands(settings_path):
    commands = []
    try:
        with open(settings_path, "r", encoding="utf-8") as handle:
            doc = json.load(handle)
    except (OSError, ValueError):
        return commands
    if not isinstance(doc, dict):
        return commands
    hooks = doc.get("hooks")
    if not isinstance(hooks, dict):
        return commands
    group = hooks.get("SessionStart")
    if not isinstance(group, list):
        return commands
    for entry in group:
        if not isinstance(entry, dict):
            continue
        inner = entry.get("hooks")
        if not isinstance(inner, list):
            continue
        for hook in inner:
            if not isinstance(hook, dict):
                continue
            command = hook.get("command")
            if isinstance(command, str) and command != "":
                commands.append(command)
    return commands


def replay(commands, cwd, env, extra_env=None):
    """Run each SessionStart command with a SessionStart payload; return (codes, joined additionalContext)."""
    run_env = dict(env)
    if extra_env:
        run_env.update(extra_env)
    payload = json.dumps(
        {"session_id": "e2e-resume", "hook_event_name": "SessionStart",
         "source": "startup", "cwd": cwd}
    )
    codes = []
    pieces = []
    for command in commands:
        result = subprocess.run(
            ["/bin/sh", "-c", command], cwd=cwd, env=run_env, input=payload,
            capture_output=True, text=True, timeout=60,
        )
        codes.append(result.returncode)
        out = result.stdout or ""
        if out.strip() == "":
            continue
        try:
            obj = json.loads(out)
        except ValueError:
            continue
        if not isinstance(obj, dict):
            continue
        specific = obj.get("hookSpecificOutput")
        if not isinstance(specific, dict):
            continue
        extra = specific.get("additionalContext")
        if isinstance(extra, str) and extra != "":
            pieces.append(extra)
    return codes, "\n".join(pieces)


def run_hook(payload_text, cwd, env):
    return subprocess.run(
        [sys.executable, "-I", HOOK], input=payload_text, cwd=cwd, env=env,
        capture_output=True, text=True, timeout=30,
    )


def main():
    base = tempfile.mkdtemp()
    results = []
    try:
        env = make_env(base)
        projects = os.path.join(base, "projects")

        # 1. Mount demo, seal one journal entry titled with the needle.
        r1 = subprocess.run(
            [sys.executable, FRUGALFLOW, "new-project", "demo", "--root", projects],
            capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
        )
        proj = os.path.join(projects, "demo")
        vault = os.path.join(proj, "vault")
        ok1 = r1.returncode == 0 and os.path.isdir(vault)
        r2 = None
        if ok1:
            r2 = subprocess.run(
                [sys.executable, FRUGALFLOW, "run", "journal_add",
                 "--vault", vault, "--title", NEEDLE,
                 "--field", "Decision=use sqlite", "--field", "Why=e2e resume"],
                capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
            )
            ok1 = r2.returncode == 0
        detail1 = "new-project rc=%d journal rc=%s" % (
            r1.returncode, r2.returncode if r2 is not None else "skipped")
        results.append(("1 new-project demo + journal_add titled 'use sqlite'", ok1, detail1))

        settings = os.path.join(proj, ".claude", "settings.json")
        start_cmds = session_start_commands(settings)

        # 2. The installed settings name the session_resume command in SessionStart.
        ok2 = any("session_resume" in c for c in start_cmds)
        results.append(("2 settings.json SessionStart names session_resume", ok2,
                        "commands=%d" % len(start_cmds)))

        # 3. Vault folder: the resume is injected, title present, total under 6000.
        codes, context = replay(start_cmds, proj, env)
        ok3 = (all(c == 0 for c in codes) and NEEDLE in context
               and "# Resume:" in context and len(context) < CONTEXT_LIMIT)
        results.append(("3 vault folder: resume injected, title present, under 6000", ok3,
                        "codes=%s len=%d needle=%s" % (codes, len(context), NEEDLE in context)))

        # 4. Folder without a vault: every code 0, no resume, no needle.
        sansvault = os.path.join(base, "sansvault")
        os.makedirs(sansvault, exist_ok=True)
        codes, context = replay(start_cmds, sansvault, env)
        ok4 = (all(c == 0 for c in codes) and "# Resume" not in context
               and NEEDLE not in context)
        results.append(("4 no-vault folder: codes 0, no resume, no needle", ok4,
                        "codes=%s resume=%s needle=%s" % (codes, "# Resume" in context, NEEDLE in context)))

        # 5. A resume past the cap: the progressive fallback keeps the carrier
        # lines, omits the tail line by line, adds pointers, total under 6000.
        r5 = subprocess.run(
            [sys.executable, FRUGALFLOW, "new-project", "big", "--root", projects],
            capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
        )
        big = os.path.join(projects, "big")
        ok5 = r5.returncode == 0 and os.path.isdir(os.path.join(big, "vault"))
        if ok5:
            long_line = LONG_MARK + " " + ("filler word " * 30)
            with open(os.path.join(big, "vault", "overview.md"), "w", encoding="utf-8") as fh:
                fh.write("# big - long overview\n")
                for i in range(20):
                    fh.write("overview line %d %s\n" % (i, long_line))
            with open(os.path.join(big, "vault", "todo.md"), "a", encoding="utf-8") as fh:
                for i in range(40):
                    fh.write("- [ ] (me) open todo %d %s\n" % (i, long_line))
            big_cmds = session_start_commands(os.path.join(big, ".claude", "settings.json"))
            codes, context = replay(big_cmds, big, env)
            ok5 = (all(c == 0 for c in codes)
                   and "run frugalflow resume for the full handoff" in context
                   and "vault/overview.md" in context
                   and "Never edit an old log entry" in context
                   and "open todo 39" not in context
                   and "overview line 19" not in context
                   and len(context) < CONTEXT_LIMIT)
            detail5 = "codes=%s len=%d pointers=%s carrier=%s tail_absent=%s" % (
                codes, len(context),
                "run frugalflow resume for the full handoff" in context,
                "Never edit an old log entry" in context,
                "open todo 39" not in context and "overview line 19" not in context)
        else:
            detail5 = "new-project big rc=%d" % r5.returncode
        results.append(("5 resume past the cap: carrier kept, tail omitted, pointers, under 6000",
                        ok5, detail5))

        # 6. The plugin hooks.json path: session_resume listed, replay injects the title.
        plugin_cmds = session_start_commands(os.path.join(ROOT, "hooks", "hooks.json"))
        plugin_cmds = [c.replace("${CLAUDE_PLUGIN_ROOT}", ROOT) for c in plugin_cmds]
        ok6 = any("session_resume" in c for c in plugin_cmds)
        if ok6:
            codes, context = replay(plugin_cmds, proj, env,
                                    {"CLAUDE_PLUGIN_ROOT": ROOT})
            ok6 = all(c == 0 for c in codes) and NEEDLE in context
            detail6 = "codes=%s needle=%s" % (codes, NEEDLE in context)
        else:
            detail6 = "hooks.json SessionStart has no session_resume command"
        results.append(("6 plugin hooks.json: session_resume replayed, title injected", ok6, detail6))

        # 7. The hook itself: broken JSON and no vault exit 0 with empty stdout;
        #    a vault folder gets a SessionStart hookSpecificOutput.
        proc = run_hook("{not json", proj, env)
        ok7a = proc.returncode == 0 and proc.stdout == ""
        proc = run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": sansvault}),
                        sansvault, env)
        ok7b = proc.returncode == 0 and proc.stdout == ""
        proc = run_hook(json.dumps({"hook_event_name": "SessionStart", "cwd": proj}),
                        proj, env)
        ok7c = False
        if proc.returncode == 0 and proc.stdout != "":
            try:
                obj = json.loads(proc.stdout)
                specific = obj.get("hookSpecificOutput")
                ok7c = (isinstance(specific, dict)
                        and specific.get("hookEventName") == "SessionStart"
                        and NEEDLE in specific.get("additionalContext", ""))
            except ValueError:
                ok7c = False
        ok7 = ok7a and ok7b and ok7c
        results.append(("7 hook edge cases: broken JSON and no vault exit 0 empty; vault injects",
                        ok7, "broken=%s novault=%s vault=%s" % (ok7a, ok7b, ok7c)))

        # 8. A big resume (long journal entries, last entry titled with the
        # needle): the order is carrier lines, then the newest entries, then
        # pointers; total under 6000.
        r8 = subprocess.run(
            [sys.executable, FRUGALFLOW, "new-project", "huge", "--root", projects],
            capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
        )
        huge = os.path.join(projects, "huge")
        ok8 = r8.returncode == 0 and os.path.isdir(os.path.join(huge, "vault"))
        detail8 = "new-project huge rc=%d" % r8.returncode
        if ok8:
            vault8 = os.path.join(huge, "vault")
            for n in range(8):
                rj = subprocess.run(
                    [sys.executable, FRUGALFLOW, "run", "journal_add",
                     "--vault", vault8, "--title", "big decision %02d" % n,
                     "--field", "Decision=big decision %02d sealed" % n,
                     "--field", "Why=" + ("filler text " * 120)],
                    capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
                )
                ok8 = ok8 and rj.returncode == 0
            rj = subprocess.run(
                [sys.executable, FRUGALFLOW, "run", "journal_add",
                 "--vault", vault8, "--title", NEEDLE,
                 "--field", "Decision=use sqlite", "--field", "Why=order check"],
                capture_output=True, text=True, env=env, cwd=env["HOME"], timeout=60,
            )
            ok8 = ok8 and rj.returncode == 0
            if ok8:
                huge_cmds = session_start_commands(os.path.join(huge, ".claude", "settings.json"))
                codes, context = replay(huge_cmds, huge, env)
                carrier = "Never edit an old log entry"
                handoff = "run frugalflow resume for the full handoff"
                ordered = (carrier in context and NEEDLE in context and handoff in context
                           and context.index(carrier) < context.index(NEEDLE)
                           and context.index(NEEDLE) < context.index(handoff))
                ok8 = (all(c == 0 for c in codes) and ordered
                       and "vault/log.md" in context
                       and len(context) < CONTEXT_LIMIT)
                detail8 = "codes=%s len=%d ordered=%s log_pointer=%s" % (
                    codes, len(context), ordered, "vault/log.md" in context)
        results.append(("8 big resume: order carrier lines, newest entries, pointers; under 6000",
                        ok8, detail8))
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
    if "--notice" in sys.argv[1:]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    sys.exit(main())
