#!/usr/bin/env python3
# e2e_journal_zone.py - end-to-end test: the protected zone covers the Claude settings file and the vault journals

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
HOOK = os.path.join(BIN, "guard_hook.py")
JOURNAL_ADD = os.path.join(BIN, "journal_add.py")

SETTINGS = {
    "code_extensions": [".py"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}

LOG_TEXT = "# Log\n\n"
SCHEMA_TEXT = "# Schema\n\nThrowaway vault for the journal zone test.\n"
SETTINGS_TEXT = '{"permissions": {"allow": []}}\n'


def ENV(home):
    # every trial runs with a throwaway HOME and FRUGALFLOW_HOME under /tmp: never the real HOME.
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY", "FRUGALFLOW_BRIEF_RULES"):
        env.pop(key, None)
    env["HOME"] = home
    env["FRUGALFLOW_HOME"] = home
    return env


def new_home():
    h = tempfile.mkdtemp(prefix="ff_zone_home_", dir="/tmp")
    with open(os.path.join(h, "guard.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(SETTINGS))
    with open(os.path.join(h, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write("")
    return h


def new_vault():
    # a vault: a folder holding a SCHEMA.md beside log.md.
    v = tempfile.mkdtemp(prefix="ff_zone_vault_", dir="/tmp")
    with open(os.path.join(v, "SCHEMA.md"), "w", encoding="utf-8") as f:
        f.write(SCHEMA_TEXT)
    with open(os.path.join(v, "log.md"), "w", encoding="utf-8") as f:
        f.write(LOG_TEXT)
    return v


def HOOK_CALL(home, tool, tool_input, cwd):
    payload = json.dumps({"tool_name": tool, "tool_input": tool_input, "cwd": cwd})
    r = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=payload,
        capture_output=True,
        text=True,
        env=ENV(home),
        timeout=120,
    )
    stripped = (r.stdout or "").strip()
    if stripped == "":
        return (r.returncode, "allow", "")
    try:
        h = json.loads(stripped)["hookSpecificOutput"]
        return (r.returncode, h["permissionDecision"], h.get("permissionDecisionReason", ""))
    except (json.JSONDecodeError, KeyError, TypeError):
        return (r.returncode, "unreadable", stripped)


def has_fix_line(reason):
    """True when a line of the refusal begins with 'To fix:'."""
    return any(line.strip().startswith("To fix:") for line in reason.splitlines())


def proof_e1():
    """Write and Bash writes on the two new protected files are refused with a To fix:
    line; reading them stays allowed."""
    home = new_home()
    vault = new_vault()
    try:
        settings_path = os.path.join(home, ".claude", "settings.json")
        os.makedirs(os.path.dirname(settings_path), exist_ok=True)
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(SETTINGS_TEXT)
        log_path = os.path.join(vault, "log.md")

        denies = 0
        reads = 0
        detail = []

        deny_calls = [
            ("Write settings.json", "Write", {"file_path": settings_path, "content": SETTINGS_TEXT}),
            ("Write vault log.md", "Write", {"file_path": log_path, "content": "x\n"}),
            ("Bash echo append log.md", "Bash", {"command": "echo x >> " + log_path}),
            # 2026-11-12: sort with an output file writes it, even though sort reads.
            ("Bash sort -o log.md", "Bash",
             {"command": "sort -o " + log_path + " /tmp/ff_zone_sort_in"}),
        ]
        for label, tool, tool_input in deny_calls:
            code, decision, reason = HOOK_CALL(home, tool, tool_input, home)
            if code == 0 and decision == "deny" and has_fix_line(reason):
                denies += 1
            else:
                detail.append(label + "=" + str(decision) + "/code=" + str(code) + "/reason=" + repr(reason[:120]))

        read_calls = [
            ("Read settings.json", "Read", {"file_path": settings_path}),
            ("Read vault log.md", "Read", {"file_path": log_path}),
            # 2026-11-12: text-processing readers (sort, tr) are not writes.
            ("Bash sort log.md | uniq -c", "Bash", {"command": "sort " + log_path + " | uniq -c"}),
            ("Bash tr a-z A-Z < log.md", "Bash", {"command": "tr a-z A-Z < " + log_path}),
        ]
        for label, tool, tool_input in read_calls:
            code, decision, reason = HOOK_CALL(home, tool, tool_input, home)
            if code == 0 and decision == "allow":
                reads += 1
            else:
                detail.append(label + "=" + str(decision) + "/code=" + str(code) + "/reason=" + repr(reason[:120]))

        expected = "4 denies with a To fix: line and 4 reads allowed"
        got = "%d denies with a To fix: line and %d reads allowed" % (denies, reads)
        if detail:
            got += " (" + "; ".join(detail) + ")"
        return (denies == 4 and reads == 4, expected, got)
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)


def proof_e2():
    """journal_add.py on the throwaway vault exits 0 and adds an entry to log.md;
    the same gesture through the hook stays allowed."""
    home = new_home()
    vault = new_vault()
    try:
        args = [
            sys.executable,
            JOURNAL_ADD,
            "--vault", vault,
            "--title", "journal zone proof",
            "--field", "Decision=journal_add stays allowed",
            "--when", "2026-11-05 12:00",
        ]
        r = subprocess.run(args, capture_output=True, text=True, env=ENV(home), timeout=120)
        with open(os.path.join(vault, "log.md"), "r", encoding="utf-8") as f:
            text = f.read()

        ok_code = r.returncode == 0
        ok_entry = "journal zone proof" in text and "Decision: journal_add stays allowed" in text
        code_h, decision_h, reason_h = HOOK_CALL(home, "Bash", {"command": " ".join(args)}, home)
        ok_gesture = code_h == 0 and decision_h == "allow"

        expected = "exit 0, entry in log.md, hook allows the gesture"
        got = "exit %s, entry %s, hook %s" % (
            r.returncode,
            "added" if ok_entry else "missing",
            decision_h if code_h == 0 else "code=" + str(code_h),
        )
        if not ok_code:
            got += " (stdout=" + repr(r.stdout[:120]) + " stderr=" + repr(r.stderr[:120]) + ")"
        if not ok_gesture:
            got += " (reason=" + repr(reason_h[:120]) + ")"
        return (ok_code and ok_entry and ok_gesture, expected, got)
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)


def proof_e3_casse():
    """A protected file named in mixed case is refused like its lowercase name: the zone
    compares names without case. Witnesses keep the zone from widening: a same-named file
    in a throwaway work folder outside the home stays free, and the exact lowercase name
    stays refused."""
    home = new_home()
    vault = new_vault()
    work = tempfile.mkdtemp(prefix="ff_zone_work_", dir="/tmp")
    try:
        cdir = os.path.join(home, ".claude")
        os.makedirs(cdir, exist_ok=True)
        with open(os.path.join(cdir, "settings.json"), "w", encoding="utf-8") as f:
            f.write(SETTINGS_TEXT)

        # (label, tool, tool_input, cwd, expected decision)
        cases = [
            ("Write Preferences.json", "Write",
             {"file_path": os.path.join(home, "Preferences.json"), "content": "{}"}, home, "deny"),
            ("Write GUARD.json", "Write",
             {"file_path": os.path.join(home, "GUARD.json"), "content": "{}"}, home, "deny"),
            ("Edit GUARD.json", "Edit",
             {"file_path": os.path.join(home, "GUARD.json"),
              "old_string": "allow", "new_string": "deny"}, home, "deny"),
            ("Write AUDIT.jsonl", "Write",
             {"file_path": os.path.join(home, "AUDIT.jsonl"), "content": "x\n"}, home, "deny"),
            ("MultiEdit Models-mixed", "MultiEdit",
             {"file_path": os.path.join(home, "Mo" + "De" + "Ls.json"),  # lang-ok: De is a fragment of MoDeLs.json, not French
              "edits": [{"old_string": "a", "new_string": "b"}]}, home, "deny"),
            ("Write Delegations.jsonl", "Write",
             {"file_path": os.path.join(home, "Delegations.jsonl"), "content": "x\n"}, home, "deny"),
            ("Write .claude/Settings.json", "Write",
             {"file_path": os.path.join(cdir, "Settings.json"), "content": "{}"}, home, "deny"),
            ("Write vault LOG.md", "Write",
             {"file_path": os.path.join(vault, "LOG.md"), "content": "x\n"}, home, "deny"),
            ("Bash printf PREFERENCES.json", "Bash",
             {"command": "printf '{}' > " + os.path.join(home, "PREFERENCES.json")}, home, "deny"),
            ("Bash echo Delegations.jsonl", "Bash",
             {"command": "echo x >> " + os.path.join(home, "Delegations.jsonl")}, home, "deny"),
            ("Write workdir Preferences.json", "Write",
             {"file_path": os.path.join(work, "Preferences.json"), "content": "{}"}, work, "allow"),
            ("Write preferences.json lowercase", "Write",
             {"file_path": os.path.join(home, "preferences.json"), "content": "{}"}, home, "deny"),
        ]

        results = []
        ok_all = True
        for label, tool, tool_input, cwd, expect in cases:
            code, decision, reason = HOOK_CALL(home, tool, tool_input, cwd)
            seen = decision if code == 0 else "code=" + str(code)
            if not (code == 0 and decision == expect):
                ok_all = False
                seen += "/code=" + str(code) + "/reason=" + repr(reason[:120])
            results.append(label + "=" + seen)

        expected = ("12 cases as expected: 10 mixed-case denies, 1 allow in a work folder "
                    "outside the home, 1 lowercase deny")
        got = "; ".join(results)
        return (ok_all, expected, got)
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(work, ignore_errors=True)


def run_e2e():
    fail_k = 0
    for num, proof in ((1, proof_e1), (2, proof_e2), (3, proof_e3_casse)):
        try:
            ok, expected, got = proof()
        except Exception as e:
            ok, expected, got = False, "no exception", "exception " + repr(e)
        if not ok:
            fail_k += 1
        print("%s %d %s | expected %s | got %s" % ("PASS" if ok else "FAIL", num, label_of(num), expected, got))
    return fail_k


def label_of(num):
    return {1: "zone denies writes, allows reads", 2: "journal_add gesture", 3: "mixed-case refused"}.get(num, "")


def main():
    fail_k = run_e2e()
    if fail_k == 0:
        print("E2E JOURNAL ZONE OK")
        sys.exit(0)
    print("E2E JOURNAL ZONE FAILED %d" % fail_k)
    sys.exit(1)


if __name__ == "__main__":
    main()
