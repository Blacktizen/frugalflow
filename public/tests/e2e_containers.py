#!/usr/bin/env python3
# e2e_containers.py - C2, C3, C7, C9: folders that hold protected files,
# vault journals, and container folders. The guard refuses a move or a
# removal of a folder holding a protected file, refuses a write into the
# journal of a vault, and stays silent on ordinary folders and on container
# folders (node_modules and friends), whatever they hold.
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

NODE_MODULE_COUNT = 21000


def run_hook(home_ff, home_user, work, payload):
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


def bash(work, command):
    return {"tool_name": "Bash", "tool_input": {"command": command}, "cwd": work}


def write_file(work, file_path, content):
    return {"tool_name": "Write", "tool_input": {"file_path": file_path, "content": content}, "cwd": work}


def main():
    tmp = tempfile.mkdtemp(prefix="e2e-containers-", dir="/tmp")
    failures = 0
    try:
        home_ff = os.path.join(tmp, "ff")
        home_user = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        for d in (home_ff, home_user, work):
            os.makedirs(d)
        with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
            json.dump(GUARD_BASE, f)
        for h in (home_ff, home_user):
            with open(os.path.join(h, "preferences.json"), "w", encoding="utf-8") as f:
                json.dump(PREFS, f)
        open(os.path.join(home_ff, "delegations.jsonl"), "w", encoding="utf-8").close()

        # proj: a folder holding a Claude settings file (C2, C9).
        proj = os.path.join(work, "proj")
        os.makedirs(os.path.join(proj, ".claude"))
        with open(os.path.join(proj, ".claude", "settings.json"), "w", encoding="utf-8") as f:
            f.write("{}\n")

        # vault: a folder holding overview.md and log.md, with a journal in a
        # subfolder (C3, C7, C9).
        vault = os.path.join(work, "vault")
        os.makedirs(os.path.join(vault, "sub"))
        for name in ("overview.md", "log.md", os.path.join("sub", "log.md")):
            with open(os.path.join(vault, name), "w", encoding="utf-8") as f:
                f.write("entry\n")

        # build: an ordinary folder holding one small file.
        build = os.path.join(work, "build")
        os.makedirs(build)
        with open(os.path.join(build, "o.txt"), "w", encoding="utf-8") as f:
            f.write("o\n")

        with open(os.path.join(work, "a.txt"), "w", encoding="utf-8") as f:
            f.write("a\n")

        # notes: an ordinary folder with no marker above it up to the
        # temporary folder.
        notes = os.path.join(work, "notes")
        os.makedirs(notes)

        # node_modules: a container folder holding more files than the walk
        # cap; the descent never enters it.
        node_modules = os.path.join(work, "node_modules")
        os.makedirs(node_modules)
        for i in range(NODE_MODULE_COUNT):
            open(os.path.join(node_modules, "f%05d" % i), "w").close()

        cases = []

        _, out = run_hook(home_ff, home_user, work, bash(work, "mv proj proj2"))
        cases.append(("C2 mv of proj holding .claude/settings.json refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm -rf proj"))
        cases.append(("C9 rm -rf proj (relative) refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm -rf " + proj))
        cases.append(("C9 rm -rf proj (absolute) refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "mv vault/overview.md vault/old.md"))
        cases.append(("C3 mv of the vault marker overview.md refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm vault/overview.md"))
        cases.append(("C3 rm of the vault marker overview.md refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work,
                          write_file(work, os.path.join(vault, "sub", "log.md"), "x\n"))
        cases.append(("C7 Write into vault/sub/log.md (journal under a vault) refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm -rf vault"))
        cases.append(("C9 rm -rf vault refuses", decision(out), "deny"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "mv a.txt b.txt"))
        cases.append(("OK mv of an ordinary file allows", decision(out), "allow"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm -rf build"))
        cases.append(("OK rm -rf build holding only o.txt allows", decision(out), "allow"))

        _, out = run_hook(home_ff, home_user, work, bash(work, "rm -rf node_modules"))
        cases.append(("OK rm -rf node_modules holding %d files allows (container folder)" % NODE_MODULE_COUNT,
                      decision(out), "allow"))

        _, out = run_hook(home_ff, home_user, work,
                          write_file(work, os.path.join(notes, "log.md"), "x\n"))
        cases.append(("OK Write notes/log.md with no marker above it allows", decision(out), "allow"))

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
