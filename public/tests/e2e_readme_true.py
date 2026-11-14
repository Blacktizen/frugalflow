#!/usr/bin/env python3
"""e2e_readme_true.py - replays the L1 README-truth criteria a, a2, b, c, f.

Same montages as the L1 oracle (fresh home seeded by the SessionStart hook,
a real git gesture through the PreToolUse hook, the Stop hook judged after,
the reading gate judged on a new-project vault, journal_add then resume),
with one correction the oracle could not make inside its own checks: the
switch is written to FRUGALFLOW_HOME/preferences.json, the file the product
reads. The oracle wrote it to HOME/preferences.json, where nothing reads it.

One PASS or FAIL line per criterion. Exit 0 when all pass, 1 otherwise.
Standard library only.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile

# Determine repo root from FF_ROOT env var or from this file's location
if "FF_ROOT" in os.environ:
    REPO_ROOT = os.environ["FF_ROOT"]
else:
    REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

BIN_DIR = os.path.join(REPO_ROOT, "public", "bin")
PLUGIN = os.path.join(BIN_DIR, "plugin_hook.py")
FRUGALFLOW = os.path.join(BIN_DIR, "frugalflow.py")
README = os.path.join(REPO_ROOT, "README.md")

PHRASE_C = "refuses every write"
PHRASE_F = "the next session starts where the previous one stopped"


def excerpt(text, limit=140):
    """One-line excerpt of a measured output; <empty> when empty."""
    flat = " ".join((text or "").split())
    if flat == "":
        return "<empty>"
    if len(flat) > limit:
        flat = flat[:limit] + "..."
    return flat


def run_quiet(cmd, env=None, cwd=None, input_text=None):
    """Run a command with DEVNULL stdin (or a payload) and captured utf-8 text."""
    return subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        input=input_text,
        stdin=None if input_text is not None else subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def write_file(path, text):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(text)


def make_env(home):
    """Exact environment for every call: a private home, git reachable."""
    path = os.environ.get("PATH", "")
    if "/usr/bin" not in path:
        path = path + ":/usr/bin:/bin"
    return {
        "HOME": home,
        "FRUGALFLOW_HOME": os.path.join(home, ".frugalflow"),
        "PATH": path,
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
    }


def hook(plugin, tool, args, payload, env, cwd):
    """Launch one hook the way hooks.json does: python3 -I plugin_hook.py TOOL."""
    return run_quiet(
        [sys.executable, "-I", plugin, tool] + args,
        env=env,
        cwd=cwd,
        input_text=json.dumps(payload),
    )


def write_prefs(home, enabled, mode):
    """Set the switch in FRUGALFLOW_HOME/preferences.json, keeping the other keys.

    This is the file guard_hook.read_switch reads. Writing it to HOME instead
    (the oracle's defect) leaves the seeded mode in force and measures nothing.
    """
    path = os.path.join(home, ".frugalflow", "preferences.json")
    doc = {}
    try:
        with open(path, "r", encoding="utf-8") as handle:
            loaded = json.load(handle)
        if isinstance(loaded, dict):
            doc = loaded
    except Exception:
        doc = {}
    doc["switch"] = {"enabled": enabled, "mode": mode}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(doc, handle)


def git_setup(proj):
    """Plain git repo for a trial project (no frugalflow commit gate)."""
    run_quiet(["git", "init", "-q", proj])
    run_quiet(["git", "-C", proj, "config", "user.email", "e2e-readme@example.com"])
    run_quiet(["git", "-C", proj, "config", "user.name", "e2e readme"])


def make_gesture_project(tmp, name, with_vault):
    """Trial project: git repo, src files, optional vault (SCHEMA.md + log.md)."""
    proj = os.path.join(tmp, name)
    os.makedirs(os.path.join(proj, "src"))
    if with_vault:
        vault = os.path.join(proj, "vault")
        os.makedirs(vault)
        write_file(
            os.path.join(vault, "SCHEMA.md"),
            "# SCHEMA\n\n<!-- REQUIRED-READING\noverview.md\n-->\n\n"
            "# Rules\n- log.md is append-only and sealed.\n",
        )
        write_file(os.path.join(vault, "overview.md"), "# overview\n\nTrial vault.\n")
        write_file(os.path.join(vault, "log.md"), "# Log\n")
    write_file(os.path.join(proj, "src", "app.py"), "print('setup')\n")
    git_setup(proj)
    run_quiet(["git", "-C", proj, "add", "-A"])
    run_quiet(["git", "-C", proj, "commit", "-qm", "setup"])
    write_file(os.path.join(proj, "src", "turn.py"), "print('turn')\n")
    run_quiet(["git", "-C", proj, "add", "-A"])
    return proj


def run_gesture_case(plugin, env, home, proj, mode, sid):
    """Replay one turn: git commit through PreToolUse, then the Stop hook.

    Returns (r1_result, executed). The commit really runs and its PostToolUse
    is logged only when the guard hook did not deny it, like a real session.
    """
    write_prefs(home, True, mode)
    command = "git commit -m e2e-turn-" + sid
    pre = {
        "session_id": sid,
        "cwd": proj,
        "hook_event_name": "PreToolUse",
        "tool_name": "Bash",
        "tool_use_id": sid + "-t1",
        "tool_input": {"command": command},
    }
    hook(plugin, "session_log", [], pre, env, proj)
    guard = hook(plugin, "guard_hook", ["--hook"], pre, env, proj)
    executed = '"deny"' not in (guard.stdout or "")
    if executed:
        run_quiet(["git", "commit", "-m", "e2e-turn-" + sid], env=env, cwd=proj)
        post = {
            "session_id": sid,
            "cwd": proj,
            "hook_event_name": "PostToolUse",
            "tool_name": "Bash",
            "tool_use_id": sid + "-t1",
            "tool_response": {"stdout": "committed"},
        }
        hook(plugin, "session_log", [], post, env, proj)
    stop = {"session_id": sid, "cwd": proj, "hook_event_name": "Stop"}
    hook(plugin, "session_log", [], stop, env, proj)
    r1 = hook(plugin, "r1_guard", [], {"session_id": sid, "cwd": proj}, env, proj)
    return r1, executed


def criterion_a(plugin, env, home, tmp):
    """README: 'observe mode (nothing is blocked)' - Stop must not block, vault project."""
    proj = make_gesture_project(tmp, "proj-a", True)
    r1, executed = run_gesture_case(plugin, env, home, proj, "observe", "e2e-a")
    out = (r1.stdout or "") + (r1.stderr or "")
    ok = (
        executed
        and r1.returncode == 0
        and "decision" not in out
        and "block" not in out
    )
    detail = "a observe stop: stop rc=%d out=%s gesture_ran=%s" % (
        r1.returncode, excerpt(out), executed
    )
    return ok, detail


def criterion_a2(plugin, env, home, tmp):
    """Same turn in a folder without a vault, observe mode: nothing blocked."""
    proj = make_gesture_project(tmp, "proj-a2", False)
    r1, executed = run_gesture_case(plugin, env, home, proj, "observe", "e2e-a2")
    out = (r1.stdout or "") + (r1.stderr or "")
    ok = (
        executed
        and r1.returncode == 0
        and "decision" not in out
        and "block" not in out
    )
    detail = "a2 observe no-vault stop: stop rc=%d out=%s gesture_ran=%s" % (
        r1.returncode, excerpt(out), executed
    )
    return ok, detail


def criterion_b(plugin, env, home, tmp):
    """Active mode: the end of the turn is blocked after a gesture without a journal entry."""
    proj = make_gesture_project(tmp, "proj-b", True)
    r1, executed = run_gesture_case(plugin, env, home, proj, "active", "e2e-b")
    out = r1.stdout or ""
    ok = executed and r1.returncode == 0 and "decision" in out and "block" in out
    detail = "b active stop blocked: stop rc=%d out=%s gesture_ran=%s" % (
        r1.returncode, excerpt(out), executed
    )
    return ok, detail


def phrase_present_without_resume(readme_text, phrase):
    """True when the phrase appears and at least one line holding it never says resume."""
    text = readme_text.lower()
    target = phrase.lower()
    index = text.find(target)
    while index != -1:
        line_start = text.rfind("\n", 0, index) + 1
        line_end = text.find("\n", index)
        if line_end == -1:
            line_end = len(text)
        line = text[line_start:line_end]
        if "resume" not in line:
            return True
        index = text.find(target, index + 1)
    return False


def criterion_c(plugin, env, home, tmp, readme_text):
    """README: the reading gate - src write allowed, first vault write denied, second allowed."""
    result = run_quiet(
        [sys.executable, FRUGALFLOW, "new-project", "proj-c", "--root", tmp],
        env=env,
        cwd=tmp,
    )
    proj = os.path.join(tmp, "proj-c")
    if result.returncode != 0 or not os.path.isdir(os.path.join(proj, "vault")):
        return False, "c gate: new-project failed rc=%d out=%s" % (
            result.returncode, excerpt(result.stdout + result.stderr)
        )
    os.makedirs(os.path.join(proj, "src"), exist_ok=True)
    write_prefs(home, True, "active")

    def write_call(rel_path, tool_use_id):
        payload = {
            "session_id": "e2e-c",
            "cwd": proj,
            "hook_event_name": "PreToolUse",
            "tool_name": "Write",
            "tool_use_id": tool_use_id,
            "tool_input": {
                "file_path": os.path.join(proj, rel_path),
                "content": "e2e trial content\n",
            },
        }
        return hook(plugin, "guard_hook", ["--hook"], payload, env, proj)

    src_call = write_call(os.path.join("src", "app.py"), "c-src")
    vault_call = write_call(os.path.join("vault", "note.md"), "c-vault-1")
    vault_again = write_call(os.path.join("vault", "note.md"), "c-vault-2")
    src_allowed = src_call.returncode == 0 and '"deny"' not in (src_call.stdout or "")
    vault_denied = vault_call.returncode == 0 and '"deny"' in (vault_call.stdout or "")
    vault_second_allowed = (
        vault_again.returncode == 0 and '"deny"' not in (vault_again.stdout or "")
    )
    phrase_still_there = PHRASE_C.lower() in readme_text.lower()
    ok = src_allowed and vault_denied and vault_second_allowed and not phrase_still_there
    detail = "c gate: src=%s vault_first=%s vault_second=%s phrase_in_readme=%s" % (
        "allow" if src_allowed else "refused",
        "deny" if vault_denied else "allow",
        "allow" if vault_second_allowed else "refused",
        phrase_still_there,
    )
    return ok, detail


def criterion_f(tmp, env, readme_text):
    """README: resume writes the handoff - journal_add appends, resume shows the title."""
    result = run_quiet(
        [sys.executable, FRUGALFLOW, "new-project", "proj-f", "--root", tmp],
        env=env,
        cwd=tmp,
    )
    proj = os.path.join(tmp, "proj-f")
    if result.returncode != 0 or not os.path.isdir(os.path.join(proj, "vault")):
        return False, "f resume: new-project failed rc=%d out=%s" % (
            result.returncode, excerpt(result.stdout + result.stderr)
        )
    title = "E2E sealed handoff"
    journal = run_quiet(
        [
            sys.executable,
            "-I",
            os.path.join(BIN_DIR, "journal_add.py"),
            "--vault",
            os.path.join(proj, "vault"),
            "--title",
            title,
            "--field",
            "Decision=e2e check",
        ],
        env=env,
        cwd=proj,
    )
    journal_ok = journal.returncode == 0 and "APPENDED" in (journal.stdout or "")
    resume = run_quiet([sys.executable, FRUGALFLOW, "resume"], env=env, cwd=proj)
    resume_out = resume.stdout or ""
    title_shown = title in resume_out and resume_out.strip() != ""
    phrase_bad = phrase_present_without_resume(readme_text, PHRASE_F)
    ok = journal_ok and title_shown and not phrase_bad
    detail = "f resume: journal=%s resume_shows_title=%s phrase_without_resume=%s resume_out=%s" % (
        journal_ok,
        title_shown,
        phrase_bad,
        excerpt(resume_out, 80),
    )
    return ok, detail


def main():
    tmp = tempfile.mkdtemp(prefix="e2e-readme-true-")
    try:
        home = os.path.join(tmp, "home")
        env = make_env(home)
        with open(README, "r", encoding="utf-8") as handle:
            readme_text = handle.read()

        # First hook call seeds FRUGALFLOW_HOME the way the plugin does (observe).
        hook(
            PLUGIN,
            "session_log",
            [],
            {"session_id": "e2e-seed", "cwd": tmp, "hook_event_name": "SessionStart", "source": "startup"},
            env,
            tmp,
        )

        results = []
        for name, call in (
            ("a", lambda: criterion_a(PLUGIN, env, home, tmp)),
            ("a2", lambda: criterion_a2(PLUGIN, env, home, tmp)),
            ("b", lambda: criterion_b(PLUGIN, env, home, tmp)),
            ("c", lambda: criterion_c(PLUGIN, env, home, tmp, readme_text)),
            ("f", lambda: criterion_f(tmp, env, readme_text)),
        ):
            try:
                ok, detail = call()
            except Exception as exc:
                ok, detail = False, "%s exception: %s" % (name, exc)
            if not detail:
                ok, detail = False, "%s: empty measurement" % name
            results.append(ok)
            print(("PASS " if ok else "FAIL ") + detail)

        return 0 if all(results) else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
