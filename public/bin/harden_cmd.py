#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""harden_cmd.py - the frugalflow harden subcommand: turn on the isolated mode,
the native Claude Code sandbox, with the FrugalFlow settings and journals kept
read-only to the assistant. --remove takes back exactly what was added."""

import os
import sys
import json
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import claudecode_check

USAGE = (
    "usage: harden_cmd.py [--claude-dir DIR] [--home DIR] [--project DIR]... "
    "[--allow-instructions] [--remove] | --notice | --autotest"
)

NOTICE = (
    "NAME      harden_cmd.py - the frugalflow harden subcommand: turn on the isolated mode on the native Claude Code sandbox; the FrugalFlow settings and journals become read-only to the assistant.\n"
    "READS     settings.json in --claude-dir, else ~/.claude; the record harden.json in --home, else FRUGALFLOW_HOME, else ~/.frugalflow.\n"
    "WRITES    settings.json (the three sandbox booleans, denyWrite entries, Edit deny rules) and harden.json (what was added, so --remove takes it back, plus the paths of the settings copies); a dated copy of settings.json in <home>/harden-backups/ before the first write. --remove writes settings.json back to what it was and deletes harden.json. Exit 0 done, already hardened or nothing to remove, 2 usage, 3 refused under Claude Code without a terminal, 4 native Windows, 5 settings.json cannot be read.\n"
    "EXAMPLE   python3 harden_cmd.py --claude-dir ~/.claude --home ~/.frugalflow --project ./my-project\n"
    "PITFALLS  2026-11-13 the sandbox covers Bash only: Read, Edit and Write follow the permission rules, hence the Edit(//...) deny rules written here.\n"
    "          2026-11-13 hooks and local MCP servers run outside the sandbox with the user's rights: harden protects the files, not the hooks.\n"
    "          2026-11-13 nothing is removed that harden.json did not record: settings that existed before stay untouched, and a rerun that adds nothing writes zero bytes.\n"
    "          2026-11-13 an adversarial review planted a git pre-commit hook that the user would run later outside the sandbox, and skills through the Write tool; harden now locks .githooks, .git/hooks, .git/config, .claude and CLAUDE.md of each project.\n"
    "          2026-11-13 Claude Code also loads CLAUDE.local.md at the project root and the CLAUDE.md and CLAUDE.local.md of its subfolders: harden protects them too — every instruction file that already exists under the project gets its own rule, and the Edit(//.../**/CLAUDE.md) patterns cover the file tools for files created later; a shell command creating a CLAUDE.md in a brand-new subfolder is not covered by the sandbox, which matches paths, not patterns.\n"
)

# The three sandbox booleans harden sets, and the values it sets them to.
SANDBOX_FLAGS = ("enabled", "allowUnsandboxedCommands", "failIfUnavailable")
SANDBOX_VALUES = {"enabled": True, "allowUnsandboxedCommands": False, "failIfUnavailable": True}


class SettingsRefused(Exception):
    """settings.json exists but cannot be read as settings."""


def _abs(path):
    return os.path.abspath(os.path.expanduser(path))


def _delegation_logs(home):
    """The delegation logs named by home/guard.json, resolved inside the home.
    A log already under the home is covered by the home rule and adds nothing.
    An absent or unreadable guard.json adds nothing."""
    try:
        with open(os.path.join(home, "guard.json"), "r", encoding="utf-8") as handle:
            settings = json.load(handle)
    except (OSError, ValueError):
        return []
    if not isinstance(settings, dict):
        return []
    logs = settings.get("delegation_logs")
    if not isinstance(logs, list):
        return []
    out = []
    for entry in logs:
        if not isinstance(entry, str) or not entry:
            continue
        path = os.path.normpath(os.path.join(home, os.path.expanduser(entry)))
        if path == home or path.startswith(home + os.sep):
            continue
        out.append(path)
    return out


def _instruction_files(project):
    """CLAUDE.md and CLAUDE.local.md files that already exist under the project.
    Claude Code loads those nested instruction files as instructions too, so each
    one gets its own literal protection. The walk skips .git, node_modules and
    hidden folders, except .claude."""
    found = []
    for root, dirs, files in os.walk(project):
        dirs[:] = sorted(d for d in dirs
                         if d not in (".git", "node_modules")
                         and (not d.startswith(".") or d == ".claude"))
        for name in files:
            if name in ("CLAUDE.md", "CLAUDE.local.md"):
                found.append(os.path.join(root, name))
    return found


def _instruction_pattern_rules(projects):
    """The two permission rules per project that cover the file tools for any
    instruction file anywhere under it, including one created after harden:
    permission rules take patterns, the sandbox's denyWrite does not."""
    rules = []
    for project in projects:
        rules.append("Edit(//" + project.lstrip("/") + "/**/CLAUDE.md)")
        rules.append("Edit(//" + project.lstrip("/") + "/**/CLAUDE.local.md)")
    return rules


