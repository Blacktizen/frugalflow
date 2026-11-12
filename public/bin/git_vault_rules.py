import os
import sys
import tempfile
import subprocess


def _is_bad(val):
    for ch in ("$", "`", "*", "?", "{", "("):
        if ch in val:
            return True
    if "__SUB__" in val:
        return True
    if "<unknown>" in val:
        return True
    return False


def _resolve(val, base):
    if val.startswith("~"):
        return os.path.expanduser(val)
    if os.path.isabs(val):
        return os.path.normpath(val)
    return os.path.normpath(os.path.join(base, val))


def parse_git(args, cwd):
    dir_val = cwd
    worktree_val = None
    configs = []
    sub = []
    dir_invalid = False
    i = 0

    while i < len(args):
        token = args[i]
        if not token.startswith("-"):
            sub = list(args[i:])
            break
        if token == "-C" and i + 1 < len(args):
            val = args[i + 1]
            if _is_bad(val):
                dir_invalid = True
            else:
                dir_val = _resolve(val, dir_val)
            i += 2
        elif token == "-c" and i + 1 < len(args):
            configs.append(args[i + 1])
            i += 2
        elif token == "--work-tree" and i + 1 < len(args):
            val = args[i + 1]
            if _is_bad(val):
                dir_invalid = True
            else:
                worktree_val = _resolve(val, dir_val)
            i += 2
        elif token.startswith("--work-tree="):
            val = token[12:]
            if _is_bad(val):
                dir_invalid = True
            else:
                worktree_val = _resolve(val, dir_val)
            i += 1
        elif token == "--git-dir" and i + 1 < len(args):
            i += 2
        elif token.startswith("--git-dir="):
            i += 1
        elif token == "--namespace" and i + 1 < len(args):
            i += 2
        elif token.startswith("--namespace="):
            i += 1
        else:
            i += 1

    result_dir = None if dir_invalid else dir_val
    return {"dir": result_dir, "worktree": worktree_val, "configs": configs, "sub": sub}


def is_vault_dir(d):
    try:
        has_log = os.path.isfile(os.path.join(d, "log.md"))
        if not has_log:
            return False
        has_schema = os.path.isfile(os.path.join(d, "SCHEMA.md"))
        has_overview = os.path.isfile(os.path.join(d, "overview.md"))
        return has_schema or has_overview
    except Exception:
        return False


def in_vault(d):
    d = os.path.normpath(d)
    while True:
        if is_vault_dir(d):
            return True
        parent = os.path.dirname(d)
        if parent == d:
            return False
        d = parent


def contains_vault(d, is_zone_file):
    if not os.path.isdir(d):
        return False
    try:
        base = os.path.normpath(d)
        base_parts = base.split(os.sep)
        for dirpath, dirnames, filenames in os.walk(d, followlinks=False):
            dirnames[:] = [x for x in dirnames if x != ".git"]
            norm = os.path.normpath(dirpath)
            depth = len(norm.split(os.sep)) - len(base_parts)
            if depth > 3:
                dirnames.clear()
                continue
            if is_vault_dir(dirpath):
                return True
            for fname in filenames:
                if is_zone_file(os.path.join(dirpath, fname)):
                    return True
    except Exception:
        return True
    return False


def _plain_words(words):
    return [w for w in words if not w.startswith("-")]


def _worktree_target(args, base):
    # git worktree add [-f] [-b BRANCH] TARGET [COMMIT]: the first plain word
    # is the target folder, unless -b/-B names a new branch before it.
    plain = _plain_words(args)
    if any(w in ("-b", "-B") for w in args) and plain:
        plain = plain[1:]
    if not plain or plain[0] == "-" or base is None:
        return base
    return _resolve(plain[0], base)


