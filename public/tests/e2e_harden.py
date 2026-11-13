#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test: frugalflow harden turns the isolated mode on, doctor reports it, --remove takes it back."""

import os
import sys
import json
import glob
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))
FRUGALFLOW = os.path.join(BIN, "frugalflow.py")

USAGE = "usage: e2e_harden.py | --notice\n"

NOTICE = (
    "NAME      e2e_harden.py - end-to-end test: runs frugalflow.py harden and frugalflow.py doctor against a disposable claude dir and home, in subprocesses.\n"
    "READS     the tools in ../bin, frugalflow.py, harden_cmd.py, doctor_cmd.py.\n"
    "WRITES    only a temporary folder, always removed, even on failure: a disposable HOME, a claude dir holding one settings.json, a FrugalFlow home, one project folder. Exit 0 all fourteen steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_harden.py\n"
    "PITFALLS  2026-11-13 the subprocesses get CLAUDECODE dropped: harden refuses without a terminal, and this test must run inside a Claude Code session too.\n"
    "          2026-11-13 doctor may exit 1 here (the home holds no models.json): the isolation line is INFO, so the steps check the line, never the exit code.\n"
    "          2026-11-13 --remove must give back the original JSON object, not a rewritten one: the step compares objects, and a leftover key fails step 5.\n"
    "          2026-11-13 guard.json can name a delegation log outside the home: harden protects it too (step 9), and a log inside the home adds no extra entry — the home rule already covers it.\n"
    "          2026-11-13 the settings copies go to <home>/harden-backups/, never next to settings.json: the copy beside the settings was itself a writable target (adversarial review); step 12 checks the location and the harden.json list.\n"
    "          2026-11-13 Claude Code loads CLAUDE.local.md at the root and CLAUDE.md/CLAUDE.local.md of subfolders: step 13 checks they are protected (existing files literally, later files through the /** pattern rules), step 14 checks --allow-instructions leaves every one of them free.\n"
)

ORIG = {"model": "x", "permissions": {"deny": ["Bash(rm:*)"]}}


def make_env(tmp):
    env = dict(os.environ)
    env["HOME"] = tmp
    env["PYTHONPYCACHEPREFIX"] = os.path.join(tmp, "pycache")
    for name in list(env):
        if name.endswith("_API_KEY") or name in ("FRUGALFLOW_HOME", "CLAUDECODE"):
            env.pop(name)
    return env


def run_frugalflow(env, cwd, *args):
    return subprocess.run(
        [sys.executable, FRUGALFLOW] + list(args),
        capture_output=True, text=True, input="", env=env, cwd=cwd)


def read_settings(settings_path):
    with open(settings_path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def read_bytes(path):
    with open(path, "rb") as handle:
        return handle.read()


def backup_count(home):
    return len(glob.glob(os.path.join(home, "harden-backups", "settings.json.before-frugalflow-*")))


def covered(deny_write, deny, path, is_dir):
    """True when path is in denyWrite and carries its Edit rule (/** for a folder)."""
    if path not in deny_write:
        return False
    pl = path.lstrip("/")
    rule = "Edit(//" + pl + ("/**)" if is_dir else ")")
    return rule in deny


def _step1(env, tmp, home, claude, settings_path):
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home)
    expected = ("harden exits 0; settings.json keeps model x and deny Bash(rm:*); sandbox.enabled true, "
                "allowUnsandboxedCommands false, failIfUnavailable true; denyWrite holds the home; "
                "permissions.deny holds an Edit rule for the home; home/harden.json exists and one "
                "backup sits in home/harden-backups")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    try:
        doc = read_settings(settings_path)
    except (OSError, ValueError) as error:
        return False, expected, "code=0 settings.json unreadable: " + str(error)
    sandbox = doc.get("sandbox") if isinstance(doc.get("sandbox"), dict) else {}
    deny_write = sandbox.get("filesystem", {}).get("denyWrite", []) if isinstance(sandbox.get("filesystem"), dict) else []
    deny = doc.get("permissions", {}).get("deny", [])
    ok = (doc.get("model") == "x" and "Bash(rm:*)" in deny
          and sandbox.get("enabled") is True and sandbox.get("allowUnsandboxedCommands") is False
          and sandbox.get("failIfUnavailable") is True
          and home in deny_write
          and any(d.startswith("Edit(") and home.lstrip("/") in d for d in deny)
          and os.path.isfile(os.path.join(home, "harden.json"))
          and backup_count(home) == 1)
    got = ("code=0 model=" + repr(doc.get("model")) + " enabled=" + repr(sandbox.get("enabled"))
           + " no_escape=" + repr(sandbox.get("allowUnsandboxedCommands"))
           + " fail_if_unavailable=" + repr(sandbox.get("failIfUnavailable"))
           + " denyWrite_home=" + str(home in deny_write)
           + " deny_Edit_home=" + str(any(d.startswith("Edit(") and home.lstrip("/") in d for d in deny))
           + " record=" + str(os.path.isfile(os.path.join(home, "harden.json")))
           + " backups=" + str(backup_count(home)))
    return ok, expected, got