def _protected_paths(home, claude_dir, projects, allow_instructions):
    """Every path the isolated mode keeps read-only to the assistant, as
    (path, is_dir), in order, no duplicate path. A folder gets the Edit(//.../**)
    rule, a file the plain Edit(//...) rule. --allow-instructions leaves the
    CLAUDE.md and CLAUDE.local.md files out: the assistant may keep its own notes
    there."""
    paths = [(home, True),
             (os.path.join(claude_dir, "settings.json"), False),
             (os.path.join(claude_dir, "settings.local.json"), False),
             (os.path.join(claude_dir, "hooks"), True),
             (os.path.join(claude_dir, "skills"), True),
             (os.path.join(claude_dir, "commands"), True),
             (os.path.join(claude_dir, "agents"), True)]
    if not allow_instructions:
        paths.append((os.path.join(claude_dir, "CLAUDE.md"), False))
    paths += [(path, False) for path in _delegation_logs(home)]
    for project in projects:
        paths += [(os.path.join(project, "vault", "log.md"), False),
                  (os.path.join(project, ".claude"), True),
                  (os.path.join(project, ".claude", "settings.json"), False),
                  (os.path.join(project, ".claude", "settings.local.json"), False),
                  (os.path.join(project, ".githooks"), True),
                  (os.path.join(project, ".git", "hooks"), True),
                  (os.path.join(project, ".git", "config"), False),
                  (os.path.join(project, ".mcp.json"), False)]
        if not allow_instructions:
            paths.append((os.path.join(project, "CLAUDE.md"), False))
            paths.append((os.path.join(project, "CLAUDE.local.md"), False))
            paths += [(path, False) for path in _instruction_files(project)]
    out = []
    seen = set()
    for path, is_dir in paths:
        if path not in seen:
            seen.add(path)
            out.append((path, is_dir))
    return out


def _edit_rule(path, is_dir):
    """The Claude Code permission rule that refuses the file tools on a path:
    Edit(//abs/path) — two slashes, then the absolute path without its leading
    slash; /** covers a whole folder."""
    return "Edit(//" + path.lstrip("/") + ("/**)" if is_dir else ")")


def _backup(home, settings_path, raw):
    """Copy settings.json to <home>/harden-backups/ before writing it, and return
    the path written. The copy used to sit next to settings.json — an adversarial
    review showed it was itself a writable target; the home is protected, so the
    copies are too."""
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    name = os.path.basename(settings_path) + ".before-frugalflow-" + stamp
    folder = os.path.join(home, "harden-backups")
    os.makedirs(folder, exist_ok=True)
    base = os.path.join(folder, name)
    final = base
    n = 2
    while os.path.exists(final):
        final = base + "-" + str(n)
        n += 1
    with open(final, "w", encoding="utf-8", newline="") as f:
        f.write(raw)
    return final


def _load_settings(path):
    """Return (raw, doc): (None, None) when the file does not exist. Raise
    SettingsRefused when it exists but is not a readable JSON object."""
    if not os.path.exists(path):
        return None, None
    try:
        with open(path, "r", encoding="utf-8", newline="") as f:
            raw = f.read()
    except OSError as error:
        raise SettingsRefused(str(error))
    try:
        doc = json.loads(raw)
    except ValueError as error:
        raise SettingsRefused(str(error))
    if not isinstance(doc, dict):
        raise SettingsRefused("not a JSON object")
    return raw, doc


def _write_json(path, doc):
    with open(path, "w", encoding="utf-8", newline="") as f:
        f.write(json.dumps(doc, indent=2, ensure_ascii=False) + "\n")


