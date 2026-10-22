"""release_check.py - stages the publish tree from the source repo and runs the last checks before a public push."""

import os
import re
import sys
import json
import shutil
import subprocess
import tempfile

USAGE = (
    "usage: release_check.py stage --repo REPO --out DIR | check --tree DIR [--skip-e2e] | "
    "--notice | --autotest"
)

NOTICE = (
    "NAME      release_check.py - stages the publish tree from the source repo and runs the last checks before a public push.\n"
    "READS     stage: the git-tracked files under public/ of the repo given by --repo; check: every file of the tree given by --tree and the check tools that tree holds.\n"
    "WRITES    stage only: the absent or empty folder given by --out, where the tracked files are copied; check writes nothing in the tree given by --tree: the e2e suites run in a temporary copy of the tree that is deleted afterwards, and every subprocess it runs gets a fresh PYTHONPYCACHEPREFIX.\n"
    "EXAMPLE   python3 release_check.py check --tree out --skip-e2e\n"
    "PITFALLS  2026-10-09 a tracked symlink copied into the tree would point back into the source repo: it is refused, never copied.\n"
    "          2026-10-10 the E2E suites ran inside the staged tree and left __pycache__ files that held the home path; they now run in a temporary copy of the tree.\n"
)

MAX_FILE_BYTES = 1000000
ANON_BATCH = 50
E2E_TIMEOUT = 900
ROOT_NAMES = ("README.md", "LICENSE", "CONTRIBUTING.md")


def _run(cmd, cwd=None, timeout=None):
    """Run a command with a fresh PYTHONPYCACHEPREFIX; return (returncode, stdout)."""
    cache = tempfile.mkdtemp(prefix="release_check_pyc_")
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = cache
    try:
        result = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, timeout=timeout)
        return result.returncode, result.stdout
    except subprocess.TimeoutExpired:
        return 124, ""
    finally:
        shutil.rmtree(cache, ignore_errors=True)


def _parse(args, allowed, required, flags=()):
    """Return the option dict, or None when an option is unknown, valueless or required and absent."""
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return None
        name = token[2:]
        if name not in allowed:
            return None
        if name in flags:
            keys[name] = True
            i += 1
        else:
            if i + 1 >= len(args):
                return None
            keys[name] = args[i + 1]
            i += 2
    for name in required:
        if name not in keys:
            return None
    return keys


def _is_git_repo(repo):
    if not os.path.isdir(repo):
        return False
    try:
        result = subprocess.run(["git", "-C", repo, "rev-parse", "--git-dir"],
                                capture_output=True, text=True)
    except OSError:
        return False
    return result.returncode == 0


def _tracked_public(repo):
    """Return the sorted git-tracked paths under public/ in the repo."""
    result = subprocess.run(["git", "-C", repo, "ls-files", "-z", "public"],
                            capture_output=True)
    names = []
    for raw in result.stdout.split(b"\0"):
        if raw:
            names.append(raw.decode("utf-8", "surrogateescape"))
    return sorted(names)


def _dest_of(tree, rel):
    """Where a tracked public/ path lands in the tree: release head files at the root, the rest under public/."""
    if rel.startswith("public/release/"):
        return os.path.join(tree, rel[len("public/release/"):])
    return os.path.join(tree, rel)


def _tree_files(tree):
    """Return every file under the tree, sorted."""
    files = []
    for dirpath, dirnames, filenames in os.walk(tree):
        dirnames.sort()
        for name in sorted(filenames):
            files.append(os.path.join(dirpath, name))
    return files


def _bin_py(tree):
    """Return the sorted public/bin/*.py files of the tree."""
    bin_dir = os.path.join(tree, "public", "bin")
    if not os.path.isdir(bin_dir):
        return []
    return sorted(os.path.join(bin_dir, name) for name in os.listdir(bin_dir) if name.endswith(".py"))