def _step2(env, tmp, home, claude, settings_path):
    before = read_bytes(settings_path)
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home)
    after = read_bytes(settings_path)
    expected = ("a second harden exits 0, prints ALREADY HARDENED, leaves settings.json byte for byte "
                "as it was and writes no new backup")
    ok = (proc.returncode == 0 and "ALREADY HARDENED" in proc.stdout
          and after == before and backup_count(home) == 1)
    got = ("code=" + str(proc.returncode) + " already_hardened=" + str("ALREADY HARDENED" in proc.stdout)
           + " bytes_identical=" + str(after == before) + " backups=" + str(backup_count(home)))
    return ok, expected, got


def _step3(env, tmp, home, claude):
    proc = run_frugalflow(env, tmp, "doctor", "--claude-dir", claude, "--home", home)
    expected = "doctor prints the line 'INFO isolation: isolated'"
    ok = "INFO isolation: isolated" in proc.stdout
    got = "code=" + str(proc.returncode) + " isolated_line=" + str("INFO isolation: isolated" in proc.stdout)
    return ok, expected, got


def _step4(env, tmp, home, claude, settings_path, proj):
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--project", proj)
    expected = ("harden --project PROJ exits 0; denyWrite holds PROJ/vault/log.md and PROJ/.claude/settings.json; "
                "permissions.deny holds an Edit rule for the vault log; stdout prints the PROTECT line for it")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    vault_log = os.path.join(proj, "vault", "log.md")
    proj_settings = os.path.join(proj, ".claude", "settings.json")
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    ok = (vault_log in deny_write and proj_settings in deny_write
          and any(d.startswith("Edit(") and vault_log.lstrip("/") in d for d in deny)
          and ("PROTECT " + vault_log) in proc.stdout)
    got = ("code=0 denyWrite_vault=" + str(vault_log in deny_write)
           + " denyWrite_proj_settings=" + str(proj_settings in deny_write)
           + " deny_Edit_vault=" + str(any(d.startswith("Edit(") and vault_log.lstrip("/") in d for d in deny))
           + " protect_line=" + str(("PROTECT " + vault_log) in proc.stdout))
    return ok, expected, got


def _step5(env, tmp, home, claude, settings_path):
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    expected = ("harden --remove exits 0; settings.json is the original JSON object again "
                "(model x, deny holds only Bash(rm:*), no sandbox key); home/harden.json is gone")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    ok = (doc == ORIG and not os.path.exists(os.path.join(home, "harden.json")))
    got += " settings=" + repr(doc) + " record_gone=" + str(not os.path.exists(os.path.join(home, "harden.json")))
    return ok, expected, got


def _step6(env, tmp, home, claude):
    proc = run_frugalflow(env, tmp, "doctor", "--claude-dir", claude, "--home", home)
    expected = "doctor prints the line 'INFO isolation: cooperative'"
    ok = "INFO isolation: cooperative" in proc.stdout
    got = "code=" + str(proc.returncode) + " cooperative_line=" + str("INFO isolation: cooperative" in proc.stdout)
    return ok, expected, got


