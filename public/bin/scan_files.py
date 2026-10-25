import os
import subprocess
import sys
import tempfile
import shutil

NOTICE = (
    "NAME      scan_files.py - lists the text files of a folder or a git repo "
    "that the leak scanner should read.\n"
    "READS     the path given; runs git read-only commands (ls-files, diff "
    "--cached, rev-parse); reads the first 8192 bytes of each file.\n"
    "WRITES    nothing: list_files returns a sorted list of absolute paths.\n"
    "EXAMPLE   python3 scan_files.py --autotest\n"
    "PITFALLS  2026-10-25 files listed by git but deleted from the disk "
    "crashed the scan; they are now skipped.\n"
    "          2026-10-25 a GIT_ variable inherited from a commit hook "
    "pointed git at the wrong repo; every git call now runs without them."
)

_IGNORED_DIRS = frozenset({".git", "node_modules", "__pycache__", ".venv", "venv"})
_MAX_SIZE = 1_000_000
_NUL_CHECK = 8192


def _clean_env():
    env = os.environ.copy()
    for key in list(env):
        if key.startswith("GIT_"):
            del env[key]
    return env


def _run_git(args, cwd=None):
    return subprocess.run(
        args,
        cwd=cwd,
        capture_output=True,
        env=_clean_env(),
        timeout=60,
    )


def _passes_filter(filepath):
    if not os.path.isfile(filepath):
        return False
    try:
        if os.path.getsize(filepath) > _MAX_SIZE:
            return False
        with open(filepath, "rb") as fh:
            chunk = fh.read(_NUL_CHECK)
    except OSError:
        return False
    if b"\x00" in chunk:
        return False
    return True