def _cmd_stage(args):
    keys = _parse(args, {"repo", "out"}, {"repo", "out"})
    if keys is None:
        sys.stdout.write(USAGE + "\n")
        return 2
    repo = keys["repo"]
    out = keys["out"]
    if not _is_git_repo(repo):
        sys.stdout.write("REFUSED not a git repository: " + repo + "\n")
        return 1
    if os.path.exists(out):
        if not (os.path.isdir(out) and os.listdir(out) == []):
            sys.stdout.write("REFUSED output folder not empty: " + out + "\n")
            return 1
    tracked = _tracked_public(repo)
    for rel in tracked:
        if os.path.islink(os.path.join(repo, rel)):
            sys.stdout.write("REFUSED symlink in public: " + rel + "\n")
            return 1
    os.makedirs(out, exist_ok=True)
    for rel in tracked:
        dest = _dest_of(out, rel)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        shutil.copy2(os.path.join(repo, rel), dest)
    sys.stdout.write("STAGED %d files in %s\n" % (len(tracked), out))
    return 0


def _check_root_files(tree):
    problems = []
    for name in ROOT_NAMES:
        path = os.path.join(tree, name)
        if not os.path.isfile(path):
            problems.append("missing " + name)
        elif os.path.getsize(path) == 0:
            problems.append("empty " + name)
    if problems:
        return False, ", ".join(problems)
    return True, str(len(ROOT_NAMES)) + " files"


def _check_no_git(tree):
    problems = []
    for dirpath, dirnames, filenames in os.walk(tree):
        for name in dirnames + filenames:
            full = os.path.join(dirpath, name)
            if name == ".git":
                problems.append(os.path.relpath(full, tree))
            elif os.path.islink(full):
                problems.append("symlink " + os.path.relpath(full, tree))
    if problems:
        return False, ", ".join(sorted(problems))
    return True, "no .git, no symlink"


def _check_size(tree, files):
    over = []
    biggest = 0
    for path in files:
        try:
            size = os.path.getsize(path)
        except OSError:
            continue
        if size > biggest:
            biggest = size
        if size > MAX_FILE_BYTES:
            over.append(os.path.relpath(path, tree) + " (" + str(size) + " bytes)")
    if over:
        return False, "over " + str(MAX_FILE_BYTES) + " bytes: " + ", ".join(over)
    return True, "max " + str(biggest) + " bytes"


def _check_anon(tree, files):
    tool = os.path.join(tree, "public", "bin", "anon_check.py")
    home = os.environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow")
    rules_args = []
    if not os.path.isfile(os.path.join(home, "anonymization.json")):
        # No personal pattern file yet: scan with the example patterns shipped in the tree (generic leaks are always checked).
        rules_args = ["--rules", os.path.join(tree, "public", "config", "anonymization.example.json")]
    batches = [files[i:i + ANON_BATCH] for i in range(0, len(files), ANON_BATCH)]
    refused = 0
    for batch in batches:
        # A timeout keeps a pathological file from hanging the gate; a timed out batch counts as refused.
        rc, _ = _run([sys.executable, tool] + rules_args + ["--scan"] + batch, timeout=300)
        if rc != 0:
            refused += 1
    detail = str(len(batches)) + " batches, " + str(refused) + " refused"
    return refused == 0, detail


def _check_lang(tree):
    tool = os.path.join(tree, "public", "bin", "lang_check.py")
    words = os.path.join(tree, "public", "config", "lang_words.json")
    # The skip list in lang_words.json is written against the public subtree, so the root passed is that subtree.
    rc, out = _run([sys.executable, tool, "--root", os.path.join(tree, "public"), "--words", words])
    lines = [line for line in out.splitlines() if line.strip()]
    detail = lines[-1] if lines else "exit " + str(rc)
    return rc == 0, detail


def _check_notice(tree):
    tool = os.path.join(tree, "public", "bin", "notice_check.py")
    refused = []
    for path in _bin_py(tree):
        rc, _ = _run([sys.executable, tool, path])
        if rc != 0:
            refused.append(os.path.basename(path))
    if refused:
        return False, "refused: " + ", ".join(refused)
    return True, str(len(_bin_py(tree))) + " tools ok"