def _step7(env, tmp, home, claude, settings_path):
    env2 = dict(env)
    env2["CLAUDECODE"] = "1"
    before = read_bytes(settings_path)
    proc = run_frugalflow(env2, tmp, "harden", "--claude-dir", claude, "--home", home)
    after = read_bytes(settings_path)
    expected = ("under CLAUDECODE=1 without a terminal harden exits non-zero and settings.json is byte for byte as it was")
    ok = proc.returncode != 0 and after == before
    got = ("code=" + str(proc.returncode) + " bytes_identical=" + str(after == before)
           + " out=" + repr(proc.stdout.splitlines()[:1]))
    return ok, expected, got


def _step8(env, tmp, home, claude, settings_path):
    broken = "{ not settings\n"
    backups_before = backup_count(home)
    with open(settings_path, "w", encoding="utf-8") as handle:
        handle.write(broken)
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home)
    after = read_bytes(settings_path)
    expected = ("with an unreadable settings.json harden exits 5, prints a REFUSED line ending "
                "'Nothing was written.', leaves the file byte for byte as it was, writes no backup and no record")
    ok = (proc.returncode == 5 and "REFUSED" in proc.stdout and "Nothing was written." in proc.stdout
          and after == broken.encode("utf-8") and backup_count(home) == backups_before
          and not os.path.exists(os.path.join(home, "harden.json")))
    got = ("code=" + str(proc.returncode) + " refused_line=" + str("REFUSED" in proc.stdout)
           + " nothing_written=" + str("Nothing was written." in proc.stdout)
           + " file_intact=" + str(after == broken.encode("utf-8"))
           + " backups=" + str(backup_count(home)) + "/" + str(backups_before)
           + " record=" + str(os.path.exists(os.path.join(home, "harden.json"))))
    return ok, expected, got


