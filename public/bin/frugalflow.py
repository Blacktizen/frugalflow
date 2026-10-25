#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""frugalflow.py - the product entry point."""

import os
import sys
import re
import json
import shlex
import tempfile
import shutil
import subprocess

BIN = os.path.dirname(os.path.abspath(__file__))
if BIN not in sys.path:
    sys.path.insert(0, BIN)
NAME_RULE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
COMMANDS = ("new-project", "nouveau-projet")   # lang-ok: French alias

USAGE = (
    "usage: frugalflow.py COMMAND [ARGS] | --notice | --autotest\n"
    "  new-project NAME [--root DIR]   (creates DIR/NAME; DIR defaults to the current folder)\n"
    "  init [--mode observe|active|silent] [--remove] [options]\n"
    "  scan [PATH] [--staged] [--rules FILE] [--quiet]   (finds secrets and private data in a folder or repo; exit 12 on a leak; needs no model)\n"
    "  setup [--yes] [--home DIR] [--claude-dir DIR] [--engine ENGINE] [--endpoint URL]   (guided: detects your engines, backs up, writes, runs doctor)\n"
    "  uninstall [--home DIR] [--claude-dir DIR]   (restores the backups made by setup)\n"
    "  setup --layers [--home DIR] [--answer ROLE=MODEL_ID]...[--ollama-url URL] [--lmstudio-url URL]   (walks the layers, proposes the detected models first)\n"
    "  notes add-pitfall|show|check|merge|measure [--home DIR] [...]   (pitfalls and measures per model, each with its proof)\n"
    "  doctor [options]\n"
    "  report TRACE [--log DELEGATIONS] [--models MODELS] [--summary]\n"
    "  lint BRIEF [--trust private|untrusted_third_party] [--waiver REASON] | --explain RULE_ID | --check-examples [--examples FILE]\n"
    "  config [set KEY VALUE]\n"
    "  on | off | mode MODE\n"
    "  display statusline|turn-line|summary on|off\n"
    "  options: --home DIR --claude-dir DIR --ollama-url URL --lmstudio-url URL (any OpenAI-compatible server, with or without /v1)"
)

NOTICE = (
    "NAME      frugalflow.py - the product entry point: new-project mounts a project, init installs FrugalFlow, doctor checks it, config, on, off, mode and display steer the switch and the screen.\n"
    "READS     COMMAND and its arguments; the subcommand it dispatches to; new-project reads NAME and --root (default: the current folder).\n"
    "WRITES    what the subcommand writes: new-project mounts the vault and hooks, init writes the CLAUDE.md block, the settings hook and the settings files. The exit code is the subcommand's; 2 on usage.\n"
    "EXAMPLE   python3 frugalflow.py new-project demo --root ~/projects\n"
    "PITFALLS  2026-09-22 vaults made by hand forgot the todo or the index, and hooks were wired later, or never.\n"
    "          The log and its guard are wired at creation, in the project settings, never in the user settings.\n"
    "          2026-10-05 a newcomer read --root as the project folder and got DIR/NAME/NAME: the usage now says DIR/NAME.\n"
    "          2026-10-05 a project tool refused for weeks without a trace: new-project now lays the refusal log loop, the bench and the commit gate.\n"
)

OWN_SETTINGS = "{\"permissions\": {}}\n"


def hook(command):
    """Return a single hook entry dict."""
    return {"type": "command", "command": command}


def hooks_config(bin_dir, python, project=None):
    """Build the Claude Code hooks configuration dict; with project, SessionStart gains the refusal loop todo."""
    log = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "session_log.py"))
    guard = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "r1_guard.py"))
    summary_show = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "session_summary.py")) + " --show"
    summary_record = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "session_summary.py")) + " --record-hook"
    receipt = shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "usage_report.py")) + " --hook"
    cfg = {
        "hooks": {
            "SessionStart": [{"hooks": [hook(log), hook(summary_show)]}],
            "UserPromptSubmit": [{"hooks": [hook(log)]}],
            "PreToolUse": [{"matcher": "*", "hooks": [hook(log)]}],
            "PostToolUse": [{"matcher": "*", "hooks": [hook(log)]}],
            "Stop": [{"hooks": [hook(log), hook(guard), hook(receipt)]}],
            "SessionEnd": [{"hooks": [hook(log), hook(summary_record)]}],
        }
    }
    if project is not None:
        cfg["hooks"]["SessionStart"][0]["hooks"].append(hook(
            shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "refusal_loop.py"))
            + " todo --project " + shlex.quote(project)
        ))
    return cfg


