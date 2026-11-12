"""End-to-end tests for public/bin/verify_worktree.py."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

NOTICE = "\n".join([
    "NAME      e2e_verify_worktree.py - end-to-end tests for verify_worktree.py",
    "READS     the verify_worktree module from --root/public/bin",
    "WRITES    temporary directories under /tmp, cleaned up after each test",
    "EXAMPLE   python3 e2e_verify_worktree.py --root /path/to/repo",
    "PITFALLS  tests run verify_worktree as a subprocess; --root must point to a valid repo",
])


def parse_args():
    p = argparse.ArgumentParser(add_help=False)
    default_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    p.add_argument("--root", default=default_root, help="repository root (default: the repo this file sits in)")
    p.add_argument("--notice", action="store_true", help="print notice and exit")
    return p.parse_known_args()[0]


def run_verify_worktree(root, args, cwd=None, env=None):
    """Run verify_worktree.py from <root>/public/bin as a subprocess."""
    script = os.path.join(root, "public", "bin", "verify_worktree.py")
    if not os.path.isfile(script):
        raise FileNotFoundError(f"verify_worktree.py not found at {script}")
    cmd = [sys.executable, "-B", script] + args
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def import_from_root(root):
    """Import verify_worktree functions by adding <root>/public/bin to sys.path."""
    bin_dir = os.path.join(root, "public", "bin")
    sys.path.insert(0, bin_dir)
    import verify_worktree
    return verify_worktree


def test_same_size_restored_mtime(root):
    """Case 1: same size, date restored -> changed() should detect via SHA-256."""
    vw = import_from_root(root)
    tmp = tempfile.mkdtemp(prefix="e2e_test1_")
    try:
        test_file = os.path.join(tmp, "a.txt")
        # Write initial content
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("AAAA")
        # Snapshot before
        before = vw.snapshot(tmp)
        # Rewrite with same size, restore mtime
        stat_before = os.stat(test_file)
        with open(test_file, "w", encoding="utf-8") as f:
            f.write("BBBB")
        os.utime(test_file, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))
        # Snapshot after
        after = vw.snapshot(tmp)
        diff = vw.changed(before, after)
        expected = ["a.txt"]
        if diff == expected:
            return True, f"changed()={diff}"
        return False, f"expected changed()={expected}, got {diff}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_max_watch_threshold(root):
    """Case 2: 7 files, max_watch=5 -> run_in_worktree refuses (126, REFUSED), marker not created."""
    vw = import_from_root(root)
    tmp = tempfile.mkdtemp(prefix="e2e_test2_")
    try:
        # Create 7 files
        for i in range(7):
            with open(os.path.join(tmp, f"f{i}.txt"), "w") as f:
                f.write("x")
        # Candidate file
        cand = os.path.join(tmp, "cand.py")
        with open(cand, "w") as f:
            f.write("pass\n")
        out = os.path.join(tmp, "out.py")
        # Marker outside watched dir but in same tmp
        marker = os.path.join(tmp, "marker.txt")
        # Command that would create marker if executed
        cmd = f'touch "{marker}"'
        # Call run_in_worktree with max_watch=5
        # If max_watch param doesn't exist, TypeError is raised -> test FAILS (not crash)
        try:
            code, output = vw.run_in_worktree(cmd, cand, out, tmp, 5, max_watch=5)
        except TypeError:
            return False, "run_in_worktree missing max_watch parameter (TypeError)"
        marker_exists = os.path.exists(marker)
        if code == 126 and "REFUSED" in output and not marker_exists:
            return True, f"code=126 REFUSED marker_absent"
        return False, f"expected code=126 with REFUSED and no marker, got code={code} output={output!r} marker_exists={marker_exists}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_watch_limit_exceeded_after_check(root):
    """Case 3: first snapshot fits, the check adds files past the watch limit
    -> run_in_worktree refuses like a detected write (125, exact message)."""
    vw = import_from_root(root)
    tmp = tempfile.mkdtemp(prefix="e2e_test3_")
    try:
        for i in range(3):
            with open(os.path.join(tmp, f"f{i}.txt"), "w") as f:
                f.write("x")
        cand = os.path.join(tmp, "cand.py")
        with open(cand, "w") as f:
            f.write("pass\n")
        cmd = 'touch "%s/n1.txt" "%s/n2.txt"' % (tmp, tmp)
        code, output = vw.run_in_worktree(cmd, cand, cand, tmp, 30, max_watch=5)
        expected = (125, "VERIFY WROTE TO THE PROJECT: the file count went over the watch limit")
        if (code, output) == expected:
            return True, f"code={code} output={output!r}"
        return False, f"expected {expected!r}, got code={code} output={output!r}"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def test_git_config_and_hooks_watched(root):
    """Case 4: .git is no longer fully skipped: .git/config and every file
    under .git/hooks/ are watched; other .git contents stay unwatched."""
    vw = import_from_root(root)
    tmp = tempfile.mkdtemp(prefix="e2e_test4_")
    try:
        os.makedirs(os.path.join(tmp, ".git", "hooks"))
        os.makedirs(os.path.join(tmp, ".git", "objects"))
        for rel in [".git/config", ".git/hooks/pre-commit", ".git/objects/zz"]:
            with open(os.path.join(tmp, rel), "w") as f:
                f.write("x")
        cand = os.path.join(tmp, "cand.py")
        with open(cand, "w") as f:
            f.write("pass\n")
        code1, out1 = vw.run_in_worktree('echo evil > "%s/.git/config"' % tmp, cand, cand, tmp, 30)
        code2, out2 = vw.run_in_worktree('echo evil > "%s/.git/hooks/post-commit"' % tmp, cand, cand, tmp, 30)
        code3, out3 = vw.run_in_worktree('touch "%s/.git/objects/yy"' % tmp, cand, cand, tmp, 30)
        ok1 = code1 == 125 and ".git/config" in out1
        ok2 = code2 == 125 and ".git/hooks/post-commit" in out2
        ok3 = code3 == 0
        if ok1 and ok2 and ok3:
            return True, "config=125 hooks=125 objects=0"
        return False, f"config=({code1},{out1!r}) hooks=({code2},{out2!r}) objects=({code3},{out3!r})"
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = parse_args()
    if args.notice:
        print(NOTICE)
        return 0

    root = os.path.abspath(args.root)
    if not os.path.isdir(root):
        print(f"FAIL root_not_found: --root {root!r} does not exist")
        return 2

    all_pass = True

    # Test 1
    ok, detail = test_same_size_restored_mtime(root)
    if ok:
        print(f"PASS same_size_restored_mtime {detail}")
    else:
        print(f"FAIL same_size_restored_mtime expected changed()=['a.txt'] got {detail}")
        all_pass = False

    # Test 2
    ok, detail = test_max_watch_threshold(root)
    if ok:
        print(f"PASS max_watch_threshold {detail}")
    else:
        print(f"FAIL max_watch_threshold expected code=126 REFUSED marker_absent got {detail}")
        all_pass = False

    # Test 3
    ok, detail = test_watch_limit_exceeded_after_check(root)
    if ok:
        print(f"PASS watch_limit_exceeded_after_check {detail}")
    else:
        print(f"FAIL watch_limit_exceeded_after_check expected code=125 with the watch-limit message got {detail}")
        all_pass = False

    # Test 4
    ok, detail = test_git_config_and_hooks_watched(root)
    if ok:
        print(f"PASS git_config_and_hooks_watched {detail}")
    else:
        print(f"FAIL git_config_and_hooks_watched expected 125 on .git/config and .git/hooks writes and 0 on .git/objects got {detail}")
        all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())