def _plan(doc, protected, extra_rules=()):
    """Return (new_doc, added): new_doc is a copy of doc (or {} when absent) with
    the harden keys merged in; added records exactly what was added, so --remove
    can take it back. No other key is touched, moved or removed. protected is a
    list of (path, is_dir); extra_rules are permission rules that are not the
    rule of a protected path (the instruction-file patterns)."""
    new_doc = json.loads(json.dumps(doc if doc is not None else {}))
    added = {
        "sandbox_created": False,
        "filesystem_created": False,
        "denyWrite_created": False,
        "permissions_created": False,
        "deny_created": False,
        "flags_added": [],
        "flags_previous": {},
        "denyWrite_added": [],
        "permissions_deny_added": [],
    }

    sandbox = new_doc.get("sandbox")
    if not isinstance(sandbox, dict):
        sandbox = {}
        new_doc["sandbox"] = sandbox
        added["sandbox_created"] = True
    for flag in SANDBOX_FLAGS:
        want = SANDBOX_VALUES[flag]
        if flag not in sandbox:
            sandbox[flag] = want
            added["flags_added"].append(flag)
        elif sandbox[flag] != want:
            added["flags_previous"][flag] = sandbox[flag]
            sandbox[flag] = want

    filesystem = sandbox.get("filesystem")
    if not isinstance(filesystem, dict):
        filesystem = {}
        sandbox["filesystem"] = filesystem
        added["filesystem_created"] = True
    deny_write = filesystem.get("denyWrite")
    if not isinstance(deny_write, list):
        deny_write = []
        filesystem["denyWrite"] = deny_write
        added["denyWrite_created"] = True
    for path, _is_dir in protected:
        if path not in deny_write:
            deny_write.append(path)
            added["denyWrite_added"].append(path)

    permissions = new_doc.get("permissions")
    if not isinstance(permissions, dict):
        permissions = {}
        new_doc["permissions"] = permissions
        added["permissions_created"] = True
    deny = permissions.get("deny")
    if not isinstance(deny, list):
        deny = []
        permissions["deny"] = deny
        added["deny_created"] = True
    for path, is_dir in protected:
        rule = _edit_rule(path, is_dir)
        if rule not in deny:
            deny.append(rule)
            added["permissions_deny_added"].append(rule)
    for rule in extra_rules:
        if rule not in deny:
            deny.append(rule)
            added["permissions_deny_added"].append(rule)

    return new_doc, added


def _union(old, new):
    """old + new, keeping the order and no duplicate."""
    out = list(old) if isinstance(old, list) else []
    for item in new:
        if item not in out:
            out.append(item)
    return out


def _merge_record(old, added, settings_path, created_settings, backup_paths):
    """Fold one harden run into the harden.json record, so --remove undoes every
    run since the last --remove. The earliest previous value of a flag wins.
    The record also keeps the list of settings copies written to harden-backups."""
    rec = dict(old) if isinstance(old, dict) else {}
    rec["schema_version"] = 1
    rec["settings_path"] = settings_path
    rec["created_settings"] = bool(rec.get("created_settings")) or created_settings
    for key in ("sandbox_created", "filesystem_created", "denyWrite_created",
                "permissions_created", "deny_created"):
        rec[key] = bool(rec.get(key)) or added[key]
    rec["flags_added"] = _union(rec.get("flags_added"), added["flags_added"])
    previous = dict(rec.get("flags_previous") or {})
    for flag, value in added["flags_previous"].items():
        if flag not in previous:
            previous[flag] = value
    rec["flags_previous"] = previous
    rec["denyWrite_added"] = _union(rec.get("denyWrite_added"), added["denyWrite_added"])
    rec["permissions_deny_added"] = _union(rec.get("permissions_deny_added"), added["permissions_deny_added"])
    rec["backups"] = _union(rec.get("backups"), backup_paths)
    return rec


def _load_record(path):
    """Return (doc, None) or (None, refusal_line) when the record exists but cannot be read."""
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        return None, "REFUSED: " + path + " cannot be read as a harden record. Nothing was written."
    if not isinstance(doc, dict):
        return None, "REFUSED: " + path + " cannot be read as a harden record. Nothing was written."
    return doc, None


