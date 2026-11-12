#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""e2e_plugin.py - end-to-end test of the Claude Code plugin layout of this repository."""

import json
import os
import shlex
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

NOTICE = (
    "NAME      e2e_plugin.py - end-to-end test of the plugin layout: manifest, marketplace, hooks, launcher seeding.\n"
    "READS     .claude-plugin/plugin.json, .claude-plugin/marketplace.json, hooks/hooks.json in the repository; runs each hook command with a minimal payload.\n"
    "WRITES    only in temporary folders (HOME, FRUGALFLOW_HOME, pycache), always removed. Exit 0 when every check passes, 1 otherwise.\n"
    "EXAMPLE   python3 e2e_plugin.py\n"
    "PITFALLS  2026-11-13 a hook command written with a clone path breaks when the plugin is installed elsewhere: every command must go through plugin_hook.py under CLAUDE_PLUGIN_ROOT.\n"
)

EVENTS = ("SessionStart", "UserPromptSubmit", "PreToolUse", "PostToolUse", "Stop", "SessionEnd")


def payload(event, cwd, session):
    p = {
        "session_id": session,
        "transcript_path": os.path.join(cwd, "transcript.jsonl"),
        "cwd": cwd,
        "hook_event_name": event,
    }
    if event == "SessionStart":
        p["source"] = "startup"
    elif event == "UserPromptSubmit":
        p["prompt"] = "hello"
    elif event in ("PreToolUse", "PostToolUse"):
        p["tool_name"] = "Write"
        p["tool_input"] = {"file_path": os.path.join(cwd, "note.py"), "content": "x = 1\n"}
        if event == "PostToolUse":
            p["tool_response"] = {"success": True}
    elif event == "Stop":
        p["stop_hook_active"] = False
    return json.dumps(p)


def hook_commands():
    """Yield (event, command) for every hook entry of hooks/hooks.json, in file order."""
    with open(os.path.join(ROOT, "hooks", "hooks.json"), encoding="utf-8") as f:
        doc = json.load(f)
    for event in EVENTS:
        for group in doc["hooks"].get(event, []):
            for entry in group.get("hooks", []):
                yield event, entry["command"]


def main():
    base = tempfile.mkdtemp()
    results = []
    try:
        home = os.path.join(base, "home")
        work = os.path.join(base, "work")
        os.makedirs(work, exist_ok=True)

        # 1. plugin.json and marketplace.json read as JSON, with the fields the manifest needs.
        ok1, detail1 = True, ""
        try:
            with open(os.path.join(ROOT, ".claude-plugin", "plugin.json"), encoding="utf-8") as f:
                plugin = json.load(f)
            with open(os.path.join(ROOT, ".claude-plugin", "marketplace.json"), encoding="utf-8") as f:
                market = json.load(f)
        except (OSError, ValueError) as e:
            ok1, detail1 = False, str(e)
        if ok1:
            for key in ("name", "version", "description", "author", "license", "homepage", "repository"):
                if key not in plugin:
                    ok1, detail1 = False, "plugin.json missing " + key
                    break
        if ok1 and plugin.get("name") != "frugalflow":
            ok1, detail1 = False, "plugin.json name " + str(plugin.get("name"))
        if ok1:
            for key in ("name", "owner", "plugins"):
                if key not in market:
                    ok1, detail1 = False, "marketplace.json missing " + key
                    break
        if ok1:
            entries = market.get("plugins")
            if not isinstance(entries, list) or not entries:
                ok1, detail1 = False, "marketplace.json plugins is not a non-empty list"
            else:
                entry = entries[0]
                source = entry.get("source", "")
                if entry.get("name") != "frugalflow" or not source.startswith("./") or ".." in source:
                    ok1, detail1 = False, "plugins[0] name=" + str(entry.get("name")) + " source=" + source
        results.append(("1 plugin.json and marketplace.json read with their required fields", ok1, detail1))

        # 2. Every hook command, CLAUDE_PLUGIN_ROOT replaced by the repository root, names a file that exists.
        ok2, detail2 = True, ""
        for event, command in hook_commands():
            resolved = command.replace("${CLAUDE_PLUGIN_ROOT}", ROOT)
            tokens = shlex.split(resolved)
            script = tokens[2] if len(tokens) > 2 else ""
            if not os.path.isfile(script):
                ok2, detail2 = False, event + ": " + script + " does not exist"
                break
        results.append(("2 every hook command names a file that exists", ok2, detail2))

        # 3. Each hook command, run with a minimal payload of its event, exits 0 and says no deny on the first run.
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("FRUGALFLOW_") or key == "CLAUDECODE":
                del env[key]
        env["HOME"] = base
        env["FRUGALFLOW_HOME"] = home
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        env["PYTHONPYCACHEPREFIX"] = os.path.join(base, "pycache")

        ok3, detail3 = True, ""
        session = "e2e-plugin-session"
        for event, command in hook_commands():
            resolved = command.replace("${CLAUDE_PLUGIN_ROOT}", ROOT)
            tokens = shlex.split(resolved)
            if tokens[0] == "python3":
                tokens[0] = sys.executable
            proc = subprocess.run(tokens, input=payload(event, work, session),
                                  capture_output=True, text=True, env=env, cwd=work, timeout=60)
            out = proc.stdout + proc.stderr
            if proc.returncode != 0 or "deny" in out:
                ok3 = False
                detail3 = (event + ": rc=" + str(proc.returncode) + " deny=" + str("deny" in out)
                           + " out=" + out[:120])
                break
        results.append(("3 every hook command exits 0 and says no deny on the first run", ok3, detail3))

        # 4. The home was seeded in observe mode; nothing appeared under HOME/.claude.
        ok4 = os.path.isfile(os.path.join(home, "guard.json"))
        detail4 = "guard.json=" + str(ok4)
        claude_dir = os.path.join(base, ".claude")
        if ok4:
            seeded = os.path.isdir(claude_dir) and os.listdir(claude_dir)
            ok4 = not seeded
            detail4 += " .claude entries=" + str(seeded if seeded else "none")
        results.append(("4 the home is seeded and nothing appears under HOME/.claude", ok4, detail4))

        # 5. claude plugin validate . --strict exits 0, when the claude command exists.
        claude_bin = shutil.which("claude")
        if claude_bin is None:
            print("SKIP 5 claude plugin validate (claude not on PATH)")
        else:
            proc = subprocess.run([claude_bin, "plugin", "validate", ".", "--strict"],
                                  cwd=ROOT, capture_output=True, text=True, env=env, timeout=120)
            ok5 = proc.returncode == 0
            detail5 = "rc=" + str(proc.returncode) + " out=" + (proc.stdout + proc.stderr)[:200]
            results.append(("5 claude plugin validate . --strict exits 0", ok5, detail5))
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