def commit_gate(bin_dir, python, project):
    """Write <project>/.githooks/pre-commit (mode 0o755) running the refusal loop check."""
    gate_dir = os.path.join(project, ".githooks")
    os.makedirs(gate_dir, exist_ok=True)
    gate_path = os.path.join(gate_dir, "pre-commit")
    content = (
        "#!/bin/sh\n"
        "# Installed by frugalflow new-project: the refusal loop blocks a commit that regresses a tool.\n"
        "exec " + shlex.quote(python) + " " + shlex.quote(os.path.join(bin_dir, "refusal_loop.py"))
        + ' check --project "$(git rev-parse --show-toplevel)"\n'
    )
    with open(gate_path, "w", encoding="utf-8") as handle:
        handle.write(content)
    os.chmod(gate_path, 0o755)
    return gate_path


def git_gate(project):
    """Point the repo's hooks at .githooks. Return True when git is available."""
    if not shutil.which("git"):
        return False
    if not os.path.isdir(os.path.join(project, ".git")):
        subprocess.run(["git", "init", "-q", project], capture_output=True, text=True)
    subprocess.run(
        ["git", "-C", project, "config", "core.hooksPath", ".githooks"],
        capture_output=True, text=True
    )
    return True


def new_project(name, root):
    """Mount a project: create vault via vault_new.py, lay the tools dir, the bench and the commit gate, then write Claude Code hooks.

    Returns (exit_code, list_of_lines_to_print).
    """
    project = os.path.abspath(os.path.join(root, name))
    result = subprocess.run(
        [sys.executable, os.path.join(BIN, "vault_new.py"), "--root", project, "--name", name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        lines = [line for line in result.stdout.splitlines() if line]
        lines += [line for line in result.stderr.splitlines() if line]
        return (result.returncode, lines)
    bin_dir = os.path.join(project, "bin")
    os.makedirs(bin_dir, exist_ok=True)
    cases_path = os.path.join(project, "bench", "cases.json")
    if not os.path.isfile(cases_path):
        os.makedirs(os.path.dirname(cases_path), exist_ok=True)
        with open(cases_path, "w", encoding="utf-8") as handle:
            handle.write("[]\n")
    gate_path = commit_gate(BIN, sys.executable, project)
    git_found = git_gate(project)
    settings = os.path.join(project, ".claude", "settings.json")
    if os.path.isfile(settings):
        return (4, [
            "VAULT CREATED, HOOKS NOT WRITTEN: " + settings + " already exists",
            "Add these hooks by hand:",
            json.dumps(hooks_config(BIN, sys.executable, project), indent=2)
        ])
    os.makedirs(os.path.dirname(settings), exist_ok=True)
    with open(settings, "w", encoding="utf-8") as handle:
        handle.write(json.dumps(hooks_config(BIN, sys.executable, project), indent=2) + "\n")
    lines = [
        "PROJECT READY " + project,
        "  vault  " + os.path.join(project, "vault"),
        "  hooks  " + settings,
        "  tools  " + bin_dir,
        "  bench  " + cases_path,
        "  gate   " + gate_path
    ]
    if not git_found:
        lines.append("COMMIT GATE NOT ACTIVE: git not found")
    return (0, lines)


def run_autotest():
    """Execute the five proofs as subprocesses. Return 0 if all pass, 1 otherwise."""
    base = tempfile.mkdtemp()
    results = []
    try:
        # Test 1: new-project creates vault and hooks
        proc = subprocess.run(
            [sys.executable, __file__, "new-project", "demo", "--root", base],
            capture_output=True, text=True
        )
        settings_path = os.path.join(base, "demo", ".claude", "settings.json")
        vault_log = os.path.join(base, "demo", "vault", "log.md")
        ok = (
            proc.returncode == 0
            and proc.stdout != ""
            and proc.stdout.startswith("PROJECT READY ")
            and os.path.isfile(vault_log)
        )
        if ok:
            with open(settings_path, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            ok = (
                "r1_guard.py" in cfg["hooks"]["Stop"][0]["hooks"][1]["command"]
                and cfg["hooks"]["Stop"][0]["hooks"][2]["command"].endswith("usage_report.py --hook")
                and "session_log.py" in cfg["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
                and cfg["hooks"]["PreToolUse"][0]["matcher"] == "*"
                and cfg["hooks"]["SessionStart"][0]["hooks"][1]["command"].endswith("session_summary.py --show")
                and cfg["hooks"]["SessionEnd"][0]["hooks"][1]["command"].endswith("session_summary.py --record-hook")
            )
        detail = "rc=%d first=%r" % (proc.returncode, proc.stdout.splitlines()[0] if proc.stdout else "")
        results.append((1, ok, "exit 0 + PROJECT READY + vault/log.md + settings hooks verified", detail))

        # Test 2: vault_check.py confirms vault integrity
        proc = subprocess.run(
            [sys.executable, os.path.join(BIN, "vault_check.py"), "--vault", os.path.join(base, "demo", "vault")],
            capture_output=True, text=True
        )
        ok = proc.returncode == 0 and proc.stdout != ""
        results.append((2, ok, "vault_check.py exit 0 with non-empty output", "rc=%d" % proc.returncode))

        # Test 3: second new-project on same name is refused (exit 3)
        proc = subprocess.run(
            [sys.executable, __file__, "new-project", "demo", "--root", base],
            capture_output=True, text=True
        )
        ok = proc.returncode == 3 and proc.stdout != ""
        results.append((3, ok, "repeat new-project demo exit 3 with non-empty output", "rc=%d" % proc.returncode))

        # Test 4: existing settings.json is preserved (exit 4)
        own_claude = os.path.join(base, "own", ".claude")
        os.makedirs(own_claude, exist_ok=True)
        own_settings = os.path.join(own_claude, "settings.json")
        with open(own_settings, "w", encoding="utf-8") as fh:
            fh.write(OWN_SETTINGS)
        proc = subprocess.run(
            [sys.executable, __file__, COMMANDS[1], "own", "--root", base],
            capture_output=True, text=True
        )
        own_vault_log = os.path.join(base, "own", "vault", "log.md")
        with open(own_settings, "r", encoding="utf-8") as fh:
            file_content = fh.read()
        ok = (
            proc.returncode == 4
            and proc.stdout != ""
            and proc.stdout.startswith("VAULT CREATED, HOOKS NOT WRITTEN: ")
            and file_content == OWN_SETTINGS
            and os.path.isfile(own_vault_log)
        )
        detail = "rc=%d first=%r file_unchanged=%s" % (
            proc.returncode,
            proc.stdout.splitlines()[0] if proc.stdout else "",
            file_content == OWN_SETTINGS
        )
        results.append((4, ok, "alias own exit 4 + VAULT CREATED prefix + settings unchanged + vault/log.md", detail))

        # Test 5: --notice, invalid NAME, unknown COMMAND
        proc_notice = subprocess.run(
            [sys.executable, __file__, "--notice"],
            capture_output=True, text=True
        )
        proc_escape = subprocess.run(
            [sys.executable, __file__, "new-project", "../escape", "--root", base],
            capture_output=True, text=True
        )
        proc_bogus = subprocess.run(
            [sys.executable, __file__, "bogus", "x"],
            capture_output=True, text=True
        )
        ok = (
            proc_notice.returncode == 0
            and proc_notice.stdout != ""
            and proc_notice.stdout.startswith("NAME      frugalflow.py")
            and proc_escape.returncode == 2
            and proc_bogus.returncode == 2
            and "usage: frugalflow.py" in proc_bogus.stdout
        )
        detail = "notice_rc=%d escape_rc=%d bogus_rc=%d" % (
            proc_notice.returncode, proc_escape.returncode, proc_bogus.returncode
        )
        results.append((5, ok, "--notice exit 0 + ../escape exit 2 + bogus exit 2 + usage present", detail))

        # Test 6: dispatch init/doctor/config/on/off/mode
        home6 = os.path.join(base, "ff6", "home")
        claude6 = os.path.join(base, "ff6", "claude")
        env6 = dict(os.environ)
        env6["HOME"] = base
        r_init = subprocess.run(
            [sys.executable, __file__, "init", "--home", home6, "--claude-dir", claude6,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_doctor = subprocess.run(
            [sys.executable, __file__, "doctor", "--home", home6, "--claude-dir", claude6,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_config = subprocess.run(
            [sys.executable, __file__, "config", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_on = subprocess.run(
            [sys.executable, __file__, "on", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_off = subprocess.run(
            [sys.executable, __file__, "off", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_mode = subprocess.run(
            [sys.executable, __file__, "mode", "silent", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_display = subprocess.run(
            [sys.executable, __file__, "display", "statusline", "off", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_display_bad = subprocess.run(
            [sys.executable, __file__, "display", "logo", "off", "--home", home6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        r_bad = subprocess.run(
            [sys.executable, __file__, "init", "--mode", "bogus", "--home", home6, "--claude-dir", claude6],
            capture_output=True, text=True, env=env6, cwd=base
        )
        ok = (r_init.returncode == 0 and r_doctor.returncode == 0 and r_config.returncode == 0
              and r_on.returncode == 0 and r_off.returncode == 0 and r_mode.returncode == 0
              and r_display.returncode == 0 and "FrugalFlow display statusline off" in r_display.stdout
              and r_display_bad.returncode == 2
              and r_bad.returncode == 2)
        detail = "init=%d doctor=%d config=%d on=%d off=%d mode=%d display=%d display_bad=%d bad=%d" % (
            r_init.returncode, r_doctor.returncode, r_config.returncode,
            r_on.returncode, r_off.returncode, r_mode.returncode,
            r_display.returncode, r_display_bad.returncode, r_bad.returncode)
        results.append((6, ok, "dispatch init/doctor/config/on/off/mode/display exit 0 and bad name and bad mode exit 2", detail))

        # Test 7: new-project lays the refusal loop hook, the tools dir, the bench and the commit gate
        root7 = os.path.join(base, "loop7")
        os.makedirs(root7, exist_ok=True)
        proc = subprocess.run(
            [sys.executable, __file__, "new-project", "loop", "--root", root7],
            capture_output=True, text=True
        )
        project7 = os.path.join(root7, "loop")
        bin7 = os.path.join(project7, "bin")
        cases7 = os.path.join(project7, "bench", "cases.json")
        gate7 = os.path.join(project7, ".githooks", "pre-commit")
        cases_content = None
        if os.path.isfile(cases7):
            with open(cases7, "r", encoding="utf-8") as fh:
                cases_content = fh.read()
        gate_content = None
        if os.path.isfile(gate7):
            with open(gate7, "r", encoding="utf-8") as fh:
                gate_content = fh.read()
        ok = (
            proc.returncode == 0
            and os.path.isdir(bin7)
            and cases_content == "[]\n"
            and "  tools  " + bin7 in proc.stdout
            and "  bench  " + cases7 in proc.stdout
            and "  gate   " + gate7 in proc.stdout
            and gate_content is not None
            and os.access(gate7, os.X_OK)
            and "refusal_loop.py" in gate_content
            and "check --project" in gate_content
        )
        if ok:
            with open(os.path.join(project7, ".claude", "settings.json"), "r", encoding="utf-8") as fh:
                cfg7 = json.load(fh)
            start_cmds = [h["command"] for group in cfg7["hooks"]["SessionStart"] for h in group["hooks"]]
            ok = any(
                "refusal_loop.py" in cmd and "todo --project" in cmd and project7 in cmd
                for cmd in start_cmds
            )
        if ok and shutil.which("git"):
            ok = os.path.isdir(os.path.join(project7, ".git"))
            r7 = subprocess.run(
                ["git", "-C", project7, "config", "core.hooksPath"],
                capture_output=True, text=True
            )
            ok = ok and r7.returncode == 0 and r7.stdout.strip() == ".githooks"
        elif ok:
            ok = "COMMIT GATE NOT ACTIVE: git not found" in proc.stdout
        detail = "rc=%d bin=%s cases=%r gate_exec=%s hooks_path=%s" % (
            proc.returncode, os.path.isdir(bin7), cases_content,
            os.path.isfile(gate7) and os.access(gate7, os.X_OK),
            subprocess.run(["git", "-C", project7, "config", "core.hooksPath"],
                           capture_output=True, text=True).stdout.strip() if shutil.which("git") else "no-git"
        )
        results.append((7, ok, "new-project exit 0 + bin/ + cases.json '[]' + SessionStart refusal todo + gate lines + executable gate + core.hooksPath .githooks", detail))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    all_pass = True
    for num, passed, expected, obtained in results:
        if passed:
            print("PASS test %d: %s" % (num, expected))
        else:
            print("FAIL test %d: expected %s, got %s" % (num, expected, obtained))
            all_pass = False
    return 0 if all_pass else 1


def _load_subcommand(module_name):
    import importlib
    return importlib.import_module(module_name)


def run_notes(args):
    """Dispatch notes to model_notes.py: strip --home, fill the default notes file, return the exit code."""
    subcommands = ("add-pitfall", "show", "check", "merge", "measure")
    if not args or args[0] not in subcommands:
        sys.stdout.write(USAGE + "\n")
        return 2
    subcommand = args[0]
    rest = args[1:]
    home = None
    kept = []
    i = 0
    while i < len(rest):
        if rest[i] == "--home":
            if i + 1 >= len(rest):
                sys.stdout.write(USAGE + "\n")
                return 2
            home = rest[i + 1]
            i += 2
        else:
            kept.append(rest[i])
            i += 1
    if home is None:
        home = os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")
    default_file = os.path.join(home, "model_notes.json")
    if subcommand == "check":
        if not kept:
            kept.append(default_file)
    elif "--file" not in kept:
        kept = ["--file", default_file] + kept
    if subcommand == "measure" and "--log" not in kept:
        kept = kept + ["--log", os.path.join(home, "delegations.jsonl")]
    module = _load_subcommand("model_notes")
    return module.main([subcommand] + kept)


def main():
    """Parse CLI arguments and dispatch to the appropriate action."""
    args = sys.argv[1:]

    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)

    if args == ["--autotest"]:
        sys.exit(run_autotest())

    if not args:
        sys.stdout.write(USAGE + "\n")
        sys.exit(2)

    if args[0] in ("--help", "-h", "help"):
        sys.stdout.write(USAGE + "\n")
        sys.exit(0)

    command = args[0]

    if command in COMMANDS:
        if len(args) < 2:
            sys.stdout.write(USAGE + "\n")
            sys.exit(2)
        name = args[1]
        if not NAME_RULE.fullmatch(name):
            sys.stdout.write(USAGE + "\n")
            sys.exit(2)
        if len(args) == 2:
            root = os.getcwd()
        elif len(args) == 4 and args[2] == "--root":
            root = args[3]
        else:
            sys.stdout.write(USAGE + "\n")
            sys.exit(2)
        code, lines = new_project(name, root)
        for line in lines:
            print(line)
        sys.exit(code)

    if command in ("init", "doctor", "report", "lint", "setup", "scan", "uninstall"):
        rest = args[1:]
        if command == "setup" and "--layers" not in rest and "--answer" not in rest:
            command = "onboard"
        rest = [a for a in rest if a != "--layers"]
        module = _load_subcommand(command + "_cmd")
        sys.exit(module.main(rest))

    if command in ("config", "on", "off", "mode", "display"):
        module = _load_subcommand("config_cmd")
        sys.exit(module.main([command] + args[1:]))

    if command == "notes":
        sys.exit(run_notes(args[1:]))

    sys.stdout.write(USAGE + "\n")
    sys.exit(2)


def entry():
    """Console-script entry point installed by pip: same run as the script."""
    import exit_log
    exit_log.run(main, "frugalflow", sys.argv[1:])


if __name__ == "__main__":
    entry()
