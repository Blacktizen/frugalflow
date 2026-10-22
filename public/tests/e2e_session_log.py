#!/usr/bin/env python3
"""End-to-end test of the session log and its end-of-turn guard."""

import os
import sys
import glob
import json
import shutil
import tempfile
import subprocess

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

LOG_TOOL = "journal_add.py"

NOTICE = """NAME      e2e_session_log.py - end-to-end test of the session log and its end-of-turn guard, driven like Claude Code drives them, on a project mounted in a temporary folder.
READS     the tools next to this folder: frugalflow.py, vault_check.py, session_log.py, r1_guard.py, session_note.py, session_digest.py.
WRITES    only in a temporary folder, always removed, even on failure; the session log goes there too. Exit 0 all steps pass, 1 a step failed, 2 usage.
EXAMPLE   python3 e2e_session_log.py
PITFALLS  2026-09-26 an end-to-end test left its temporary folder behind on every run; this one removes it in a finally block.
          No logged command is ever run: the hook events are simulated, the tools are real."""


def tool(env, name, *args, stdin=None):
    """Run a tool from BIN as a subprocess, return (returncode, stdout)."""
    proc = subprocess.run(
        [sys.executable, os.path.join(BIN, name)] + [str(a) for a in args],
        input=stdin, capture_output=True, text=True, env=env,
    )
    return (proc.returncode, proc.stdout)


def hook(env, payload):
    """Send a hook event JSON payload to session_log.py via stdin."""
    return tool(env, "session_log.py", stdin=json.dumps(payload))


def ran(env, session, ident, command, cwd):
    """Simulate a shell command: PreToolUse then PostToolUse hooks."""
    code_pre, _ = hook(env, {
        "session_id": session, "cwd": cwd, "hook_event_name": "PreToolUse",
        "tool_name": "Bash", "tool_use_id": ident,
        "tool_input": {"command": command},
    })
    code_post, _ = hook(env, {
        "session_id": session, "cwd": cwd, "hook_event_name": "PostToolUse",
        "tool_name": "Bash", "tool_use_id": ident,
        "tool_response": {"stdout": ""},
    })
    return code_pre == 0 and code_post == 0


def log_file(tmp, session):
    """Return the path of the session JSONL file inside the temp tree."""
    return glob.glob(os.path.join(tmp, "sessions", "*", session + ".jsonl"))[0]


def steps(tmp):
    """Run the 5 e2e steps on a project mounted in tmp. Return list of (label, ok)."""
    env = dict(os.environ,
               FRUGALFLOW_SESSIONS=os.path.join(tmp, "sessions"),
               FRUGALFLOW_ANCHORS=os.path.join(tmp, "anchors"))
    project = os.path.join(tmp, "demo")
    vault = os.path.join(project, "vault")
    log_call = "python3 " + os.path.join(BIN, LOG_TOOL) + " --vault " + vault + " --title fixed --field Decision=d"

    results = []

    # Step 1
    try:
        ok = False
        code_a, out_a = tool(env, "frugalflow.py", "new-project", "demo", "--root", tmp)
        code_b, _ = tool(env, "vault_check.py", "--vault", vault)
        with open(os.path.join(project, ".claude", "settings.json")) as fh:
            settings = json.load(fh)
        code_c, _ = tool(env, "frugalflow.py", "new-project", "demo", "--root", tmp)
        ok = (
            code_a == 0
            and out_a.startswith("PROJECT READY ")
            and code_b == 0
            and "r1_guard.py" in json.dumps(settings["hooks"]["Stop"])
            and "session_log.py" in json.dumps(settings["hooks"]["PreToolUse"])
            and code_c == 3
        )
    except Exception:
        ok = False
    results.append(("new-project mounts the vault and wires the hooks", ok))

    # Step 2
    try:
        ok = False
        code_a, _ = hook(env, {
            "session_id": "s1", "cwd": project,
            "hook_event_name": "SessionStart", "source": "startup",
        })
        flag_a = ran(env, "s1", "a1", "git status", project)
        code_b, out_b = tool(env, "session_log.py", "--check", "s1")
        with open(log_file(tmp, "s1")) as fh:
            lines = fh.readlines()
        entry = json.loads(lines[1])
        ok = (
            code_a == 0
            and flag_a
            and code_b == 0
            and out_b.startswith("SESSION LOG OK 3 lines, anchor INTACT")
            and entry["vault"] == vault
        )
    except Exception:
        ok = False
    results.append(("every event is a sealed line of the session log", ok))

    # Step 3
    try:
        ok = False
        flag_a = ran(env, "s1", "a2", "git commit -m fix", project)
        code_a, out_a = tool(env, "r1_guard.py", stdin=json.dumps({"session_id": "s1"}))
        flag_b = ran(env, "s1", "a3", log_call, project)
        code_b, out_b = tool(env, "r1_guard.py", stdin=json.dumps({"session_id": "s1"}))
        ok = (
            flag_a
            and code_a == 0
            and '"decision": "block"' in out_a
            and flag_b
            and code_b == 0
            and out_b == ""
        )
    except Exception:
        ok = False
    results.append(("a gesture without a log entry blocks the end of the turn, a real log call releases it", ok))

    # Step 4
    try:
        ok = False
        code_a, out_a = tool(env, "session_digest.py", "--session", "s1", "--vault", vault)
        code_b, _ = tool(env, "session_note.py", "--session", "s1", "--target", "5",
                         "--state", "DONE", "--text", "held")
        code_c, out_c = tool(env, "session_digest.py", "--session", "s1", "--vault", vault)
        ok = (
            code_a == 6
            and "CHECK verdicts FAIL no verdict for decisions 5" in out_a
            and code_b == 0
            and code_c == 0
            and "(DONE)" in out_c
            and "SESSION HEALTHY" in out_c
        )
    except Exception:
        ok = False
    results.append(("the closing pass wants a verdict on the decision, then passes", ok))

    # Step 5
    try:
        ok = False
        path = log_file(tmp, "s1")
        with open(path) as fh:
            original = fh.read()
        rewritten = original.replace("git status", "git stash")
        with open(path, "w") as fh:
            fh.write(rewritten)
        code_a, out_a = tool(env, "session_log.py", "--check", "s1")
        code_b, _ = tool(env, "session_note.py", "--session", "s1", "--target", "5", "--text", "x")
        first_three = original.split("\n")[:3]
        truncated = "\n".join(first_three) + "\n"
        with open(path, "w") as fh:
            fh.write(truncated)
        code_c, out_c = tool(env, "session_log.py", "--check", "s1")
        code_d, _ = tool(env, "session_digest.py", "--session", "s1")
        ok = (
            code_a == 6
            and "line 1 was rewritten" in out_a
            and code_b == 4
            and code_c == 6
            and "anchor TRUNCATED" in out_c
            and code_d == 6
        )
    except Exception:
        ok = False
    results.append(("a rewritten or truncated session log is caught", ok))

    return results