def _check_e2e(tree, skip_e2e):
    if skip_e2e:
        return True, "skipped"
    tests_dir = os.path.join(tree, "public", "tests")
    if not os.path.isdir(tests_dir):
        return True, "0 suites"
    names = sorted(name for name in os.listdir(tests_dir) if name.startswith("e2e_") and name.endswith(".py"))
    # The suites run in a throwaway copy of the tree: whatever a suite or its own subprocesses write
    # lands in the copy, never in the tree, and the copy is deleted even on failure or timeout.
    copy_root = None
    try:
        copy_root = tempfile.mkdtemp(prefix="release_check_e2e_")
        copy_tree = os.path.join(copy_root, "tree")
        shutil.copytree(tree, copy_tree, symlinks=True)
    except OSError as exc:
        if copy_root is not None:
            shutil.rmtree(copy_root, ignore_errors=True)
        return False, "cannot copy the tree: " + str(exc)
    failed = []
    try:
        for name in names:
            suite = os.path.join(copy_tree, "public", "tests", name)
            rc, _ = _run([sys.executable, suite], cwd=copy_tree, timeout=E2E_TIMEOUT)
            if rc != 0:
                failed.append(name)
    finally:
        shutil.rmtree(copy_root, ignore_errors=True)
    if failed:
        return False, "failed: " + ", ".join(failed)
    return True, str(len(names)) + " suites ok"


def _cmd_check(args):
    keys = _parse(args, {"tree", "skip-e2e"}, {"tree"}, flags=("skip-e2e",))
    if keys is None:
        sys.stdout.write(USAGE + "\n")
        return 2
    tree = keys["tree"]
    if not os.path.isdir(tree):
        sys.stdout.write("REFUSED no tree: " + tree + "\n")
        return 1
    skip_e2e = keys.get("skip-e2e", False)
    files = _tree_files(tree)
    results = [
        ("root-files",) + _check_root_files(tree),
        ("no-git",) + _check_no_git(tree),
        ("size",) + _check_size(tree, files),
        ("anon",) + _check_anon(tree, files),
        ("lang",) + _check_lang(tree),
        ("notice",) + _check_notice(tree),
        ("e2e",) + _check_e2e(tree, skip_e2e),
    ]
    failed = 0
    for name, ok, detail in results:
        sys.stdout.write(("PASS " if ok else "FAIL ") + name + " " + detail + "\n")
        if not ok:
            failed += 1
    if failed == 0:
        sys.stdout.write("RELEASE READY\n")
        return 0
    sys.stdout.write("RELEASE NOT READY " + str(failed) + " failed\n")
    return 1


FIXTURE_FILES = {
    "public/release/README.md": "# Demo\n",
    "public/release/LICENSE": "MIT\n",
    "public/release/CONTRIBUTING.md": "How to help\n",
    "public/bin/hello.py": "print('hi')\n",
    "public/config/a.json": "{}\n",
}

GOOD_BASE = {
    "public/release/README.md": "# Demo\n",
    "public/release/LICENSE": "MIT\n",
    "public/release/CONTRIBUTING.md": "How to help\n",
    "public/config/lang_words.json": '{"french": ["bonjour"], "allowed": [], "skip": []}\n',
}

CHECK_TOOLS = ("anon_check.py", "lang_check.py", "notice_check.py")


def _tool_closure(bin_dir):
    """The three check tools plus every module they import from the same folder, transitively."""
    available = set(name for name in os.listdir(bin_dir) if name.endswith(".py"))
    seen = set()
    pending = list(CHECK_TOOLS)
    while pending:
        name = pending.pop()
        if name in seen:
            continue
        seen.add(name)
        with open(os.path.join(bin_dir, name), "r", encoding="utf-8") as f:
            text = f.read()
        for match in re.finditer(r"^\s*(?:from|import)\s+([A-Za-z_][A-Za-z0-9_]*)", text, re.M):
            dep = match.group(1) + ".py"
            if dep in available and dep not in seen:
                pending.append(dep)
    return sorted(seen)


def _good_files(bin_dir):
    """Files of a complete publish tree: the release head plus copies of the check tools and their modules."""
    files = dict(GOOD_BASE)
    names = _tool_closure(bin_dir)
    for name in names:
        with open(os.path.join(bin_dir, name), "r", encoding="utf-8") as f:
            files["public/bin/" + name] = f.read()
    # anon_rules.py opens the betterleaks rules from the data folder next to bin at import time.
    with open(os.path.join(os.path.dirname(bin_dir), "data", "betterleaks_rules.json"), "r", encoding="utf-8") as f:
        files["public/data/betterleaks_rules.json"] = f.read()
    return files


def _git_free_env():
    """os.environ copied with every GIT_* variable removed: a hook environment must not redirect git."""
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    return env