def _is_in_git_repo(path):
    try:
        proc = _run_git(
            ["git", "-C", path, "rev-parse", "--is-inside-work-tree"]
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    if proc.stdout.strip() != b"true":
        return None
    return True


def _git_ls_files(path):
    try:
        proc = _run_git(
            ["git", "-C", path, "ls-files", "-z",
             "--cached", "--others", "--exclude-standard"]
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    raw = proc.stdout.split(b"\x00")
    candidates = []
    for item in raw:
        if not item:
            continue
        rel = item.decode("utf-8", errors="surrogateescape")
        abs_path = os.path.join(path, rel)
        candidates.append(abs_path)
    return candidates


def _os_walk(path):
    candidates = []
    for dirpath, dirnames, filenames in os.walk(path):
        dirnames[:] = [d for d in dirnames if d not in _IGNORED_DIRS]
        for fname in filenames:
            candidates.append(os.path.join(dirpath, fname))
    return candidates


def _git_staged_files(path):
    try:
        proc = _run_git(
            ["git", "-C", path, "rev-parse", "--show-toplevel"]
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip().decode("utf-8", errors="surrogateescape")
    if not root:
        return None
    try:
        proc = _run_git(
            ["git", "-C", path, "diff", "--cached",
             "--name-only", "--diff-filter=ACMR", "-z"]
        )
    except FileNotFoundError:
        return None
    if proc.returncode != 0:
        return None
    raw = proc.stdout.split(b"\x00")
    candidates = []
    for item in raw:
        if not item:
            continue
        rel = item.decode("utf-8", errors="surrogateescape")
        abs_path = os.path.join(root, rel)
        candidates.append(abs_path)
    return candidates


def list_files(path, staged=False):
    if not os.path.exists(path):
        raise ValueError("not found: " + path)

    if os.path.isfile(path):
        if _passes_filter(path):
            return [os.path.abspath(path)]
        return []

    abs_path = os.path.abspath(path)

    if staged:
        git_ok = _is_in_git_repo(abs_path)
        if git_ok is None:
            raise ValueError("not a git repository: " + path)
        candidates = _git_staged_files(abs_path)
        if candidates is None:
            raise ValueError("not a git repository: " + path)
    else:
        candidates = _git_ls_files(abs_path)
        if candidates is None:
            candidates = _os_walk(abs_path)

    results = []
    for c in candidates:
        if _passes_filter(c):
            results.append(os.path.abspath(c))

    results.sort()
    return results


def _rel(target, base):
    return os.path.relpath(
        os.path.realpath(target),os.path.realpath(base)
    ).replace(os.sep, "/")


def _autotest():
    passed = 0
    tmpdir = tempfile.mkdtemp()
    try:
        walk_dir = os.path.join(tmpdir, "WALK")
        os.makedirs(os.path.join(walk_dir, "sub"))
        os.makedirs(os.path.join(walk_dir, ".git"))
        os.makedirs(os.path.join(walk_dir, "node_modules"))

        WALK_FILES = {
            "a.txt": "hello\n",
            "sub/b.py": "x = 1\n",
            ".git/inner.txt": "hidden\n",
            "node_modules/m.js": "var m;\n",
            "big.txt": "a" * 1500000,
            "bin.dat": "ab\0cd",
        }
        WALK_EXPECTED = ["a.txt", "sub/b.py"]

        for rel, content in WALK_FILES.items():
            fp = os.path.join(walk_dir, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)

        git_dir = os.path.join(tmpdir, "GIT")
        os.makedirs(git_dir)
        GIT_FILES = {
            "kept.txt": "kept\n",
            "new.txt": "new\n",
            "skip.log": "skipped\n",
            ".gitignore": "*.log\n",
        }
        GIT_EXPECTED = [".gitignore", "kept.txt", "new.txt"]

        for rel, content in GIT_FILES.items():
            fp = os.path.join(git_dir, rel)
            os.makedirs(os.path.dirname(fp), exist_ok=True)
            with open(fp, "w", encoding="utf-8", newline="") as fh:
                fh.write(content)

        env_clean = _clean_env()
        git_available = True
        try:
            subprocess.run(
                ["git", "init", "-q"], cwd=git_dir,
                capture_output=True, env=env_clean, timeout=60,
            )
            subprocess.run(
                ["git", "add", "kept.txt"], cwd=git_dir,
                capture_output=True, env=env_clean, timeout=60,
            )
        except FileNotFoundError:
            git_available = False

        # test1
        try:
            got = list_files(walk_dir)
            got_rel = sorted(_rel(p, walk_dir) for p in got)
            if got_rel == WALK_EXPECTED:
                print("PASS 1 expected=%s got=%s" % (WALK_EXPECTED, got_rel))
                passed += 1
            else:
                print("FAIL 1 expected=%s got=%s" % (WALK_EXPECTED, got_rel))
        except Exception as exc:
            print("FAIL 1 expected=%s got=%s" % (WALK_EXPECTED, exc))

        # test2
        a_abs = os.path.abspath(os.path.join(walk_dir, "a.txt"))
        try:
            r1 = list_files(os.path.join(walk_dir, "a.txt"))
            r2 = list_files(os.path.join(walk_dir, "bin.dat"))
            if r1 == [a_abs] and r2 == []:
                print("PASS 2 expected=[a.txt_abs, []] got=[%s, %s]" % (r1, r2))
                passed += 1
            else:
                print("FAIL 2 expected=[a.txt_abs, []] got=[%s, %s]" % (r1, r2))
        except Exception as exc:
            print("FAIL 2 expected=[a.txt_abs, []] got=%s" % exc)

        # test3
        if not git_available:
            print("PASS 3 skipped: git not found")
            passed += 1
        else:
            try:
                got = list_files(git_dir)
                got_rel = sorted(_rel(p, git_dir) for p in got)
                if got_rel == GIT_EXPECTED:
                    print("PASS 3 expected=%s got=%s" % (GIT_EXPECTED, got_rel))
                    passed += 1
                else:
                    print("FAIL 3 expected=%s got=%s" % (GIT_EXPECTED, got_rel))
            except Exception as exc:
                print("FAIL 3 expected=%s got=%s" % (GIT_EXPECTED, exc))

        # test4
        if not git_available:
            print("PASS 4 skipped: git not found")
            passed += 1
        else:
            try:
                got = list_files(git_dir, staged=True)
                got_rel = sorted(_rel(p, git_dir) for p in got)
                ok_staged = got_rel == ["kept.txt"]
                ok_error = False
                try:
                    list_files(walk_dir, staged=True)
                except ValueError as ve:
                    if str(ve).startswith("not a git repository: "):
                        ok_error = True
                if ok_staged and ok_error:
                    print("PASS 4 expected=['kept.txt'] + not a git repository: ")
                    passed += 1
                else:
                    print("FAIL 4 expected=['kept.txt'] + not a git repository: ")
            except Exception as exc:
                print("FAIL 4 expected=['kept.txt'] + not a git repository: %s" % exc)

        # test5
        ok_absent = False
        try:
            list_files(os.path.join(walk_dir, "absent"))
        except ValueError as ve:
            if str(ve).startswith("not found: "):
                ok_absent = True

        exit_code_ok = False
        try:
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__)],
                capture_output=True, env=env_clean, timeout=60,
            )
            if proc.returncode == 2:
                exit_code_ok = True
        except Exception:
            pass

        if ok_absent and exit_code_ok:
            print("PASS 5 expected not found + exit 2")
            passed += 1
        else:
            print("FAIL 5 expected not found + exit 2")

        print("AUTOTEST %d/5" % passed)
        return 0 if passed == 5 else 1
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


def main():
    if "--autotest" in sys.argv:
        sys.exit(_autotest())
    elif "--notice" in sys.argv:
        print(NOTICE)
        sys.exit(0)
    else:
        print("usage: scan_files.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    main()