def git_refusals(args, cwd, is_zone_file):
    parsed = parse_git(args, cwd)

    for cfg in parsed["configs"]:
        key_part = cfg.split("=")[0].lower()
        if key_part == "core.hookspath":
            return ["core.hooksPath"]

    sub = parsed["sub"]
    if not sub:
        return []
    subcmd = sub[0]
    rest = sub[1:]

    if subcmd == "config":
        has_hooks = False
        has_get = False
        for word in rest:
            w_low = word.lower()
            if w_low == "core.hookspath" or w_low.startswith("core.hookspath="):
                has_hooks = True
            if word in ("--get", "--get-all", "--get-regexp", "--list", "-l"):
                has_get = True
        if has_hooks and not has_get:
            return ["core.hooksPath"]
        return []

    destructive = False
    judge_dir = None  # worktree add is judged on its target folder
    if subcmd in ("checkout", "restore", "switch", "clean", "pull", "merge", "rebase"):
        # Branch creation that leaves the working tree alone is allowed:
        # checkout -b/-B and switch -c/-C with no other start point.
        if subcmd == "checkout" and any(w in ("-b", "-B") for w in rest) and len(_plain_words(rest)) <= 1:
            destructive = False
        elif subcmd == "switch" and any(w in ("-c", "-C") for w in rest) and len(_plain_words(rest)) <= 1:
            destructive = False
        else:
            destructive = True
    elif subcmd == "reset" and any(w in ("--hard", "--keep", "--merge") for w in rest):
        destructive = True
    elif subcmd == "read-tree" and any(w in ("-u", "--reset") for w in rest):
        destructive = True
    elif subcmd in ("checkout-index", "cherry-pick", "revert", "am"):
        destructive = True
    elif subcmd == "worktree":
        if rest and rest[0] == "add":
            destructive = True
            judge_dir = _worktree_target(rest[1:], parsed["dir"])
    elif subcmd == "stash":
        first_non_dash = None
        for w in rest:
            if not w.startswith("-"):
                first_non_dash = w
                break
        action = first_non_dash if first_non_dash else "push"
        if action not in ("list", "show", "drop"):
            destructive = True
    elif subcmd == "rm" and "--cached" not in rest:
        # 2026-11-12: git rm -r . deleted a vault journal. git rm is destructive in,
        # under or above a vault, except git rm --cached (the working tree stays).
        destructive = True

    if not destructive:
        return []

    if parsed["dir"] is None:
        return ["<unknown>"]

    if judge_dir is not None:
        D = judge_dir
    else:
        D = parsed["worktree"] if parsed["worktree"] is not None else parsed["dir"]
    if in_vault(D) or contains_vault(D, is_zone_file):
        return [D]
    return []


NOTICE = (
    "NAME      git_vault_rules.py - refuses destructive git commands aimed at a vault, and git config core.hooksPath.\n"
    "READS     nothing: pure module; the caller passes the git arguments, the working folder and a zone test.\n"
    "WRITES    nothing: git_refusals() returns the reasons a git command is refused, empty when it is allowed.\n"
    "EXAMPLE   python3 git_vault_rules.py --notice\n"
    "PITFALLS  2026-11-05 git -C DIR checkout restored a vault log.md from a folder the guard did not watch.\n"
    "          2026-11-05 a vault without .git was not protected: the rule now looks at the folders, not at git.\n"
    "          2026-11-12 read-tree -u/--reset, checkout-index, cherry-pick, revert, am, stash pop/apply,\n"
    "          worktree add and reset --keep/--merge rewrote a vault tree while the guard watched nothing.\n"
    "          2026-11-12 switch -c/-C and checkout -b/-B were refused in a repo holding a vault\n"
    "          although they leave the working tree alone; pull, merge and rebase stay refused there.\n"
    "          2026-11-12 git rm -r . deleted a vault journal; git rm is now destructive in, under or\n"
    "          above a vault, except git rm --cached, which leaves the working tree alone.\n"
)


if __name__ == "__main__" and len(sys.argv) > 1 and sys.argv[1] == "--notice":
    sys.stdout.write(NOTICE)
    sys.exit(0)


