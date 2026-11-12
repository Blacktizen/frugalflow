#!/usr/bin/env python3
# e2e_install_state.py - D4 (the setup manifest and its backups are protected, and a
# restore only acts inside the install folders) and D5 (the session logs are protected).
# Each case prints one PASS or FAIL line; exit 1 if any case fails.

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
HOOK = os.path.join(BIN, "guard_hook.py")
INIT = os.path.join(BIN, "init_cmd.py")
UNINSTALL = os.path.join(BIN, "uninstall_cmd.py")
sys.path.insert(0, BIN)
import setup_manifest

GUARD_BASE = {
    "code_extensions": [".py", ".sh", ".js", ".ts", ".ipynb"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "delegate_tools": ["delegate.py"],
    "fix_hint": "delegate it.",
}

PREFS = {"schema_version": "1", "switch": {"enabled": True, "mode": "active"}}

SESSION_LOG = os.path.join("sessions", "2026-11-06", "abc.jsonl")


def run_hook(home_ff, home_user, work, payload):
    with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(GUARD_BASE, f)
    with open(os.path.join(home_ff, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    with open(os.path.join(home_user, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    open(os.path.join(home_ff, "delegations.jsonl"), "w", encoding="utf-8").close()
    env = {
        "PATH": "/opt/homebrew/bin:/usr/bin:/bin",
        "FRUGALFLOW_HOME": home_ff,
        "HOME": home_user,
    }
    r = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=30,
    )
    return r.returncode, r.stdout.strip()


def decision(stdout):
    if not stdout:
        return "allow"
    try:
        d = json.loads(stdout.splitlines()[-1])
        return d.get("hookSpecificOutput", {}).get("permissionDecision", "allow")
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return "unreadable"


def cmd_env(home_user, tmp):
    env = dict(os.environ)
    env["HOME"] = home_user
    env["USERPROFILE"] = home_user
    env.pop("FRUGALFLOW_HOME", None)
    for k in list(env):
        if k.startswith("GIT_"):
            del env[k]
    pycache = os.path.join(tmp, "_pyc")
    os.makedirs(pycache, exist_ok=True)
    env["PYTHONPYCACHEPREFIX"] = pycache
    return env


def main():
    tmp = tempfile.mkdtemp(prefix="e2e-install-state-", dir="/tmp")
    failures = 0
    try:
        home_ff = os.path.join(tmp, "ff")
        home_user = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        for d in (home_ff, home_user, work):
            os.makedirs(d)
        cases = []

        # D4: the manifest decides what an uninstall deletes; only setup writes it.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write",
                           "tool_input": {"file_path": os.path.join(home_ff, "setup-manifest.json"),
                                          "content": '{"version": 1, "entries": []}\n'}})
        cases.append(("D4 Write of setup-manifest.json refuses", decision(out), "deny"))

        # D4: the backups hold the originals; only setup writes them.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write",
                           "tool_input": {"file_path": os.path.join(home_ff, "setup-backups", "1-CLAUDE.md"),
                                          "content": "forged original\n"}})
        cases.append(("D4 Write of a file in setup-backups refuses", decision(out), "deny"))

        # D5: a session log is the trace of a gesture; rewriting it erases the proof.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write",
                           "tool_input": {"file_path": os.path.join(home_ff, SESSION_LOG),
                                          "content": "forged session\n"}})
        cases.append(("D5 Write of a session log refuses", decision(out), "deny"))

        # D5: an Edit of the same log is refused too.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Edit",
                           "tool_input": {"file_path": os.path.join(home_ff, SESSION_LOG),
                                          "old_string": "a", "new_string": "b"}})
        cases.append(("D5 Edit of a session log refuses", decision(out), "deny"))

        # D4: a Bash append to the manifest is refused.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Bash",
                           "tool_input": {"command": "echo x >> " + os.path.join(home_ff, "setup-manifest.json")}})
        cases.append(("D4 Bash append to setup-manifest.json refuses", decision(out), "deny"))

        # D5: a Bash append to a session log is refused.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Bash",
                           "tool_input": {"command": "echo x >> " + os.path.join(home_ff, SESSION_LOG)}})
        cases.append(("D5 Bash append to a session log refuses", decision(out), "deny"))

        # D4: rm -rf of the backup folder is refused.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Bash",
                           "tool_input": {"command": "rm -rf " + os.path.join(home_ff, "setup-backups")}})
        cases.append(("D4 Bash rm -rf of setup-backups refuses", decision(out), "deny"))

        # Control: reading a session log stays free.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Bash",
                           "tool_input": {"command": "cat " + os.path.join(home_ff, SESSION_LOG)}})
        cases.append(("OK Bash cat of a session log allows", decision(out), "allow"))

        # Control: an ordinary small file in the work folder is allowed.
        _, out = run_hook(home_ff, home_user, work,
                          {"tool_name": "Write",
                           "tool_input": {"file_path": os.path.join(work, "s.py"), "content": "a = 1\n"}})
        cases.append(("OK Write of a small .py in the work folder allows", decision(out), "allow"))

        # D4: a manifest naming a file outside the install folders is skipped, not deleted.
        ff2 = os.path.join(tmp, "ff2")
        cl2 = os.path.join(tmp, "cl2")
        outside = os.path.join(tmp, "outside")
        for d in (ff2, cl2, outside):
            os.makedirs(d)
        secret = os.path.join(outside, "secret.txt")
        with open(secret, "w", encoding="utf-8") as f:
            f.write("do not delete me\n")
        manifest = {"version": 1, "entries": [
            {"path": secret, "existed": False, "backup": None, "after_sha": None},
        ]}
        with open(os.path.join(ff2, "setup-manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f)
        r = subprocess.run(
            [sys.executable, UNINSTALL, "--home", ff2, "--claude-dir", cl2],
            capture_output=True, text=True, env=cmd_env(home_user, tmp), timeout=300,
        )
        survived = os.path.isfile(secret) and open(secret, encoding="utf-8").read() == "do not delete me\n"
        got = (r.returncode == 0
               and "SKIPPED " + secret + ": outside the install folders" in r.stdout
               and survived)
        cases.append(("D4 uninstall skips a manifest entry outside the install folders", got, True))

        # Control: a normal init then uninstall in a throwaway HOME still works.
        ff3 = os.path.join(tmp, "ff3")
        cl3 = os.path.join(tmp, "cl3")
        for d in (ff3, cl3):
            os.makedirs(d)
        ORIGINAL = "# my notes\n"
        claude_md = os.path.join(cl3, "CLAUDE.md")
        with open(claude_md, "w", encoding="utf-8", newline="") as f:
            f.write(ORIGINAL)
        created = [os.path.join(ff3, n + ".json")
                   for n in ("models", "preferences", "guard", "anonymization", "model_notes")]
        m = setup_manifest.snapshot(ff3, [claude_md] + created)
        env = cmd_env(home_user, tmp)
        subprocess.run(
            [sys.executable, INIT, "--home", ff3, "--claude-dir", cl3,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env, timeout=300,
        )
        setup_manifest.finish(ff3, m)
        r3 = subprocess.run(
            [sys.executable, UNINSTALL, "--home", ff3, "--claude-dir", cl3],
            capture_output=True, text=True, env=env, timeout=300,
        )
        content = open(claude_md, encoding="utf-8").read() if os.path.isfile(claude_md) else None
        got = (r3.returncode == 0
               and "RESTORED " + claude_md in r3.stdout
               and content == ORIGINAL
               and all("REMOVED " + p in r3.stdout and not os.path.isfile(p) for p in created))
        cases.append(("OK init then uninstall restores CLAUDE.md and removes the setup files", got, True))

        for name, got, want in cases:
            ok = got == want
            if not ok:
                failures += 1
            print("%s  %s  (expected %s, got %s)" % ("PASS" if ok else "FAIL", name, want, got))
        print("SUMMARY %d / %d" % (len(cases) - failures, len(cases)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
