#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: frugalflow init --here mounts the memory in an existing git repository."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")

USAGE = "usage: e2e_init_here.py | --notice\n"

NOTICE = (
    "NAME      e2e_init_here.py - end-to-end test: frugalflow init --here mounts the vault in a throwaway git repository, keeps every existing file, and never touches the global Claude Code settings.\n"
    "READS     frugalflow.py in ../bin; git, for two throwaway repositories.\n"
    "WRITES    only temporary folders, always removed, even on failure: a disposable HOME, two git repos, their vaults. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_init_here.py\n"
    "PITFALLS  2026-11-13 init --here must not run git init, must not rewrite .gitignore, and must leave a core.hooksPath that already has its value: each is one step here.\n"
    "          GIT_* and CLAUDECODE are stripped from every subprocess: the suite behaves the same inside and outside Claude Code.\n"
)


def make_env(home_path):
    env = {}
    for key, val in os.environ.items():
        if key.startswith("GIT_") or key == "CLAUDECODE" or key.startswith("FRUGALFLOW_"):
            continue
        env[key] = val
    env["HOME"] = home_path
    env["FRUGALFLOW_HOME"] = os.path.join(home_path, "ff")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_ff(env, cwd, *args):
    return subprocess.run(
        [sys.executable, FRUGALFLOW] + list(args),
        capture_output=True, text=True, timeout=120,
        stdin=subprocess.DEVNULL, env=env, cwd=cwd)


def run_git(env, cwd, *args):
    return subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"] + list(args),
        capture_output=True, text=True, timeout=60,
        stdin=subprocess.DEVNULL, env=env, cwd=cwd)


def make_repo(env, path):
    """Create a git repository with a README and a .gitignore, committed once."""
    os.makedirs(path, exist_ok=True)
    with open(os.path.join(path, "README.md"), "w", encoding="utf-8") as handle:
        handle.write("hello\n")
    with open(os.path.join(path, ".gitignore"), "w", encoding="utf-8") as handle:
        handle.write("node_modules/\nbuild/\n")
    for cmd in (["init", "-q"], ["add", "-A"], ["commit", "-q", "-m", "first"]):
        r = run_git(env, path, *cmd)
        if r.returncode != 0:
            return False
    return True


