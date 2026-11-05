#!/usr/bin/env python3
# e2e_git_vault.py - end-to-end test: git vault protection (C4, C10, C19)

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
HOOK = os.path.join(BIN, "guard_hook.py")

SETTINGS = {
    "code_extensions": [".py"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}


def ENV(home):
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY", "FRUGALFLOW_BRIEF_RULES"):
        env.pop(key, None)
    env["HOME"] = home
    env["FRUGALFLOW_HOME"] = home
    return env


def new_home():
    h = tempfile.mkdtemp(prefix="ff_git_home_", dir="/tmp")
    with open(os.path.join(h, "guard.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(SETTINGS))
    with open(os.path.join(h, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write("")
    return h


def new_vault():
    v = tempfile.mkdtemp(prefix="ff_git_vault_", dir="/tmp")
    # Initialize as git repo
    subprocess.run(["git", "init"], cwd=v, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture-user"], cwd=v, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=v, capture_output=True)
    # Create vault markers
    with open(os.path.join(v, "SCHEMA.md"), "w", encoding="utf-8") as f:
        f.write("# Schema\n")
    with open(os.path.join(v, "log.md"), "w", encoding="utf-8") as f:
        f.write("# Log\n")
    with open(os.path.join(v, "overview.md"), "w", encoding="utf-8") as f:
        f.write("# Overview\n")
    with open(os.path.join(v, "notes.md"), "w", encoding="utf-8") as f:
        f.write("# Notes\n")
    # Add and commit
    subprocess.run(["git", "add", "."], cwd=v, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=v, capture_output=True)
    return v


def new_project():
    p = tempfile.mkdtemp(prefix="ff_git_proj_", dir="/tmp")
    # Initialize as git repo (no vault markers)
    subprocess.run(["git", "init"], cwd=p, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture-user"], cwd=p, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=p, capture_output=True)
    with open(os.path.join(p, "a.txt"), "w", encoding="utf-8") as f:
        f.write("a\n")
    os.makedirs(os.path.join(p, "build"), exist_ok=True)
    with open(os.path.join(p, "build", "o.txt"), "w", encoding="utf-8") as f:
        f.write("o\n")
    subprocess.run(["git", "add", "."], cwd=p, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=p, capture_output=True)
    return p


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


def deny_contains(reason):
    return "deny" in reason


def run_case(label, home, tool, tool_input, cwd, expect_deny):
    code, decision, reason = HOOK_CALL(home, tool, tool_input, cwd)
    got_deny = (code == 0 and decision == "deny")
    if got_deny == expect_deny:
        return True, f"PASS {label}: expected {'deny' if expect_deny else 'allow'}, got {'deny' if got_deny else 'allow'}"
    else:
        return False, f"FAIL {label}: expected {'deny' if expect_deny else 'allow'}, got decision={decision} code={code} reason={reason[:120]!r}"


def proof_c4_git_global_options():
    """C4: git -C DIR, --git-dir, --work-tree tracked like cd; destructive ops in vault refused."""
    home = new_home()
    vault = new_vault()
    try:
        results = []

        # C4: git -C vault checkout -> deny
        ok, msg = run_case("C4: git -C vault checkout", home, "Bash",
                           {"command": f"git -C {vault} checkout HEAD"}, vault, True)
        results.append((ok, msg))

        # C4: git --git-dir=vault/.git --work-tree=vault checkout -> deny
        ok, msg = run_case("C4: git --git-dir --work-tree checkout", home, "Bash",
                           {"command": f"git --git-dir={vault}/.git --work-tree={vault} checkout HEAD"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault restore -> deny
        ok, msg = run_case("C4: git -C vault restore", home, "Bash",
                           {"command": f"git -C {vault} restore ."}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault reset --hard -> deny
        ok, msg = run_case("C4: git -C vault reset --hard", home, "Bash",
                           {"command": f"git -C {vault} reset --hard"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault stash push -> deny
        ok, msg = run_case("C4: git -C vault stash push", home, "Bash",
                           {"command": f"git -C {vault} stash push"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault clean -fdx -> deny
        ok, msg = run_case("C4: git -C vault clean", home, "Bash",
                           {"command": f"git -C {vault} clean -fdx"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault switch -> deny
        ok, msg = run_case("C4: git -C vault switch", home, "Bash",
                           {"command": f"git -C {vault} switch main"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault pull -> deny
        ok, msg = run_case("C4: git -C vault pull", home, "Bash",
                           {"command": f"git -C {vault} pull"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault merge -> deny
        ok, msg = run_case("C4: git -C vault merge", home, "Bash",
                           {"command": f"git -C {vault} merge main"}, vault, True)
        results.append((ok, msg))

        # C4: git -C vault rebase -> deny
        ok, msg = run_case("C4: git -C vault rebase", home, "Bash",
                           {"command": f"git -C {vault} rebase main"}, vault, True)
        results.append((ok, msg))

        # C4 witness: git -C vault status -> allow
        ok, msg = run_case("C4 witness: git -C vault status", home, "Bash",
                           {"command": f"git -C {vault} status"}, vault, False)
        results.append((ok, msg))

        # C4 witness: git -C vault log -> allow
        ok, msg = run_case("C4 witness: git -C vault log", home, "Bash",
                           {"command": f"git -C {vault} log"}, vault, False)
        results.append((ok, msg))

        # C4 witness: git -C vault diff -> allow
        ok, msg = run_case("C4 witness: git -C vault diff", home, "Bash",
                           {"command": f"git -C {vault} diff"}, vault, False)
        results.append((ok, msg))

        # C4 witness: git -C vault add -> allow
        ok, msg = run_case("C4 witness: git -C vault add", home, "Bash",
                           {"command": f"git -C {vault} add ."}, vault, False)
        results.append((ok, msg))

        # C4 witness: git -C vault commit -> allow
        ok, msg = run_case("C4 witness: git -C vault commit", home, "Bash",
                           {"command": f"git -C {vault} commit -m test"}, vault, False)
        results.append((ok, msg))

        # C4: words judged from -C dir (log.md in vault should be detected)
        ok, msg = run_case("C4: words judged from -C dir", home, "Bash",
                           {"command": f"git -C {vault} checkout log.md"}, vault, True)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)


def proof_c10_same_rule():
    """C10: Same destructive commands launched inside vault (cwd=vault) refused."""
    home = new_home()
    vault = new_vault()
    project = new_project()
    try:
        results = []

        # C10: git reset --hard in vault -> deny
        ok, msg = run_case("C10: git reset --hard in vault", home, "Bash",
                           {"command": "git reset --hard"}, vault, True)
        results.append((ok, msg))

        # C10 vault without .git: clean run from a sub-folder of the vault -> deny (in_vault walks up)
        ok, msg = run_case("C10 vault without .git: clean in vault sub-folder", home, "Bash",
                           {"command": "git clean -fdx"}, os.path.join(vault, "05-reference"), True)
        results.append((ok, msg))

        # C10 vault without .git: checkout of a branch from the vault -> deny
        ok, msg = run_case("C10 vault without .git: checkout branch in vault", home, "Bash",
                           {"command": "git checkout other"}, vault, True)
        results.append((ok, msg))

        # C10: git clean -fdx in vault -> deny
        ok, msg = run_case("C10: git clean -fdx in vault", home, "Bash",
                           {"command": "git clean -fdx"}, vault, True)
        results.append((ok, msg))

        # C10: git stash push in vault -> deny
        ok, msg = run_case("C10: git stash push in vault", home, "Bash",
                           {"command": "git stash push"}, vault, True)
        results.append((ok, msg))

        # C10: git switch in vault -> deny
        ok, msg = run_case("C10: git switch in vault", home, "Bash",
                           {"command": "git switch main"}, vault, True)
        results.append((ok, msg))

        # C10: git pull in vault -> deny
        ok, msg = run_case("C10: git pull in vault", home, "Bash",
                           {"command": "git pull"}, vault, True)
        results.append((ok, msg))

        # C10: git merge in vault -> deny
        ok, msg = run_case("C10: git merge in vault", home, "Bash",
                           {"command": "git merge main"}, vault, True)
        results.append((ok, msg))

        # C10 witness: git status in vault -> allow
        ok, msg = run_case("C10 witness: git status in vault", home, "Bash",
                           {"command": "git status"}, vault, False)
        results.append((ok, msg))

        # C10 witness: git log in vault -> allow
        ok, msg = run_case("C10 witness: git log in vault", home, "Bash",
                           {"command": "git log"}, vault, False)
        results.append((ok, msg))

        # C10 witness: git diff in vault -> allow
        ok, msg = run_case("C10 witness: git diff in vault", home, "Bash",
                           {"command": "git diff"}, vault, False)
        results.append((ok, msg))

        # C10 witness: git add in vault -> allow
        ok, msg = run_case("C10 witness: git add in vault", home, "Bash",
                           {"command": "git add ."}, vault, False)
        results.append((ok, msg))

        # C10 witness: git commit in vault -> allow
        ok, msg = run_case("C10 witness: git commit in vault", home, "Bash",
                           {"command": "git commit -m test"}, vault, False)
        results.append((ok, msg))

        # C10 witness: git reset --hard in project (no vault) -> allow
        ok, msg = run_case("C10 witness: git reset --hard in project", home, "Bash",
                           {"command": "git reset --hard"}, project, False)
        results.append((ok, msg))

        # C10 witness: git clean in project (no vault) -> allow
        ok, msg = run_case("C10 witness: git clean in project", home, "Bash",
                           {"command": "git clean -fdx"}, project, False)
        results.append((ok, msg))

        # C10 witness: git switch in project (no vault) -> allow
        ok, msg = run_case("C10 witness: git switch in project", home, "Bash",
                           {"command": "git switch main"}, project, False)
        results.append((ok, msg))

        # C10 witness: git stash push in project (no vault) -> allow
        ok, msg = run_case("C10 witness: git stash push in project", home, "Bash",
                           {"command": "git stash push"}, project, False)
        results.append((ok, msg))

        # C10 witness: git config user.name -> allow
        ok, msg = run_case("C10 witness: git config user.name", home, "Bash",
                           {"command": "git config user.name"}, vault, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(project, ignore_errors=True)


def proof_c19_hooksPath():
    """C19: git config core.hooksPath and git -c core.hooksPath=... always refused."""
    home = new_home()
    vault = new_vault()
    project = new_project()
    try:
        results = []

        # C19: git config core.hooksPath ... -> deny (in vault)
        ok, msg = run_case("C19: git config core.hooksPath in vault", home, "Bash",
                           {"command": "git config core.hooksPath /tmp/hooks"}, vault, True)
        results.append((ok, msg))

        # C19: git config core.hooksPath ... -> deny (in project)
        ok, msg = run_case("C19: git config core.hooksPath in project", home, "Bash",
                           {"command": "git config core.hooksPath /tmp/hooks"}, project, True)
        results.append((ok, msg))

        # C19: git -c core.hooksPath=... commit -> deny (in vault)
        ok, msg = run_case("C19: git -c core.hooksPath commit in vault", home, "Bash",
                           {"command": "git -c core.hooksPath=/tmp/hooks commit -m test"}, vault, True)
        results.append((ok, msg))

        # C19: git -c core.hooksPath=... commit -> deny (in project)
        ok, msg = run_case("C19: git -c core.hooksPath commit in project", home, "Bash",
                           {"command": "git -c core.hooksPath=/tmp/hooks commit -m test"}, project, True)
        results.append((ok, msg))

        # C19 witness: git config --get core.hooksPath -> allow
        ok, msg = run_case("C19 witness: git config --get core.hooksPath", home, "Bash",
                           {"command": "git config --get core.hooksPath"}, vault, False)
        results.append((ok, msg))

        # C19 witness: git config --list -> allow
        ok, msg = run_case("C19 witness: git config --list", home, "Bash",
                           {"command": "git config --list"}, vault, False)
        results.append((ok, msg))

        # C19 witness: git config user.name -> allow
        ok, msg = run_case("C19 witness: git config user.name", home, "Bash",
                           {"command": "git config user.name"}, vault, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(project, ignore_errors=True)


def run_e2e():
    fail_k = 0
    case_num = 0

    for proof_func, label in [
        (proof_c4_git_global_options, "C4 git global options"),
        (proof_c10_same_rule, "C10 same rule"),
        (proof_c19_hooksPath, "C19 core.hooksPath"),
    ]:
        try:
            results = proof_func()
        except Exception as e:
            fail_k += 1
            case_num += 1
            print(f"FAIL {case_num} {label}: exception {e!r}")
            continue

        for ok, msg in results:
            case_num += 1
            if not ok:
                fail_k += 1
            print(msg)

    return fail_k


def main():
    fail_k = run_e2e()
    if fail_k == 0:
        print("E2E GIT VAULT OK")
        sys.exit(0)
    print(f"E2E GIT VAULT FAILED {fail_k}")
    sys.exit(1)


if __name__ == "__main__":
    main()