def _make_repo(path, files):
    """Create a committed git repo holding the given files."""
    os.makedirs(path)
    for rel, text in files.items():
        full = os.path.join(path, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(text)
    git = ["git", "-C", path]
    env = _git_free_env()
    subprocess.run(git + ["init", "-q"], check=True, env=env)
    subprocess.run(git + ["add", "-A"], check=True, env=env)
    subprocess.run(git + ["-c", "user.email=autotest", "-c", "user.name=autotest",
                          "-c", "commit.gpgsign=false", "commit", "-q", "-m", "fixture"], check=True, env=env)


def _autotest():
    self_path = os.path.abspath(__file__)

    failures = 0
    lines = []

    def record(number, ok, expected, obtained):
        nonlocal failures
        status = "PASS" if ok else "FAIL"
        lines.append("%s %d: expected %s | got %s" % (status, number, expected, obtained))
        if not ok:
            failures += 1

    def fail_names(stdout):
        return [line.split()[1] for line in stdout.splitlines() if line.startswith("FAIL ")]

    def last_line(stdout):
        out_lines = [line for line in stdout.splitlines() if line.strip()]
        return out_lines[-1] if out_lines else ""

    with tempfile.TemporaryDirectory() as tmp:
        # The autotest is hermetic: every tool run gets this fixture home as FRUGALFLOW_HOME, so no
        # check ever reads the real environment rules, and no GIT_* variable can reach a subprocess.
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        with open(os.path.join(home, "anonymization.json"), "w", encoding="utf-8") as f:
            f.write('{"anonymizable": [], "irreducible": [{"pattern": "zzleakword", "label": "autotest leak"}]}\n')

        def run(args):
            env = _git_free_env()
            env["FRUGALFLOW_HOME"] = home
            cache = tempfile.mkdtemp(prefix="release_check_autotest_pyc_")
            env["PYTHONPYCACHEPREFIX"] = cache
            try:
                return subprocess.run([sys.executable, self_path] + args, capture_output=True, text=True, env=env)
            finally:
                shutil.rmtree(cache, ignore_errors=True)

        repo_r = os.path.join(tmp, "repo_r")
        _make_repo(repo_r, FIXTURE_FILES)
        scratch = os.path.join(repo_r, "public", "bin", "scratch.py")
        with open(scratch, "w", encoding="utf-8") as f:
            f.write("print('untracked')\n")

        # Test 1: stage the fixture repo: rc 0, STAGED 5 files, exact places, nothing untracked, no .git
        t1 = os.path.join(tmp, "tree1")
        r = run(["stage", "--repo", repo_r, "--out", t1])
        ok1 = r.returncode == 0 and r.stdout.strip() == "STAGED 5 files in " + t1
        for rel in ("README.md", "LICENSE", "CONTRIBUTING.md", "public/bin/hello.py", "public/config/a.json"):
            ok1 = ok1 and os.path.isfile(os.path.join(t1, rel))
        ok1 = (ok1 and not os.path.exists(os.path.join(t1, "public", "release"))
               and not os.path.exists(os.path.join(t1, "public", "bin", "scratch.py"))
               and not os.path.exists(os.path.join(t1, ".git")))
        record(1, ok1, "rc=0 STAGED 5 files, the five places, no scratch.py, no release folder, no .git",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 2: stage onto a non-empty folder refuses rc 1
        r = run(["stage", "--repo", repo_r, "--out", t1])
        record(2, r.returncode == 1 and r.stdout.startswith("REFUSED output folder not empty: "),
               "rc=1 REFUSED output folder not empty", "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 3: stage from a folder without git refuses rc 1
        plain = os.path.join(tmp, "plain")
        os.makedirs(plain)
        r = run(["stage", "--repo", plain, "--out", os.path.join(tmp, "tree_plain")])
        record(3, r.returncode == 1 and r.stdout.startswith("REFUSED not a git repository: "),
               "rc=1 REFUSED not a git repository", "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 4: unknown option, missing required option and missing value all exit 2 with USAGE
        r_unknown = run(["--unknown-option"])
        r_missing = run(["stage", "--repo", repo_r])
        r_valueless = run(["stage", "--repo"])
        ok4 = (r_unknown.returncode == 2 and r_unknown.stdout.startswith("usage: release_check.py")
               and r_missing.returncode == 2 and r_missing.stdout.startswith("usage: release_check.py")
               and r_valueless.returncode == 2 and r_valueless.stdout.startswith("usage: release_check.py"))
        record(4, ok4, "rc=2 USAGE for an unknown option, a missing required option and a missing value",
               "rc_unknown=" + str(r_unknown.returncode) + " rc_missing=" + str(r_missing.returncode)
               + " rc_valueless=" + str(r_valueless.returncode))

        # Test 5: a tracked symlink refuses rc 1 and nothing is staged
        repo_s = os.path.join(tmp, "repo_s")
        _make_repo(repo_s, FIXTURE_FILES)
        os.symlink("hello.py", os.path.join(repo_s, "public", "bin", "link.py"))
        git_env = _git_free_env()
        subprocess.run(["git", "-C", repo_s, "add", "-A"], check=True, env=git_env)
        subprocess.run(["git", "-C", repo_s, "-c", "user.email=autotest",
                        "-c", "user.name=autotest", "-c", "commit.gpgsign=false",
                        "commit", "-q", "-m", "symlink"], check=True, env=git_env)
        tree_s = os.path.join(tmp, "tree_s")
        r = run(["stage", "--repo", repo_s, "--out", tree_s])
        ok5 = (r.returncode == 1 and r.stdout.strip() == "REFUSED symlink in public: public/bin/link.py"
               and not os.path.exists(tree_s))
        record(5, ok5, "rc=1 REFUSED symlink in public: public/bin/link.py and no tree written",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " written=" + str(os.path.exists(tree_s)))

        # Test 6: check on an absent tree refuses rc 1
        absent = os.path.join(tmp, "absent_tree")
        r = run(["check", "--tree", absent])
        record(6, r.returncode == 1 and r.stdout.strip() == "REFUSED no tree: " + absent,
               "rc=1 REFUSED no tree: " + absent, "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 7: a fixture tree holding a leak file fails anon only, rc 1
        repo_a = os.path.join(tmp, "repo_a")
        leak_files = dict(_good_files(os.path.dirname(self_path)))
        leak_files["public/docs/leak.md"] = "zzleakword\n"
        _make_repo(repo_a, leak_files)
        t3 = os.path.join(tmp, "tree_leak")
        r_stage = run(["stage", "--repo", repo_a, "--out", t3])
        r = run(["check", "--tree", t3, "--skip-e2e"])
        names = fail_names(r.stdout)
        ok7 = (r_stage.returncode == 0 and r.returncode == 1 and names == ["anon"]
               and last_line(r.stdout) == "RELEASE NOT READY 1 failed")
        record(7, ok7, "rc=1, fail anon only, RELEASE NOT READY 1 failed",
               "rc_stage=" + str(r_stage.returncode) + " rc=" + str(r.returncode)
               + " fails=" + repr(names) + " last=" + repr(last_line(r.stdout)))

        # Test 8: a complete clean tree gives RELEASE READY, rc 0
        repo_g = os.path.join(tmp, "repo_g")
        _make_repo(repo_g, _good_files(os.path.dirname(self_path)))
        t4 = os.path.join(tmp, "tree_good")
        run(["stage", "--repo", repo_g, "--out", t4])
        r = run(["check", "--tree", t4, "--skip-e2e"])
        ok8 = r.returncode == 0 and fail_names(r.stdout) == [] and last_line(r.stdout) == "RELEASE READY"
        record(8, ok8, "rc=0 all PASS and RELEASE READY",
               "rc=" + str(r.returncode) + " fails=" + repr(fail_names(r.stdout))
               + " last=" + repr(last_line(r.stdout)))

        # Test 9: an emptied LICENSE fails root-files only, rc 1
        t5 = os.path.join(tmp, "tree_no_license")
        shutil.copytree(t4, t5)
        with open(os.path.join(t5, "LICENSE"), "w", encoding="utf-8") as f:
            f.write("")
        r = run(["check", "--tree", t5, "--skip-e2e"])
        ok9 = (r.returncode == 1 and fail_names(r.stdout) == ["root-files"]
               and last_line(r.stdout) == "RELEASE NOT READY 1 failed")
        record(9, ok9, "rc=1 fail root-files only, RELEASE NOT READY 1 failed",
               "rc=" + str(r.returncode) + " fails=" + repr(fail_names(r.stdout))
               + " last=" + repr(last_line(r.stdout)))

        # Test 10: a 1200000-byte file fails size only, rc 1
        t6 = os.path.join(tmp, "tree_big")
        shutil.copytree(t4, t6)
        with open(os.path.join(t6, "public", "big.bin"), "wb") as f:
            f.write(b"\x00" * 1200000)
        r = run(["check", "--tree", t6, "--skip-e2e"])
        ok10 = (r.returncode == 1 and fail_names(r.stdout) == ["size"]
                and last_line(r.stdout) == "RELEASE NOT READY 1 failed")
        record(10, ok10, "rc=1 fail size only, RELEASE NOT READY 1 failed",
               "rc=" + str(r.returncode) + " fails=" + repr(fail_names(r.stdout))
               + " last=" + repr(last_line(r.stdout)))

        # Test 11: an empty .git folder fails no-git only, rc 1
        t7 = os.path.join(tmp, "tree_dotgit")
        shutil.copytree(t4, t7)
        os.mkdir(os.path.join(t7, ".git"))
        r = run(["check", "--tree", t7, "--skip-e2e"])
        ok11 = (r.returncode == 1 and fail_names(r.stdout) == ["no-git"]
                and last_line(r.stdout) == "RELEASE NOT READY 1 failed")
        record(11, ok11, "rc=1 fail no-git only, RELEASE NOT READY 1 failed",
               "rc=" + str(r.returncode) + " fails=" + repr(fail_names(r.stdout))
               + " last=" + repr(last_line(r.stdout)))

        # Test 12: a tool without a notice fails notice only, rc 1
        t8 = os.path.join(tmp, "tree_new_tool")
        shutil.copytree(t4, t8)
        with open(os.path.join(t8, "public", "bin", "zz_new.py"), "w", encoding="utf-8") as f:
            f.write("print('x')\n")
        r = run(["check", "--tree", t8, "--skip-e2e"])
        ok12 = (r.returncode == 1 and fail_names(r.stdout) == ["notice"]
                and last_line(r.stdout) == "RELEASE NOT READY 1 failed")
        record(12, ok12, "rc=1 fail notice only, RELEASE NOT READY 1 failed",
               "rc=" + str(r.returncode) + " fails=" + repr(fail_names(r.stdout))
               + " last=" + repr(last_line(r.stdout)))

        # Test 13: --notice exits 0, starts with the NAME line and carries both dated pitfalls
        r = run(["--notice"])
        ok13 = (r.returncode == 0 and r.stdout.startswith("NAME      release_check.py")
                and "PITFALLS  2026-10-09" in r.stdout
                and "2026-10-10 the E2E suites ran inside the staged tree and left __pycache__ files that held the home path; they now run in a temporary copy of the tree." in r.stdout)
        record(13, ok13, "rc=0 notice with the NAME line, the PITFALLS 2026-10-09 line and the 2026-10-10 pitfall",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout[:60]))

        # Test 14: a planted suite runs in a temporary copy of the tree, never in the tree itself
        t9 = os.path.join(tmp, "tree_planted")
        shutil.copytree(t4, t9)
        planted_dir = os.path.join(t9, "public", "tests")
        os.makedirs(planted_dir)
        with open(os.path.join(planted_dir, "e2e_zz_planted.py"), "w", encoding="utf-8") as f:
            f.write("import os\nopen(os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'zz_planted.txt'), 'w').write('x')\n")
        r = run(["check", "--tree", t9])
        e2e_lines = [line for line in r.stdout.splitlines() if line.startswith("PASS e2e ")]
        planted = os.path.exists(os.path.join(t9, "public", "zz_planted.txt"))
        ok14 = (r.returncode == 0 and e2e_lines and e2e_lines[0].startswith("PASS e2e 1 suites ok")
                and not planted)
        record(14, ok14, "rc=0, PASS e2e 1 suites ok, no public/zz_planted.txt in the tree",
               "rc=" + str(r.returncode) + " e2e=" + repr(e2e_lines[0] if e2e_lines else "")
               + " planted=" + str(planted))

    for line in lines:
        sys.stdout.write(line + "\n")
    return 1 if failures else 0


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    if argv and argv[0] == "stage":
        return _cmd_stage(argv[1:])
    if argv and argv[0] == "check":
        return _cmd_check(argv[1:])
    sys.stdout.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "release_check", sys.argv[1:])
