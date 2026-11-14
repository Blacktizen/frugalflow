#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""session_resume.py - SessionStart hook: inject the project resume into the session."""

import sys
import os
import json
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import resume_cmd

NOTICE = (
    "NAME      session_resume.py - SessionStart hook: when the folder has a vault, injects the resume (journal entries by title, open todos, pages to reread) into additionalContext.\n"
    "READS     stdin hook JSON (cwd); cwd/vault through resume_cmd._build_resume_lines (overview.md, todo.md, log.md, SCHEMA.md). Never the vault of the last mounted project.\n"
    "WRITES    nothing: one JSON object on stdout (hookSpecificOutput.additionalContext), capped at 5000 characters; past the cap, pointers to the vault files replace the text. Nothing when cwd has no vault. Exit 0 in every case; an exception prints one line on stderr and injects nothing.\n"
    "EXAMPLE   echo '{\"cwd\": \"~/projects/demo\"}' | python3 session_resume.py\n"
    "PITFALLS  2026-11-14 the resume was a manual command only, so a new session started from memory of the last one; the hook injects it at startup, capped so the whole additionalContext of the SessionStart hooks stays under 6000 characters.\n"
    "          2026-11-14 resume_cmd falls back to the vault recorded by the last mount; this hook never does: it reads only cwd/vault, so a folder without a vault gets no resume.\n"
)

RESUME_LIMIT = 5000
# Room kept inside RESUME_LIMIT for the pointer block written at the end.
POINTER_RESERVE = 200
FULL_HANDOFF_LINE = "run frugalflow resume for the full handoff"


def _split_resume_sections(lines):
    """Split resume lines into (head, sections): head holds the lines before
    the first '## ' section; sections is a list of [header, body_lines]."""
    head = []
    sections = []
    current = None
    for line in lines:
        if line.startswith("## "):
            current = [line, []]
            sections.append(current)
        elif current is None:
            head.append(line)
        else:
            current[1].append(line)
    return head, sections


def _journal_entry_blocks(body):
    """Group entry lines into blocks; each block starts with its '### ' title."""
    blocks = []
    current = None
    for line in body:
        if line.startswith("### "):
            current = [line]
            blocks.append(current)
        elif current is not None:
            current.append(line)
    return blocks


def _fallback_resume(lines):
    """Build the capped resume, in this order: the carrier lines (the session
    rules, the Log line), then the journal entries newest first whole, then
    open todos, then where we stand, then pointers to what did not fit.
    An entry is added whole or not at all, never cut mid-line."""
    head, sections = _split_resume_sections(lines)
    rules = recent = todos = stand = None
    for header, body in sections:
        if header.startswith("## Rules for this session"):
            rules = body
        elif header.startswith("## Recent decisions"):
            recent = body
        elif header.startswith("## Open todos"):
            todos = body
        elif header.startswith("## Where we stand"):
            stand = body

    out = []
    budget = RESUME_LIMIT - POINTER_RESERVE

    def add(line):
        if len("\n".join(out + [line])) <= budget:
            out.append(line)
            return True
        return False

    # 1. Carrier lines: the resume title, the Log line, the session rules.
    if head:
        add(head[0])
    for line in head:
        if line.startswith("Log:") or line.startswith("LOG CHAIN BROKEN"):
            add(line)
            break
    if rules is not None:
        add("## Rules for this session")
        for line in rules:
            add(line)

    # 2. Journal entries, newest first, whole or not at all.
    blocks = _journal_entry_blocks(recent or [])
    kept = 0
    for block in reversed(blocks):
        if len("\n".join(out + block)) <= budget:
            out.extend(block)
            kept += 1
        else:
            break
    omitted_entries = len(blocks) - kept

    # 3. Open todos, then where we stand: whole if they fit, else line by line.
    def add_section(header, body):
        if not body or body == ["NOTHING FOUND"]:
            return False
        if len("\n".join(out + [header] + body)) <= budget:
            out.append(header)
            out.extend(body)
            return False
        omitted = False
        if add(header):
            for line in body:
                if not add(line):
                    omitted = True
                    break
        else:
            omitted = True
        return omitted

    todos_omitted = add_section("## Open todos", todos or [])
    stand_omitted = add_section("## Where we stand", stand or [])

    # 4. Pointers to what did not fit.
    pointers = ["Pointers:"]
    if omitted_entries > 0:
        pointers.append("vault/log.md (%d entries omitted)" % omitted_entries)
    if todos_omitted:
        pointers.append("vault/todo.md")
    if stand_omitted:
        pointers.append("vault/overview.md")
    pointers.append("vault/SCHEMA.md")
    pointers.append(FULL_HANDOFF_LINE)
    out.extend(pointers)
    return "\n".join(out)