if __name__ == "__main__" and "--casee" in sys.argv:
    idx = sys.argv.index("--casee")
    n = int(sys.argv[idx + 1])
    vault = os.environ["GVR_VAULT"]
    proj = os.environ["GVR_PROJET"]
    tmp = os.environ["GVR_TMP"]

    def _no_zone(path):
        return False

    ok = True
    label = ""

    if n == 1:
        result = git_refusals(["reset", "--hard"], vault, _no_zone)
        ok = len(result) > 0
        label = "reset in vault"
    elif n == 2:
        result = git_refusals(["-C", vault, "checkout", "--", "log.md"], proj, _no_zone)
        ok = len(result) > 0 and vault in result
        label = "checkout -C vault"
    elif n == 3:
        result = git_refusals(["clean", "-fdx"], os.path.join(vault, "05-reference"), _no_zone)
        ok = len(result) > 0
        label = "clean vault subfolder"
    elif n == 4:
        r1 = git_refusals(["stash"], tmp, _no_zone)
        r2 = git_refusals(["stash", "list"], proj, _no_zone)
        ok = (len(r1) > 0) and (r2 == [])
        label = "stash parent + stash list proj"
    elif n == 5:
        r1 = git_refusals(["config", "core.hooksPath", "/tmp/x"], tmp, _no_zone)
        r2 = git_refusals(["config", "--get", "core.hooksPath"], tmp, _no_zone)
        r3 = git_refusals(["reset", "--hard"], proj, _no_zone)
        r4 = git_refusals(["status"], proj, _no_zone)
        ok = (r1 == ["core.hooksPath"]) and (r2 == []) and (r3 == []) and (r4 == [])
        label = "config hooks safe reset status"
    elif n == 6:
        r1 = git_refusals(["read-tree", "-u", "--reset", "HEAD~1"], vault, _no_zone)
        r2 = git_refusals(["checkout-index", "-a", "-f"], vault, _no_zone)
        r3 = git_refusals(["cherry-pick", "HEAD~1"], vault, _no_zone)
        r4 = git_refusals(["revert", "HEAD~1"], vault, _no_zone)
        r5 = git_refusals(["am", "patch.mbox"], vault, _no_zone)
        r6 = git_refusals(["worktree", "add", "--force", ".", "HEAD~1"], vault, _no_zone)
        r7 = git_refusals(["reset", "--keep", "HEAD~1"], vault, _no_zone)
        r8 = git_refusals(["reset", "--merge"], vault, _no_zone)
        ok = all(len(r) > 0 for r in (r1, r2, r3, r4, r5, r6, r7, r8))
        label = "read-tree checkout-index cherry-pick revert am worktree reset keep merge"
    elif n == 7:
        r1 = git_refusals(["reset", "--soft", "HEAD~1"], vault, _no_zone)
        r2 = git_refusals(["stash", "list"], vault, _no_zone)
        r3 = git_refusals(["stash", "drop"], vault, _no_zone)
        r4 = git_refusals(["switch", "-c", "feature"], vault, _no_zone)
        r5 = git_refusals(["checkout", "-b", "feature"], vault, _no_zone)
        r6 = git_refusals(["branch", "feature"], vault, _no_zone)
        r7 = git_refusals(["worktree", "add", "../outside", "HEAD"], vault, _no_zone)
        r8 = git_refusals(["switch", "-c", "feature", "other"], vault, _no_zone)
        r9 = git_refusals(["checkout", "-b", "feature", "other"], vault, _no_zone)
        ok = (r1 == [] and r2 == [] and r3 == [] and r4 == [] and r5 == []
              and r6 == [] and r7 == [] and len(r8) > 0 and len(r9) > 0)
        label = "soft reset stash list drop branch creation outside worktree"
    elif n == 8:
        r1 = git_refusals(["rm", "-r", "."], vault, _no_zone)
        r2 = git_refusals(["rm", "--cached", "-r", "."], vault, _no_zone)
        r3 = git_refusals(["rm", "-r", "."], tmp, _no_zone)
        r4 = git_refusals(["rm", "-r", "log.md"], os.path.join(vault, "05-reference"), _no_zone)
        r5 = git_refusals(["rm", "-r", "."], proj, _no_zone)
        r6 = git_refusals(["rm", "--cached", "a.txt"], proj, _no_zone)
        ok = (len(r1) > 0 and r2 == [] and len(r3) > 0 and len(r4) > 0
              and r5 == [] and r6 == [])
        label = "git rm vault cached above under outside"

    if ok:
        print(f"PASS {n} {label}")
    else:
        print(f"FAIL {n} {label}")
        sys.exit(1)


if __name__ == "__main__" and "--autotest" in sys.argv:
    tmp = tempfile.mkdtemp(dir="/tmp")
    vault = os.path.join(tmp, "vault")
    proj = os.path.join(tmp, "proj")

    os.makedirs(os.path.join(vault, "05-reference"))
    os.makedirs(os.path.join(proj, "build"))

    with open(os.path.join(vault, "SCHEMA.md"), "w") as f:
        f.write("# Schema\n\nVault d" "e test.\n")
    with open(os.path.join(vault, "log.md"), "w") as f:
        f.write("# Log\n")
    with open(os.path.join(vault, "overview.md"), "w") as f:
        f.write("# Overview")
    with open(os.path.join(vault, "notes.md"), "w") as f:
        f.write("notes")
    with open(os.path.join(vault, "05-reference", "log.md"), "w") as f:
        f.write("# Log\n")
    with open(os.path.join(proj, "a.txt"), "w") as f:
        f.write("a")
    with open(os.path.join(proj, "build", "o.txt"), "w") as f:
        f.write("o")

    ref_file = os.path.abspath(__file__)
    failed = False

    for n in range(1, 9):
        pyc = tempfile.mkdtemp(dir="/tmp")
        env = os.environ.copy()
        env["GVR_VAULT"] = vault
        env["GVR_PROJET"] = proj
        env["GVR_TMP"] = tmp
        env["PYTHONPYCACHEPREFIX"] = pyc
        res = subprocess.run(
            [sys.executable, ref_file, "--casee", str(n)],
            env=env,
        )
        if res.returncode != 0:
            failed = True

    sys.exit(1 if failed else 0)


if __name__ == "__main__" and "--casee" not in sys.argv:
    sys.stdout.write("usage: git_vault_rules.py --notice | --autotest\n")
    sys.exit(2)