def _harden(home, claude_dir, projects, allow_instructions):
    settings_path = os.path.join(claude_dir, "settings.json")
    record_path = os.path.join(home, "harden.json")

    try:
        raw, doc = _load_settings(settings_path)
    except SettingsRefused:
        print("REFUSED: " + settings_path + " cannot be read as settings. Nothing was written.")
        return 5

    protected = _protected_paths(home, claude_dir, projects, allow_instructions)
    extra_rules = [] if allow_instructions else _instruction_pattern_rules(projects)
    new_doc, added = _plan(doc, protected, extra_rules)
    if allow_instructions:
        print("NOTE: CLAUDE.md stays writable (--allow-instructions)")
    if doc is not None and new_doc == doc:
        # Everything is already in place: not one byte is written.
        print("ALREADY HARDENED")
        return 0

    old_record = None
    if os.path.isfile(record_path):
        old_record, refusal = _load_record(record_path)
        if refusal is not None:
            print(refusal)
            return 5

    backup_paths = []
    if raw is not None:
        backup_paths.append(_backup(home, settings_path, raw))
    os.makedirs(claude_dir, exist_ok=True)
    _write_json(settings_path, new_doc)
    os.makedirs(home, exist_ok=True)
    _write_json(record_path, _merge_record(old_record, added, settings_path, raw is None, backup_paths))

    for path, _is_dir in protected:
        print("PROTECT " + path)
    print("Isolated mode: Bash runs in the Claude Code sandbox, FrugalFlow settings "
          "and journals are read-only to the assistant. Restart Claude Code to apply.")
    print("Git hooks, project instructions and Claude Code extensions of each "
          "--project are read-only to the assistant too.")
    if not allow_instructions:
        print("Limit: a CLAUDE.md created later in a new subfolder by a shell command "
              "is not covered (the sandbox matches paths, not patterns); the file "
              "tools are covered by pattern.")
    return 0


def _apply_removal(doc, rec):
    """Take back exactly what the record says was added: recorded list entries go,
    recorded flags return to their previous value or disappear, a dictionary or a
    list harden created and left empty is removed. Anything else stays."""
    sandbox = doc.get("sandbox")
    if isinstance(sandbox, dict):
        for flag in rec.get("flags_added") or []:
            sandbox.pop(flag, None)
        for flag, value in (rec.get("flags_previous") or {}).items():
            sandbox[flag] = value
        filesystem = sandbox.get("filesystem")
        if isinstance(filesystem, dict):
            deny_write = filesystem.get("denyWrite")
            if isinstance(deny_write, list):
                removed = rec.get("denyWrite_added") or []
                filesystem["denyWrite"] = [d for d in deny_write if d not in removed]
                if not filesystem["denyWrite"] and rec.get("denyWrite_created"):
                    filesystem.pop("denyWrite")
            if not filesystem and rec.get("filesystem_created"):
                sandbox.pop("filesystem")
        if not sandbox and rec.get("sandbox_created"):
            doc.pop("sandbox")

    permissions = doc.get("permissions")
    if isinstance(permissions, dict):
        deny = permissions.get("deny")
        if isinstance(deny, list):
            removed = rec.get("permissions_deny_added") or []
            permissions["deny"] = [d for d in deny if d not in removed]
            if not permissions["deny"] and rec.get("deny_created"):
                permissions.pop("deny")
        if not permissions and rec.get("permissions_created"):
            doc.pop("permissions")
    return doc