def build_context(cwd):
    """Return the resume text for cwd, or None when cwd has no vault.
    Past RESUME_LIMIT the text falls back progressively, never all or nothing."""
    vault = os.path.join(cwd, "vault")
    if not os.path.isdir(vault):
        return None
    lines, _chain_ok = resume_cmd._build_resume_lines(vault, 5)
    text = "\n".join(lines)
    if len(text) <= RESUME_LIMIT:
        return text
    return _fallback_resume(lines)


def run_hook():
    """Read the SessionStart payload on stdin, print the hook JSON on stdout."""
    try:
        raw = sys.stdin.read()
        data = json.loads(raw)
        if not isinstance(data, dict):
            return 0
        cwd = data.get("cwd")
        if not isinstance(cwd, str) or cwd == "":
            return 0
        if not os.path.isdir(cwd):
            return 0
        context = build_context(cwd)
        if context is None:
            return 0
        output_obj = {
            "hookSpecificOutput": {
                "hookEventName": "SessionStart",
                "additionalContext": context,
            },
        }
        sys.stdout.write(json.dumps(output_obj))
        return 0
    except Exception as exc:
        sys.stderr.write("session_resume: " + str(exc) + "\n")
        return 0


def run_autotest():
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    script = os.path.abspath(__file__)
    base = tempfile.mkdtemp()
    results = []
    try:
        env = dict(os.environ)
        for key in list(env):
            if key.startswith("FRUGALFLOW_") or key.startswith("GIT_") or key == "CLAUDECODE":
                del env[key]
        env["HOME"] = os.path.join(base, "home")
        env["FRUGALFLOW_HOME"] = os.path.join(env["HOME"], ".frugalflow")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        os.makedirs(env["HOME"], exist_ok=True)

        proj = os.path.join(base, "proj")
        vault = os.path.join(proj, "vault")
        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "vault_new.py"),
             "--root", proj, "--name", "demo", "--today", "2026-11-14"],
            check=True, capture_output=True, env=env, timeout=30)
        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "journal_add.py"),
             "--vault", vault, "--title", "Picked sqlite",
             "--field", "Decision=Picked sqlite",
             "--field", "Why=one file, no server"],
            check=True, capture_output=True, env=env, timeout=30)
        sansvault = os.path.join(base, "sansvault")
        os.makedirs(sansvault, exist_ok=True)

        def hook_run(payload_text, cwd):
            return subprocess.run(
                [sys.executable, script], input=payload_text, cwd=cwd, env=env,
                capture_output=True, text=True, timeout=30)

        # Test 1: vault folder -> hook JSON with the sealed title in additionalContext.
        r1 = hook_run(json.dumps({"hook_event_name": "SessionStart", "cwd": proj}), proj)
        ok1 = r1.returncode == 0
        context1 = ""
        if ok1:
            try:
                obj = json.loads(r1.stdout)
                specific = obj.get("hookSpecificOutput")
                ok1 = (isinstance(specific, dict)
                       and specific.get("hookEventName") == "SessionStart")
                context1 = specific.get("additionalContext", "") if isinstance(specific, dict) else ""
                ok1 = ok1 and "Picked sqlite" in context1 and "# Resume:" in context1
            except ValueError:
                ok1 = False
        results.append(("1 vault folder: resume injected with the sealed title", ok1,
                        "rc=%d len=%d" % (r1.returncode, len(context1))))

        # Test 2: no vault, broken JSON, missing cwd -> exit 0, empty stdout.
        r2a = hook_run(json.dumps({"hook_event_name": "SessionStart", "cwd": sansvault}), sansvault)
        r2b = hook_run("{not json", proj)
        r2c = hook_run(json.dumps({"hook_event_name": "SessionStart"}), proj)
        ok2 = (r2a.returncode == 0 and r2a.stdout == ""
               and r2b.returncode == 0 and r2b.stdout == ""
               and r2c.returncode == 0 and r2c.stdout == "")
        results.append(("2 no vault, broken JSON, missing cwd: exit 0, empty stdout", ok2,
                        "rc=%d/%d/%d out=%r/%r/%r" % (
                            r2a.returncode, r2b.returncode, r2c.returncode,
                            r2a.stdout[:40], r2b.stdout[:40], r2c.stdout[:40])))

        # Test 3: a resume past the cap -> carrier lines and the last entry
        # kept, the tail of the overview omitted, pointers, cap respected.
        long_line = "OVERVIEWLONGMARK " + ("filler word " * 30)
        with open(os.path.join(vault, "overview.md"), "w", encoding="utf-8") as fh:
            fh.write("# demo - long overview\n")
            for i in range(20):
                fh.write("overview line %d %s\n" % (i, long_line))
        r3 = hook_run(json.dumps({"hook_event_name": "SessionStart", "cwd": proj}), proj)
        context3 = ""
        ok3 = r3.returncode == 0
        if ok3:
            try:
                obj = json.loads(r3.stdout)
                context3 = obj["hookSpecificOutput"]["additionalContext"]
                ok3 = ("run frugalflow resume for the full handoff" in context3
                       and "vault/overview.md" in context3
                       and "Never edit an old log entry" in context3
                       and "Picked sqlite" in context3
                       and "overview line 19" not in context3
                       and len(context3) < 6000)
            except (ValueError, KeyError, TypeError):
                ok3 = False
        results.append(("3 past the cap: carrier lines and last entry kept, "
                        "overview tail omitted, pointers, under 6000", ok3,
                        "rc=%d len=%d" % (r3.returncode, len(context3))))

        # Test 4: --notice exits 0 with the notice.
        r4 = subprocess.run([sys.executable, script, "--notice"],
                            capture_output=True, text=True, env=env, timeout=30)
        ok4 = r4.returncode == 0 and r4.stdout.startswith("NAME      session_resume.py")
        results.append(("4 --notice exits 0 with the notice", ok4,
                        "rc=%d" % r4.returncode))

        # Test 5: a big resume (long journal entries) -> the carrier lines and
        # the last entry are present, the omitted entries get a log pointer.
        for n in range(6):
            subprocess.run(
                [sys.executable, os.path.join(bin_dir, "journal_add.py"),
                 "--vault", vault, "--title", "long decision %d" % n,
                 "--field", "Decision=long decision %d sealed" % n,
                 "--field", "Why=" + ("filler text " * 120)],
                check=True, capture_output=True, env=env, timeout=30)
        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "journal_add.py"),
             "--vault", vault, "--title", "LastDecision",
             "--field", "Decision=last decision sealed",
             "--field", "Why=kept in the capped resume"],
            check=True, capture_output=True, env=env, timeout=30)
        r5 = hook_run(json.dumps({"hook_event_name": "SessionStart", "cwd": proj}), proj)
        context5 = ""
        ok5 = r5.returncode == 0
        if ok5:
            try:
                obj = json.loads(r5.stdout)
                context5 = obj["hookSpecificOutput"]["additionalContext"]
                ok5 = ("Never edit an old log entry" in context5
                       and "LastDecision" in context5
                       and "vault/log.md" in context5
                       and "run frugalflow resume for the full handoff" in context5
                       and len(context5) < 6000)
            except (ValueError, KeyError, TypeError):
                ok5 = False
        results.append(("5 big resume: carrier lines and last entry present, "
                        "log pointer for omitted entries, under 6000", ok5,
                        "rc=%d len=%d" % (r5.returncode, len(context5))))
    finally:
        shutil.rmtree(base, ignore_errors=True)

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + " | " + detail)
            all_pass = False
    print("AUTOTEST %d/5" % (5 if all_pass else sum(1 for _d, p, _x in results if p)))
    return 0 if all_pass else 1


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return run_autotest()
    # Hook mode: any other argument set still runs the hook, which exits 0.
    return run_hook()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