def _step9(env, tmp, home, claude, settings_path, proj):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as handle:
        json.dump({"code_extensions": [".py"],
                   "delegation_logs": ["delegations.jsonl", "../logs/delegations.jsonl"],
                   "audit_log": "audit.jsonl"}, handle)
    outside = os.path.normpath(os.path.join(home, "..", "logs", "delegations.jsonl"))
    inside = os.path.join(home, "delegations.jsonl")
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--project", proj)
    expected = ("harden protects the delegation log guard.json names outside the home "
                "(denyWrite and an Edit rule hold it, the log inside the home adds no extra entry); "
                "--remove gives back the original settings.json")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    holds = (outside in deny_write
             and any(d.startswith("Edit(") and outside.lstrip("/") in d for d in deny)
             and ("PROTECT " + outside) in proc.stdout
             and inside not in deny_write)
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = holds and proc2.returncode == 0 and doc2 == ORIG
    got = ("code=0 denyWrite_outside=" + str(outside in deny_write)
           + " deny_Edit_outside=" + str(any(d.startswith("Edit(") and outside.lstrip("/") in d for d in deny))
           + " protect_line=" + str(("PROTECT " + outside) in proc.stdout)
           + " in_home_log_not_added=" + str(inside not in deny_write)
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def _step10(env, tmp, home, claude, settings_path, proj):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--project", proj)
    expected = ("harden --project PROJ protects PROJ/.githooks, PROJ/.git/hooks, PROJ/.git/config, "
                "the whole PROJ/.claude folder, PROJ/CLAUDE.md and PROJ/.mcp.json, and the claude "
                "dir's hooks, skills, commands, agents and CLAUDE.md (denyWrite plus the Edit rule, "
                "/** for folders); --remove gives back the original settings.json")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    want = [(os.path.join(proj, ".githooks"), True),
            (os.path.join(proj, ".git", "hooks"), True),
            (os.path.join(proj, ".git", "config"), False),
            (os.path.join(proj, ".claude"), True),
            (os.path.join(proj, "CLAUDE.md"), False),
            (os.path.join(proj, ".mcp.json"), False),
            (os.path.join(claude, "hooks"), True),
            (os.path.join(claude, "skills"), True),
            (os.path.join(claude, "commands"), True),
            (os.path.join(claude, "agents"), True),
            (os.path.join(claude, "CLAUDE.md"), False)]
    missing = [p for p, is_dir in want if not covered(deny_write, deny, p, is_dir)]
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = (not missing) and proc2.returncode == 0 and doc2 == ORIG
    got = ("code=0 missing=" + repr(missing)
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def _step11(env, tmp, home, claude, settings_path, proj):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home,
                          "--project", proj, "--allow-instructions")
    expected = ("harden --allow-instructions exits 0 and prints 'NOTE: CLAUDE.md stays writable "
                "(--allow-instructions)'; PROJ/CLAUDE.md and the claude dir's CLAUDE.md are absent "
                "from denyWrite and from the Edit rules, while PROJ/.githooks, the PROJ/.claude "
                "folder and the claude dir's hooks stay protected; --remove is exact")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    md_free = (os.path.join(proj, "CLAUDE.md") not in deny_write
               and os.path.join(claude, "CLAUDE.md") not in deny_write
               and not any(d.startswith("Edit(//") and "CLAUDE.md" in d for d in deny))
    holds = (md_free
             and covered(deny_write, deny, os.path.join(proj, ".githooks"), True)
             and covered(deny_write, deny, os.path.join(proj, ".claude"), True)
             and covered(deny_write, deny, os.path.join(claude, "hooks"), True)
             and "NOTE: CLAUDE.md stays writable (--allow-instructions)" in proc.stdout)
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = holds and proc2.returncode == 0 and doc2 == ORIG
    got = ("code=0 claude_md_free=" + str(md_free)
           + " githooks=" + str(covered(deny_write, deny, os.path.join(proj, ".githooks"), True))
           + " note=" + str("NOTE: CLAUDE.md stays writable (--allow-instructions)" in proc.stdout)
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def _step12(env, tmp, home, claude, settings_path):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    if os.path.isfile(os.path.join(home, "harden.json")):
        os.remove(os.path.join(home, "harden.json"))
    shutil.rmtree(os.path.join(home, "harden-backups"), ignore_errors=True)
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home)
    expected = ("harden writes no copy next to settings.json; the dated copy sits in "
                "home/harden-backups/ and harden.json lists its path; --remove gives back "
                "the original settings.json")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    side_copies = glob.glob(settings_path + ".before-frugalflow-*")
    copies = sorted(glob.glob(os.path.join(home, "harden-backups", "settings.json.before-frugalflow-*")))
    with open(os.path.join(home, "harden.json"), "r", encoding="utf-8") as handle:
        rec = json.load(handle)
    listed = rec.get("backups")
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = (side_copies == [] and len(copies) == 1 and listed == copies
          and proc2.returncode == 0 and doc2 == ORIG)
    got = ("code=0 side_copies=" + str(len(side_copies)) + " backups=" + str(len(copies))
           + " listed=" + str(listed == copies)
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def _step13(env, tmp, home, claude, settings_path, proj):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    os.makedirs(os.path.join(proj, "sub"), exist_ok=True)
    with open(os.path.join(proj, "sub", "CLAUDE.md"), "w", encoding="utf-8") as handle:
        handle.write("planted instruction\n")
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--project", proj)
    expected = ("harden --project PROJ protects PROJ/CLAUDE.local.md and the existing "
                "PROJ/sub/CLAUDE.md (denyWrite plus the literal Edit rule), writes the "
                "pattern rules Edit(//PROJ/**/CLAUDE.md) and Edit(//PROJ/**/CLAUDE.local.md) "
                "and prints the Limit line; --remove gives back the original settings.json")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    want = [(os.path.join(proj, "CLAUDE.local.md"), False),
            (os.path.join(proj, "sub", "CLAUDE.md"), False)]
    missing = [p for p, is_dir in want if not covered(deny_write, deny, p, is_dir)]
    pl = proj.lstrip("/")
    patterns = ["Edit(//" + pl + "/**/CLAUDE.md)", "Edit(//" + pl + "/**/CLAUDE.local.md)"]
    missing_patterns = [r for r in patterns if r not in deny]
    limit = ("Limit: a CLAUDE.md created later in a new subfolder by a shell command "
             "is not covered (the sandbox matches paths, not patterns); the file "
             "tools are covered by pattern.") in proc.stdout
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = (not missing and not missing_patterns and limit
          and proc2.returncode == 0 and doc2 == ORIG)
    got = ("code=0 missing=" + repr(missing) + " missing_patterns=" + repr(missing_patterns)
           + " limit_line=" + str(limit)
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def _step14(env, tmp, home, claude, settings_path, proj):
    with open(settings_path, "w", encoding="utf-8") as handle:
        json.dump(ORIG, handle, indent=2)
    # PROJ/sub/CLAUDE.md exists since step 13: --allow-instructions must not protect it either.
    proc = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home,
                          "--project", proj, "--allow-instructions")
    expected = ("harden --allow-instructions protects no CLAUDE.md or CLAUDE.local.md path "
                "and writes no rule naming them (root files, the subfolder file created "
                "before harden, the pattern rules), while PROJ/.githooks stays protected; "
                "--remove is exact")
    got = "code=" + str(proc.returncode)
    if proc.returncode != 0:
        got += " out=" + repr(proc.stdout.splitlines()[:2])
        return False, expected, got
    doc = read_settings(settings_path)
    deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
    deny = doc.get("permissions", {}).get("deny", [])
    free = (not any("CLAUDE" in p for p in deny_write)
            and not any("CLAUDE" in d for d in deny))
    holds = (free
             and covered(deny_write, deny, os.path.join(proj, ".githooks"), True)
             and "NOTE: CLAUDE.md stays writable (--allow-instructions)" in proc.stdout)
    proc2 = run_frugalflow(env, tmp, "harden", "--claude-dir", claude, "--home", home, "--remove")
    doc2 = read_settings(settings_path)
    ok = holds and proc2.returncode == 0 and doc2 == ORIG
    got = ("code=0 claude_free=" + str(free)
           + " githooks=" + str(covered(deny_write, deny, os.path.join(proj, ".githooks"), True))
           + " remove_code=" + str(proc2.returncode) + " settings_back=" + str(doc2 == ORIG))
    return ok, expected, got


def main_run():
    tmp = tempfile.mkdtemp()
    try:
        env = make_env(tmp)
        home = os.path.join(tmp, "ff")
        claude = os.path.join(tmp, "claude")
        proj = os.path.join(tmp, "proj")
        settings_path = os.path.join(claude, "settings.json")
        os.makedirs(claude, exist_ok=True)
        os.makedirs(proj, exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as handle:
            json.dump(ORIG, handle, indent=2)

        fns = [
            lambda: _step1(env, tmp, home, claude, settings_path),
            lambda: _step2(env, tmp, home, claude, settings_path),
            lambda: _step3(env, tmp, home, claude),
            lambda: _step4(env, tmp, home, claude, settings_path, proj),
            lambda: _step5(env, tmp, home, claude, settings_path),
            lambda: _step6(env, tmp, home, claude),
            lambda: _step7(env, tmp, home, claude, settings_path),
            lambda: _step8(env, tmp, home, claude, settings_path),
            lambda: _step9(env, tmp, home, claude, settings_path, proj),
            lambda: _step10(env, tmp, home, claude, settings_path, proj),
            lambda: _step11(env, tmp, home, claude, settings_path, proj),
            lambda: _step12(env, tmp, home, claude, settings_path),
            lambda: _step13(env, tmp, home, claude, settings_path, proj),
            lambda: _step14(env, tmp, home, claude, settings_path, proj),
        ]
        results = []
        for num, fn in enumerate(fns, start=1):
            try:
                ok, expected, got = fn()
            except Exception as error:
                ok, expected, got = False, "the step runs", "exception: " + str(error)
            results.append((num, bool(ok), expected, got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    failed = None
    for num, ok, expected, got in results:
        if ok:
            print("PASS {} expected {} | got {}".format(num, expected, got))
        else:
            print("FAIL {} expected {} | got {}".format(num, expected, got))
            if failed is None:
                failed = (num, got)
    if failed is None:
        print("E2E HARDEN OK")
        return 0
    print("E2E HARDEN FAIL {} {}".format(failed[0], failed[1]))
    return 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        sys.exit(main_run())
    elif sys.argv[1:] == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