def main_run(parent):
    """Create a temp working dir, run steps, clean up, return (exit_code, lines)."""
    work_dir = tempfile.mkdtemp(dir=parent)
    lines = []
    try:
        step_results = steps(work_dir)
        fail_count = 0
        for idx, (label, ok) in enumerate(step_results, 1):
            if ok:
                lines.append("PASS %d %s" % (idx, label))
            else:
                lines.append("FAIL %d %s" % (idx, label))
                fail_count += 1
        if fail_count == 0:
            lines.append("E2E SESSION LOG OK")
        else:
            lines.append("E2E SESSION LOG FAILED %d of 5" % fail_count)
        code = 0 if fail_count == 0 else 1
    finally:
        shutil.rmtree(work_dir, ignore_errors=True)
    return (code, lines)


def autotest():
    """Run 5 self-verification proofs, print one line per proof, return exit code."""
    proofs = []

    # Proof 1: --notice
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True,
    )
    passed = proc.returncode == 0 and proc.stdout.startswith("NAME      e2e_session_log.py")
    detail = "expected exit 0, stdout starts 'NAME      e2e_session_log.py'; got exit %d, stdout[:30]=%r" % (
        proc.returncode, proc.stdout[:30])
    proofs.append(("notice exit 0 and correct header", passed, detail))

    # Proof 2: --bogus
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--bogus"],
        capture_output=True, text=True,
    )
    expected_stdout = "usage: e2e_session_log.py [--notice | --autotest]\n"
    passed = proc.returncode == 2 and proc.stdout == expected_stdout
    detail = "expected exit 2, stdout==%r; got exit %d, stdout=%r" % (
        expected_stdout, proc.returncode, proc.stdout)
    proofs.append(("bogus arg gives exit 2 and usage line", passed, detail))

    # Proof 3: main_run cleans up parent
    tmp_parent = tempfile.mkdtemp()
    try:
        main_run(tmp_parent)
        passed = os.listdir(tmp_parent) == []
    except Exception as exc:
        passed = False
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)
    detail = "expected empty parent dir after main_run; got %r" % (
        os.listdir(tmp_parent) if os.path.exists(tmp_parent) else "removed")
    proofs.append(("main_run removes its temp folder from parent", passed, detail))

    # Proof 4: main_run returns (code, lines) with correct structure
    tmp_parent = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent)
        passed = (
            code in (0, 1)
            and len(lines) == 6
            and all(ln.startswith("PASS ") or ln.startswith("FAIL ") for ln in lines[:5])
            and lines[5].startswith("E2E SESSION LOG ")
        )
    except Exception:
        code, lines = (-1, [])
        passed = False
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)
    detail = "expected code in (0,1), 6 lines (5 PASS/FAIL + 1 E2E); got code=%r, len=%d" % (
        code, len(lines))
    proofs.append(("main_run returns (code, 6 lines) with correct shape", passed, detail))

    # Proof 5: PASS/FAIL count consistent with final line and exit code
    tmp_parent = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent)
        fail_count = sum(1 for ln in lines if ln.startswith("FAIL "))
        expected_final = "E2E SESSION LOG OK" if fail_count == 0 else "E2E SESSION LOG FAILED %d of 5" % fail_count
        expected_code = 0 if fail_count == 0 else 1
        passed = lines[-1] == expected_final and code == expected_code
    except Exception:
        passed = False
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)
    detail = "expected last line %r and code %d; got last=%r, code=%r" % (
        expected_final, expected_code, lines[-1] if lines else "", code)
    proofs.append(("FAIL count matches final line and exit code", passed, detail))

    all_ok = True
    for idx, (desc, ok, detail) in enumerate(proofs, 1):
        if ok:
            print("PASS %d %s" % (idx, desc))
        else:
            print("FAIL %d %s -- %s" % (idx, desc, detail))
            all_ok = False
    return 0 if all_ok else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(autotest())
    elif len(sys.argv) == 1:
        code, lines = main_run(None)
        for line in lines:
            print(line)
        sys.exit(code)
    else:
        print("usage: e2e_session_log.py [--notice | --autotest]")
        sys.exit(2)


if __name__ == "__main__":
    main()
