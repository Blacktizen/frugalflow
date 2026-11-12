#!/usr/bin/env python3
# e2e_git_vault.py - end-to-end test: git vault protection (C4, C10, C19, D6, D11)

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


def new_plain_vault():
    # A vault folder without .git: the rule looks at the folders, not at git.
    v = tempfile.mkdtemp(prefix="ff_git_plainvault_", dir="/tmp")
    with open(os.path.join(v, "SCHEMA.md"), "w", encoding="utf-8") as f:
        f.write("# Schema\n")
    with open(os.path.join(v, "log.md"), "w", encoding="utf-8") as f:
        f.write("# Log\n")
    with open(os.path.join(v, "overview.md"), "w", encoding="utf-8") as f:
        f.write("# Overview\n")
    return v


def new_project_with_vault():
    # A git repo that holds a vault in a sub-folder.
    p = tempfile.mkdtemp(prefix="ff_git_hold_", dir="/tmp")
    subprocess.run(["git", "init"], cwd=p, capture_output=True)
    subprocess.run(["git", "config", "user.email", "fixture-user"], cwd=p, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test"], cwd=p, capture_output=True)
    v = os.path.join(p, "vault")
    os.makedirs(v)
    with open(os.path.join(v, "SCHEMA.md"), "w", encoding="utf-8") as f:
        f.write("# Schema\n")
    with open(os.path.join(v, "log.md"), "w", encoding="utf-8") as f:
        f.write("# Log\n")
    with open(os.path.join(v, "overview.md"), "w", encoding="utf-8") as f:
        f.write("# Overview\n")
    with open(os.path.join(p, "a.txt"), "w", encoding="utf-8") as f:
        f.write("a\n")
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


def proof_d6_destructive_subcommands():
    """D6: read-tree, checkout-index, cherry-pick, revert, am, worktree add,
    reset --keep/--merge, stash pop/apply rewrite the tree and are refused."""
    home = new_home()
    vault = new_vault()
    plain = new_plain_vault()
    try:
        results = []

        # D6: git read-tree -u --reset in vault -> deny
        ok, msg = run_case("D6: git read-tree -u --reset in vault", home, "Bash",
                           {"command": "git read-tree -u --reset HEAD~1"}, vault, True)
        results.append((ok, msg))

        # D6: git checkout-index -a -f in vault -> deny
        ok, msg = run_case("D6: git checkout-index in vault", home, "Bash",
                           {"command": "git checkout-index -a -f"}, vault, True)
        results.append((ok, msg))

        # D6: git cherry-pick in vault -> deny
        ok, msg = run_case("D6: git cherry-pick in vault", home, "Bash",
                           {"command": "git cherry-pick HEAD~1"}, vault, True)
        results.append((ok, msg))

        # D6: git revert in vault -> deny
        ok, msg = run_case("D6: git revert in vault", home, "Bash",
                           {"command": "git revert HEAD"}, vault, True)
        results.append((ok, msg))

        # D6: git am in vault -> deny
        ok, msg = run_case("D6: git am in vault", home, "Bash",
                           {"command": "git am patch.mbox"}, vault, True)
        results.append((ok, msg))

        # D6: git worktree add --force . in vault -> deny (target is the vault itself)
        ok, msg = run_case("D6: git worktree add --force . in vault", home, "Bash",
                           {"command": "git worktree add --force . HEAD~1"}, vault, True)
        results.append((ok, msg))

        # D6: git reset --keep in vault -> deny
        ok, msg = run_case("D6: git reset --keep in vault", home, "Bash",
                           {"command": "git reset --keep HEAD~1"}, vault, True)
        results.append((ok, msg))

        # D6: git reset --merge in vault -> deny
        ok, msg = run_case("D6: git reset --merge in vault", home, "Bash",
                           {"command": "git reset --merge"}, vault, True)
        results.append((ok, msg))

        # D6: git stash pop in vault -> deny
        ok, msg = run_case("D6: git stash pop in vault", home, "Bash",
                           {"command": "git stash pop"}, vault, True)
        results.append((ok, msg))

        # D6: git stash apply in vault -> deny
        ok, msg = run_case("D6: git stash apply in vault", home, "Bash",
                           {"command": "git stash apply"}, vault, True)
        results.append((ok, msg))

        # D6 vault without .git: cherry-pick run inside it -> deny
        ok, msg = run_case("D6 vault without .git: git cherry-pick inside", home, "Bash",
                           {"command": "git cherry-pick HEAD~1"}, plain, True)
        results.append((ok, msg))

        # D6 vault without .git: worktree add --force . run inside it -> deny
        ok, msg = run_case("D6 vault without .git: git worktree add --force .", home, "Bash",
                           {"command": "git worktree add --force . HEAD~1"}, plain, True)
        results.append((ok, msg))

        # D6 witness: git reset --soft HEAD~1 in vault -> allow
        ok, msg = run_case("D6 witness: git reset --soft in vault", home, "Bash",
                           {"command": "git reset --soft HEAD~1"}, vault, False)
        results.append((ok, msg))

        # D6 witness: git stash list in vault -> allow
        ok, msg = run_case("D6 witness: git stash list in vault", home, "Bash",
                           {"command": "git stash list"}, vault, False)
        results.append((ok, msg))

        # D6 witness: git stash drop in vault -> allow
        ok, msg = run_case("D6 witness: git stash drop in vault", home, "Bash",
                           {"command": "git stash drop"}, vault, False)
        results.append((ok, msg))

        # D6 witness: git read-tree without -u/--reset in vault -> allow
        ok, msg = run_case("D6 witness: git read-tree plain in vault", home, "Bash",
                           {"command": "git read-tree HEAD~1"}, vault, False)
        results.append((ok, msg))

        # D6 witness: git worktree add to a folder outside the vault -> allow
        ok, msg = run_case("D6 witness: git worktree add outside vault", home, "Bash",
                           {"command": "git worktree add ../ff_git_wt_outside HEAD"}, vault, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(plain, ignore_errors=True)


def proof_d11_branch_creation():
    """D11: branch creation without a tree change passes in a repo holding a vault;
    pull, merge and rebase stay refused there (maintainer decision)."""
    home = new_home()
    hold = new_project_with_vault()
    vault = new_vault()
    try:
        results = []

        # D11: git switch -c feature in repo holding a vault -> allow
        ok, msg = run_case("D11: git switch -c in repo holding a vault", home, "Bash",
                           {"command": "git switch -c feature"}, hold, False)
        results.append((ok, msg))

        # D11: git switch -C feature -> allow
        ok, msg = run_case("D11: git switch -C in repo holding a vault", home, "Bash",
                           {"command": "git switch -C feature"}, hold, False)
        results.append((ok, msg))

        # D11: git checkout -b feature -> allow
        ok, msg = run_case("D11: git checkout -b in repo holding a vault", home, "Bash",
                           {"command": "git checkout -b feature"}, hold, False)
        results.append((ok, msg))

        # D11: git checkout -B feature -> allow
        ok, msg = run_case("D11: git checkout -B in repo holding a vault", home, "Bash",
                           {"command": "git checkout -B feature"}, hold, False)
        results.append((ok, msg))

        # D11: git branch feature -> allow
        ok, msg = run_case("D11: git branch in repo holding a vault", home, "Bash",
                           {"command": "git branch feature"}, hold, False)
        results.append((ok, msg))

        # D11: git switch -c feature main (start point changes the tree) -> deny
        ok, msg = run_case("D11: git switch -c with start point", home, "Bash",
                           {"command": "git switch -c feature main"}, hold, True)
        results.append((ok, msg))

        # D11: git checkout -b feature main -> deny
        ok, msg = run_case("D11: git checkout -b with start point", home, "Bash",
                           {"command": "git checkout -b feature main"}, hold, True)
        results.append((ok, msg))

        # D11: git switch main (changes the tree) -> deny
        ok, msg = run_case("D11: git switch in repo holding a vault", home, "Bash",
                           {"command": "git switch main"}, hold, True)
        results.append((ok, msg))

        # Maintainer decision: pull, merge, rebase stay refused -> deny
        ok, msg = run_case("D11: git pull in repo holding a vault", home, "Bash",
                           {"command": "git pull"}, hold, True)
        results.append((ok, msg))

        ok, msg = run_case("D11: git merge in repo holding a vault", home, "Bash",
                           {"command": "git merge main"}, hold, True)
        results.append((ok, msg))

        ok, msg = run_case("D11: git rebase in repo holding a vault", home, "Bash",
                           {"command": "git rebase main"}, hold, True)
        results.append((ok, msg))

        # D11: git worktree add aimed at the vault sub-folder -> deny
        ok, msg = run_case("D11: git worktree add aimed at the vault", home, "Bash",
                           {"command": "git worktree add vault HEAD~1"}, hold, True)
        results.append((ok, msg))

        # D11: git worktree add to a folder outside -> allow
        ok, msg = run_case("D11: git worktree add outside the repo", home, "Bash",
                           {"command": "git worktree add ../ff_git_wt_free HEAD"}, hold, False)
        results.append((ok, msg))

        # D11 witness: git switch -c feature inside a vault repo -> allow
        ok, msg = run_case("D11: git switch -c inside a vault repo", home, "Bash",
                           {"command": "git switch -c feature"}, vault, False)
        results.append((ok, msg))

        # D11 witness: git checkout -b feature inside a vault repo -> allow
        ok, msg = run_case("D11: git checkout -b inside a vault repo", home, "Bash",
                           {"command": "git checkout -b feature"}, vault, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(hold, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)


def proof_f2_git_rm():
    """F2: git rm is destructive in, under or above a vault; git rm --cached passes."""
    home = new_home()
    vault = new_vault()
    hold = new_project_with_vault()
    project = new_project()
    try:
        results = []

        # F2: git rm -r . in vault -> deny
        ok, msg = run_case("F2: git rm -r . in vault", home, "Bash",
                           {"command": "git rm -r ."}, vault, True)
        results.append((ok, msg))

        # F2: git rm log.md in vault -> deny
        ok, msg = run_case("F2: git rm log.md in vault", home, "Bash",
                           {"command": "git rm log.md"}, vault, True)
        results.append((ok, msg))

        # F2: git rm -r log.md run under the vault (vault sub-folder) -> deny
        ok, msg = run_case("F2: git rm in vault sub-folder", home, "Bash",
                           {"command": "git rm -r log.md"}, os.path.join(vault, "05-reference"), True)
        results.append((ok, msg))

        # F2: git rm -r vault in a repo holding a vault (above) -> deny
        ok, msg = run_case("F2: git rm -r aimed at the vault", home, "Bash",
                           {"command": "git rm -r vault"}, hold, True)
        results.append((ok, msg))

        # F2: git rm -r . in a repo holding a vault -> deny
        ok, msg = run_case("F2: git rm -r . in repo holding a vault", home, "Bash",
                           {"command": "git rm -r ."}, hold, True)
        results.append((ok, msg))

        # F2 witness: git rm --cached -r . in vault -> allow (working tree untouched)
        ok, msg = run_case("F2 witness: git rm --cached in vault", home, "Bash",
                           {"command": "git rm --cached -r ."}, vault, False)
        results.append((ok, msg))

        # F2 witness: git rm -r . in project (no vault) -> allow
        ok, msg = run_case("F2 witness: git rm -r . in project", home, "Bash",
                           {"command": "git rm -r ."}, project, False)
        results.append((ok, msg))

        # F2 witness: git rm --cached a.txt in project -> allow
        ok, msg = run_case("F2 witness: git rm --cached in project", home, "Bash",
                           {"command": "git rm --cached a.txt"}, project, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)
        shutil.rmtree(hold, ignore_errors=True)
        shutil.rmtree(project, ignore_errors=True)


def proof_i1_eval_and_inline_python():
    """I1: the body of eval, and a shell call made by literal arguments inside
    inline Python, are judged as commands of their own inside a vault."""
    home = new_home()
    vault = new_vault()
    try:
        results = []

        # I1: eval 'git reset --hard' in vault -> deny
        ok, msg = run_case("I1: eval git reset --hard in vault", home, "Bash",
                           {"command": "eval 'git reset --hard'"}, vault, True)
        results.append((ok, msg))

        # I1: python3 -c running subprocess.run(['git','reset','--hard']) in vault -> deny
        ok, msg = run_case("I1: python3 -c subprocess git reset --hard in vault", home, "Bash",
                           {"command": "python3 -c \"import subprocess; subprocess.run(['git','reset','--hard'])\""}, vault, True)
        results.append((ok, msg))

        # I1 witness: eval 'echo hello' -> allow
        ok, msg = run_case("I1 witness: eval echo hello in vault", home, "Bash",
                           {"command": "eval 'echo hello'"}, vault, False)
        results.append((ok, msg))

        # I1 witness: python3 -c "print(1)" -> allow
        ok, msg = run_case("I1 witness: python3 -c print(1) in vault", home, "Bash",
                           {"command": "python3 -c \"print(1)\""}, vault, False)
        results.append((ok, msg))

        # I2 witness: git rm --cached log.md in vault -> allow (index only, tree untouched)
        ok, msg = run_case("I2 witness: git rm --cached log.md in vault", home, "Bash",
                           {"command": "git rm --cached log.md"}, vault, False)
        results.append((ok, msg))

        return results
    finally:
        shutil.rmtree(home, ignore_errors=True)
        shutil.rmtree(vault, ignore_errors=True)


def run_e2e():
    fail_k = 0
    case_num = 0

    for proof_func, label in [
        (proof_c4_git_global_options, "C4 git global options"),
        (proof_c10_same_rule, "C10 same rule"),
        (proof_c19_hooksPath, "C19 core.hooksPath"),
        (proof_d6_destructive_subcommands, "D6 destructive sub-commands"),
        (proof_d11_branch_creation, "D11 branch creation"),
        (proof_f2_git_rm, "F2 git rm"),
        (proof_i1_eval_and_inline_python, "I1 eval and inline Python"),
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