def _remove(home, claude_dir):
    settings_path = os.path.join(claude_dir, "settings.json")
    record_path = os.path.join(home, "harden.json")

    if not os.path.isfile(record_path):
        print("NOTHING TO REMOVE")
        return 0

    rec, refusal = _load_record(record_path)
    if refusal is not None:
        print(refusal)
        return 5

    try:
        raw, doc = _load_settings(settings_path)
    except SettingsRefused:
        print("REFUSED: " + settings_path + " cannot be read as settings. Nothing was written.")
        return 5

    changed = False
    if doc is not None:
        before = json.loads(json.dumps(doc))
        restored = _apply_removal(doc, rec)
        if rec.get("created_settings") and not restored:
            # settings.json did not exist before harden: taking it back means removing it.
            _backup(home, settings_path, raw)
            os.remove(settings_path)
            changed = True
        elif restored != before:
            _backup(home, settings_path, raw)
            _write_json(settings_path, restored)
            changed = True

    os.remove(record_path)
    print("REMOVED " + settings_path if changed else "NOTHING TO REMOVE")
    return 0


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    if os.name == "nt":
        print("UNSUPPORTED: the native sandbox needs macOS, Linux or WSL2.")
        return 4

    claude_dir = None
    home = None
    projects = []
    remove = False
    allow_instructions = False
    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--claude-dir":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            claude_dir = argv[i + 1]
            i += 2
        elif a == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            home = argv[i + 1]
            i += 2
        elif a == "--project":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            projects.append(argv[i + 1])
            i += 2
        elif a == "--allow-instructions":
            allow_instructions = True
            i += 1
        elif a == "--remove":
            remove = True
            i += 1
        else:
            print(USAGE)
            return 2

    home = _abs(home or os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow"))
    claude_dir = _abs(claude_dir or os.path.expanduser("~/.claude"))
    projects = [_abs(p) for p in projects]

    # harden changes Claude Code settings: inside Claude Code without a terminal
    # it is refused, like every setting change (the same check as init).
    if os.environ.get("CLAUDECODE") == "1" and not (sys.stdin.isatty() and sys.stdout.isatty()):
        sys.stdout.write(claudecode_check.MESSAGE)
        return 3

    if remove:
        return _remove(home, claude_dir)
    return _harden(home, claude_dir, projects, allow_instructions)


def _autotest():
    import glob
    import subprocess
    import tempfile

    script = os.path.abspath(__file__)
    results = []

    base_env = dict(os.environ)
    base_env.pop("CLAUDECODE", None)

    def run(env, cwd, *args):
        return subprocess.run([sys.executable, script] + list(args),
                              capture_output=True, text=True, input="", env=env, cwd=cwd)

    def settings_of(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)

    def bytes_of(path):
        with open(path, "rb") as f:
            return f.read()

    ORIG = {"model": "x", "permissions": {"deny": ["Bash(rm:*)"]}}

    # Test 1: harden writes the sandbox keys, keeps what existed, records what it added.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        r = run(env, tmp, "--home", home, "--claude-dir", claude)
        doc = settings_of(settings_path)
        sandbox = doc.get("sandbox", {})
        deny = doc.get("permissions", {}).get("deny", [])
        record = settings_of(os.path.join(home, "harden.json"))
        copies = sorted(glob.glob(os.path.join(home, "harden-backups", "settings.json.before-frugalflow-*")))
        ok = (r.returncode == 0
              and doc.get("model") == "x" and "Bash(rm:*)" in deny
              and sandbox.get("enabled") is True
              and sandbox.get("allowUnsandboxedCommands") is False
              and sandbox.get("failIfUnavailable") is True
              and home in sandbox.get("filesystem", {}).get("denyWrite", [])
              and _edit_rule(home, True) in deny
              and _edit_rule(settings_path, False) in deny
              and "Isolated mode:" in r.stdout
              and "read-only to the assistant too." in r.stdout
              and os.path.isfile(os.path.join(home, "harden.json"))
              and glob.glob(settings_path + ".before-frugalflow-*") == []
              and len(copies) == 1
              and record.get("backups") == copies)
        results.append(("1 harden writes the sandbox keys, keeps the existing settings, "
                        "copies settings.json into home/harden-backups and lists the copy", ok,
                        "rc=%d" % r.returncode))

    # Test 2: a rerun with nothing to add writes zero bytes and says ALREADY HARDENED.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        run(env, tmp, "--home", home, "--claude-dir", claude)
        before = bytes_of(settings_path)
        backups_before = len(glob.glob(os.path.join(home, "harden-backups", "settings.json.before-frugalflow-*")))
        r = run(env, tmp, "--home", home, "--claude-dir", claude)
        ok = (r.returncode == 0 and "ALREADY HARDENED" in r.stdout
              and bytes_of(settings_path) == before
              and len(glob.glob(os.path.join(home, "harden-backups", "settings.json.before-frugalflow-*"))) == backups_before)
        results.append(("2 a rerun that adds nothing writes zero bytes", ok, "rc=%d" % r.returncode))

    # Test 3: --remove restores the original JSON object and deletes the record.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        run(env, tmp, "--home", home, "--claude-dir", claude)
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = (r.returncode == 0 and settings_of(settings_path) == ORIG
              and not os.path.isfile(os.path.join(home, "harden.json")))
        results.append(("3 --remove restores the settings that existed before", ok, "rc=%d" % r.returncode))

    # Test 4: --remove without a record says NOTHING TO REMOVE and changes nothing.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        before = bytes_of(settings_path)
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = (r.returncode == 0 and "NOTHING TO REMOVE" in r.stdout
              and bytes_of(settings_path) == before)
        results.append(("4 --remove without a record changes nothing", ok, "rc=%d" % r.returncode))

    # Test 5: settings.json that cannot be read as settings: refusal 5, file intact, nothing written.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write("{ not json ]")
        before = bytes_of(settings_path)
        r = run(env, tmp, "--home", home, "--claude-dir", claude)
        ok = (r.returncode == 5 and "cannot be read as settings. Nothing was written." in r.stdout
              and bytes_of(settings_path) == before
              and not os.path.isfile(os.path.join(home, "harden.json"))
              and glob.glob(settings_path + ".before-frugalflow-*") == []
              and not os.path.isdir(os.path.join(home, "harden-backups")))
        results.append(("5 unreadable settings.json: refusal 5, file intact, nothing written", ok,
                        "rc=%d" % r.returncode))

    # Test 6: --project adds the vault log and the project settings paths.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude, project = (os.path.join(tmp, "home"), os.path.join(tmp, "claude"),
                                 os.path.join(tmp, "proj"))
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--project", project)
        doc = settings_of(settings_path)
        deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
        deny = doc.get("permissions", {}).get("deny", [])
        vault_log = os.path.join(project, "vault", "log.md")
        project_settings = os.path.join(project, ".claude", "settings.json")
        ok = (r.returncode == 0
              and vault_log in deny_write and project_settings in deny_write
              and _edit_rule(vault_log, False) in deny
              and _edit_rule(project_settings, False) in deny)
        # --remove takes the project paths back too.
        r2 = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = ok and r2.returncode == 0 and settings_of(settings_path) == ORIG
        results.append(("6 --project protects the vault log and the project settings, --remove takes them back", ok,
                        "rc=%d rc2=%d" % (r.returncode, r2.returncode)))

    # Test 7: under Claude Code without a terminal: refusal 3, settings untouched.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        env["CLAUDECODE"] = "1"
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        before = bytes_of(settings_path)
        r = run(env, tmp, "--home", home, "--claude-dir", claude)
        ok = (r.returncode == 3 and bytes_of(settings_path) == before
              and not os.path.isfile(os.path.join(home, "harden.json")))
        results.append(("7 refused under Claude Code without a terminal", ok, "rc=%d" % r.returncode))

    # Test 8: settings.json absent: harden creates it, --remove takes it back.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude = os.path.join(tmp, "home"), os.path.join(tmp, "claude")
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        r = run(env, tmp, "--home", home, "--claude-dir", claude)
        created = r.returncode == 0 and os.path.isfile(settings_path)
        r2 = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = (created and r2.returncode == 0 and not os.path.isfile(settings_path)
              and not os.path.isfile(os.path.join(home, "harden.json")))
        results.append(("8 settings.json absent: harden creates it, --remove takes it back", ok,
                        "rc=%d rc2=%d" % (r.returncode, r2.returncode)))

    # Test 10: --project adds the git hooks, .git/config, the whole .claude folder,
    # CLAUDE.md and .mcp.json; the claude dir adds hooks, skills, commands, agents
    # and CLAUDE.md. Folders get the /** rule, files the plain rule. --remove is exact.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude, project = (os.path.join(tmp, "home"), os.path.join(tmp, "claude"),
                                 os.path.join(tmp, "proj"))
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--project", project)
        doc = settings_of(settings_path)
        deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
        deny = doc.get("permissions", {}).get("deny", [])
        want_dir = [os.path.join(project, ".githooks"), os.path.join(project, ".git", "hooks"),
                    os.path.join(project, ".claude"), os.path.join(claude, "hooks"),
                    os.path.join(claude, "skills"), os.path.join(claude, "commands"),
                    os.path.join(claude, "agents")]
        want_file = [os.path.join(project, ".git", "config"), os.path.join(project, "CLAUDE.md"),
                     os.path.join(project, ".mcp.json"), os.path.join(claude, "CLAUDE.md")]
        ok = (r.returncode == 0
              and all(p in deny_write and _edit_rule(p, True) in deny for p in want_dir)
              and all(p in deny_write and _edit_rule(p, False) in deny for p in want_file))
        r2 = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = ok and r2.returncode == 0 and settings_of(settings_path) == ORIG
        results.append(("10 git hooks, .git/config, .claude, CLAUDE.md and .mcp.json are protected, "
                        "--remove is exact", ok, "rc=%d rc2=%d" % (r.returncode, r2.returncode)))

    # Test 11: --allow-instructions leaves every CLAUDE.md and CLAUDE.local.md out
    # and says so — the root files, a subfolder file that already exists, and the
    # pattern rules; everything else is protected as usual.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude, project = (os.path.join(tmp, "home"), os.path.join(tmp, "claude"),
                                 os.path.join(tmp, "proj"))
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        os.makedirs(os.path.join(project, "sub"), exist_ok=True)
        with open(os.path.join(project, "sub", "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("planted")
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--project", project,
                "--allow-instructions")
        doc = settings_of(settings_path)
        deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
        deny = doc.get("permissions", {}).get("deny", [])
        md_paths = [os.path.join(project, "CLAUDE.md"), os.path.join(claude, "CLAUDE.md"),
                    os.path.join(project, "CLAUDE.local.md"),
                    os.path.join(project, "sub", "CLAUDE.md")]
        ok = (r.returncode == 0
              and "NOTE: CLAUDE.md stays writable (--allow-instructions)" in r.stdout
              and all(p not in deny_write for p in md_paths)
              and all(_edit_rule(p, False) not in deny for p in md_paths)
              and not any("CLAUDE" in p for p in deny_write)
              and not any("CLAUDE" in rule for rule in deny)
              and os.path.join(project, ".githooks") in deny_write
              and _edit_rule(os.path.join(project, ".githooks"), True) in deny
              and os.path.join(claude, "hooks") in deny_write)
        r2 = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = ok and r2.returncode == 0 and settings_of(settings_path) == ORIG
        results.append(("11 --allow-instructions: no CLAUDE.md or CLAUDE.local.md is protected, "
                        "the rest is", ok, "rc=%d rc2=%d" % (r.returncode, r2.returncode)))

    # Test 12: nested instructions. CLAUDE.local.md at the project root is protected
    # like CLAUDE.md; a CLAUDE.md that already exists in a subfolder is protected
    # literally; the two /** pattern rules are written; the Limit line is printed;
    # --remove is exact.
    with tempfile.TemporaryDirectory() as tmp:
        env = dict(base_env, HOME=tmp, PYTHONPYCACHEPREFIX=os.path.join(tmp, "pycache"))
        home, claude, project = (os.path.join(tmp, "home"), os.path.join(tmp, "claude"),
                                 os.path.join(tmp, "proj"))
        os.makedirs(home, exist_ok=True)
        os.makedirs(claude, exist_ok=True)
        os.makedirs(os.path.join(project, "sub"), exist_ok=True)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(ORIG, f, indent=2)
        with open(os.path.join(project, "sub", "CLAUDE.md"), "w", encoding="utf-8") as f:
            f.write("planted")
        r = run(env, tmp, "--home", home, "--claude-dir", claude, "--project", project)
        doc = settings_of(settings_path)
        deny_write = doc.get("sandbox", {}).get("filesystem", {}).get("denyWrite", [])
        deny = doc.get("permissions", {}).get("deny", [])
        want_file = [os.path.join(project, "CLAUDE.local.md"),
                     os.path.join(project, "sub", "CLAUDE.md")]
        want_rule = ["Edit(//" + project.lstrip("/") + "/**/CLAUDE.md)",
                     "Edit(//" + project.lstrip("/") + "/**/CLAUDE.local.md)"]
        ok = (r.returncode == 0
              and all(p in deny_write and _edit_rule(p, False) in deny for p in want_file)
              and all(rule in deny for rule in want_rule)
              and "Limit: a CLAUDE.md created later in a new subfolder by a shell command "
                  "is not covered (the sandbox matches paths, not patterns); the file "
                  "tools are covered by pattern." in r.stdout)
        r2 = run(env, tmp, "--home", home, "--claude-dir", claude, "--remove")
        ok = ok and r2.returncode == 0 and settings_of(settings_path) == ORIG
        results.append(("12 CLAUDE.local.md and an existing subfolder CLAUDE.md are protected, "
                        "the /** pattern rules are written, --remove is exact", ok,
                        "rc=%d rc2=%d" % (r.returncode, r2.returncode)))

    # Test 9: --notice prints the notice.
    rn = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    ok = rn.returncode == 0 and rn.stdout.startswith("NAME      harden_cmd.py")
    results.append(("9 --notice prints the notice", ok, "rc=%d" % rn.returncode))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + (" | " + detail if detail else ""))
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "harden_cmd", sys.argv[1:])