def read_lines(path):
    with open(path, "r", encoding="utf-8") as handle:
        return [line.rstrip("\n") for line in handle.readlines()]


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(sys.argv) > 1:
        sys.stdout.write(USAGE)
        return 2

    tmp = tempfile.mkdtemp()
    env = make_env(os.path.join(tmp, "home"))
    os.makedirs(env["FRUGALFLOW_HOME"], exist_ok=True)
    failed = 0

    def step(num, expected, ok, detail):
        nonlocal failed
        if ok:
            print("PASS step %d: %s" % (num, expected))
        else:
            print("FAIL step %d: expected %s, got %s" % (num, expected, detail))
            failed += 1

    try:
        if not make_repo(env, os.path.join(tmp, "repo")):
            step(0, "git builds a throwaway repository", False, "git init/add/commit failed")
            print("E2E INIT HERE 1 step(s) failed")
            return 1
        repo = os.path.join(tmp, "repo")
        vault = os.path.join(repo, "vault")
        log_path = os.path.join(vault, "log.md")

        # Step 1: init --here exits 0, mounts the vault, prints the guard-mode line last.
        p1 = run_ff(env, repo, "init", "--here")
        out1 = p1.stdout
        last1 = out1.splitlines()[-1] if out1 else ""
        step(1, "init --here exit 0, vault mounted, guard-mode line last",
             p1.returncode == 0
             and os.path.isfile(os.path.join(vault, "overview.md"))
             and os.path.isfile(log_path)
             and last1 == ("Guard mode: observe until you run frugalflow mode active "
                           "(nothing is blocked yet). At the end of a session: "
                           "frugalflow close, then frugalflow resume."),
             "rc=%d last=%r" % (p1.returncode, last1))

        # Step 2: the project hooks are written in the project settings.json.
        settings_path = os.path.join(repo, ".claude", "settings.json")
        hooks_ok = False
        if os.path.isfile(settings_path):
            try:
                with open(settings_path, "r", encoding="utf-8") as handle:
                    cfg = json.load(handle)
                hooks_ok = "hooks" in cfg and "Stop" in cfg["hooks"] and "SessionStart" in cfg["hooks"]
            except ValueError:
                hooks_ok = False
        step(2, "project .claude/settings.json holds the FrugalFlow hooks",
             hooks_ok, "settings_exists=%s" % os.path.isfile(settings_path))

        # Step 3: README intact; .gitignore keeps its lines and gains the two FrugalFlow lines.
        readme_ok = os.path.isfile(os.path.join(repo, "README.md")) and read_bytes(os.path.join(repo, "README.md")) == b"hello\n"
        gi = read_lines(os.path.join(repo, ".gitignore"))
        step(3, "README.md byte-identical; .gitignore keeps node_modules/ and build/ and gains .claude/settings.json and .githooks/",
             readme_ok and gi[:2] == ["node_modules/", "build/"]
             and ".claude/settings.json" in gi and ".githooks/" in gi,
             "readme=%s gitignore=%r" % (readme_ok, gi))

        # Step 4: the global Claude Code settings were not touched.
        step(4, "no CLAUDE.md and no settings.json written under HOME/.claude",
             not os.path.exists(os.path.join(env["HOME"], ".claude", "CLAUDE.md"))
             and not os.path.exists(os.path.join(env["HOME"], ".claude", "settings.json")),
             "claude_md=%s claude_settings=%s" % (
                 os.path.exists(os.path.join(env["HOME"], ".claude", "CLAUDE.md")),
                 os.path.exists(os.path.join(env["HOME"], ".claude", "settings.json"))))

        # Step 5: core.hooksPath now points at .githooks.
        r5 = run_git(env, repo, "config", "core.hooksPath")
        step(5, "core.hooksPath is .githooks",
             r5.returncode == 0 and r5.stdout.strip() == ".githooks",
             "value=%r" % r5.stdout.strip())

        # Step 6: a second init --here says ALREADY MOUNTED, exits 0, writes nothing.
        before = read_bytes(log_path)
        p6 = run_ff(env, repo, "init", "--here")
        step(6, "second init --here exit 0 with ALREADY MOUNTED and log.md byte-identical",
             p6.returncode == 0 and "ALREADY MOUNTED" in p6.stdout and read_bytes(log_path) == before,
             "rc=%d out=%r changed=%s" % (p6.returncode, p6.stdout.splitlines()[:1], read_bytes(log_path) != before))

        # Step 7: frugalflow close on this vault exits 0.
        p7 = run_ff(env, repo, "close", "--vault", vault)
        step(7, "close --vault on the mounted vault exit 0",
             p7.returncode == 0, "rc=%d out=%r" % (p7.returncode, p7.stdout.splitlines()[-1:]))

        # Step 8: a folder without .git is refused with exit 3 and nothing written.
        nogit = os.path.join(tmp, "nogit")
        os.makedirs(nogit, exist_ok=True)
        p8 = run_ff(env, nogit, "init", "--here")
        wrote8 = any(os.path.exists(os.path.join(nogit, name)) for name in ("vault", "bin", ".claude", ".githooks", "bench"))
        step(8, "init --here without .git exit 3 with NO GIT REPOSITORY and nothing written",
             p8.returncode == 3 and "NO GIT REPOSITORY" in p8.stdout and not wrote8,
             "rc=%d wrote=%s out=%r" % (p8.returncode, wrote8, p8.stdout.splitlines()[:1]))

        # Step 9: a repo whose core.hooksPath is already set keeps its value and says the gate is not active.
        repo9 = os.path.join(tmp, "repo9")
        make_repo(env, repo9)
        run_git(env, repo9, "config", "core.hooksPath", "custom-hooks")
        p9 = run_ff(env, repo9, "init", "--here")
        r9 = run_git(env, repo9, "config", "core.hooksPath")
        step(9, "init --here with core.hooksPath=custom-hooks exit 0, value unchanged, COMMIT GATE NOT ACTIVE line",
             p9.returncode == 0 and r9.stdout.strip() == "custom-hooks"
             and "COMMIT GATE NOT ACTIVE: core.hooksPath is already set to custom-hooks" in p9.stdout,
             "rc=%d value=%r out=%r" % (p9.returncode, r9.stdout.strip(), p9.stdout.splitlines()[-2:]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failed:
        print("E2E INIT HERE %d step(s) failed" % failed)
        return 1
    print("E2E INIT HERE ALL STEPS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
