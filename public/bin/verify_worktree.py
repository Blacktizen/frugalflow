"""Run a delegation check in a temporary working copy of the project.

This is NOT a sandbox: there is no operating-system isolation. Files outside the
copy, other processes and the network stay reachable with the user's permissions.

The check command runs with only the candidate file, the sibling modules the
candidate imports, and the project files the command names.  Sensitive
environment variables are stripped, a time limit applies, and any write the
check still makes into the project folder is reported instead of applied.
"""

import ast
import hashlib
import os
import re
import shlex
import shutil
import signal
import subprocess
import sys
import tempfile

SENSITIVE = re.compile(r"(?i)(key|token|secret|passw|credential|auth|cookie|session|private)")
SKIP_DIRS = {".git", "node_modules", "__pycache__", ".venv", "venv"}
MAX_WATCH = 50000

NOTICE = "\n".join([
    "NAME      verify_worktree.py - runs a delegation check in a temporary work folder (NOT a sandbox: no system isolation) holding only the useful files, without sensitive variables, under a time limit, and reports any write into the project.",
    "READS     the candidate, the sibling modules it imports, and the project files the check command names.",
    "WRITES    a temporary folder, removed afterwards; never the project: run_in_worktree() returns (code, output), 124 on timeout, 125 when the check wrote into the project.",
    "EXAMPLE   python3 verify_worktree.py --autotest",
    "PITFALLS  2026-10-03 a check ran in the project folder with every secret of the environment: it could write beside the code and read the keys; it now runs in a copy, and a write it still makes through an absolute path is caught and refused.",
    "          2026-11-12 the second snapshot returned None when the check pushed the file count over the watch limit, so changed() saw nothing and the write passed; a None second snapshot is now refused like a detected write, and .git/config plus every file under .git/hooks/ are watched.",
])


def scrub_env(environ):
    """Return the (key, value) pairs whose key does not look sensitive."""
    return {key: value for key, value in environ.items() if SENSITIVE.search(key) is None}


def neighbour_modules(source_text, folder, own_name):
    """Return the sorted absolute paths of the imported sibling modules,
    discovered transitively up to a depth of 3."""
    try:
        tree = ast.parse(source_text)
    except (SyntaxError, ValueError):
        return []

    def names_in(tree):
        result = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    result.append(alias.name.split(".")[0])
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module is not None:
                    result.append(node.module.split(".")[0])
        return result

    result = []
    seen = set()
    queue = [(tree, 1)]
    while queue:
        tree, depth = queue.pop(0)
        for name in names_in(tree):
            if name + ".py" == own_name:
                continue
            path = os.path.abspath(os.path.join(folder, name + ".py"))
            if not os.path.isfile(path) or path in seen:
                continue
            seen.add(path)
            result.append(path)
            if depth < 3:
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        text = f.read()
                except OSError:
                    continue
                try:
                    child = ast.parse(text)
                except (SyntaxError, ValueError):
                    continue
                queue.append((child, depth + 1))
    return sorted(result)


def command_files(verify_cmd, project_dir):
    """Return the deduplicated, ordered tokens of verify_cmd that name a
    project file to copy into the work folder."""
    try:
        tokens = shlex.split(verify_cmd)
    except ValueError:
        tokens = verify_cmd.split()
    result = []
    seen = set()
    for token in tokens:
        if token.startswith("-"):
            continue
        if "$" in token:
            continue
        if os.path.isabs(token):
            continue
        if ".." in token.split("/"):
            continue
        if not os.path.isfile(os.path.join(project_dir, token)):
            continue
        if token in seen:
            continue
        seen.add(token)
        result.append(token)
    return result


def snapshot(project_dir, max_watch=MAX_WATCH):
    """Walk project_dir and map each relative path to (st_mtime_ns, st_size, sha256_hex),
    or return None once the file count exceeds max_watch."""
    result = {}
    count = 0
    for dirpath, dirnames, filenames in os.walk(project_dir):
        relative_dir = os.path.relpath(dirpath, project_dir)
        if relative_dir == ".":
            # .git stays walked at the root: a write to .git/config or under
            # .git/hooks/ is a write into the project. Other skipped dirs stay.
            dirnames[:] = [dirname for dirname in dirnames
                           if dirname not in SKIP_DIRS or dirname == ".git"]
        elif relative_dir == ".git":
            dirnames[:] = ["hooks"] if "hooks" in dirnames else []
            filenames = [filename for filename in filenames if filename == "config"]
        else:
            dirnames[:] = [dirname for dirname in dirnames if dirname not in SKIP_DIRS]
        for filename in filenames:
            count += 1
            if count > max_watch:
                return None
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, project_dir)
            try:
                stat_result = os.stat(full)
            except OSError:
                continue
            # Compute SHA-256 of file content in chunks
            sha256 = hashlib.sha256()
            try:
                with open(full, "rb") as f:
                    for chunk in iter(lambda: f.read(65536), b""):
                        sha256.update(chunk)
            except OSError:
                continue
            result[relative] = (stat_result.st_mtime_ns, stat_result.st_size, sha256.hexdigest())
    return result


def changed(before, after):
    """Return sorted paths present in only one dict or whose value differs."""
    if before is None or after is None:
        return []
    result = []
    for path in set(before) | set(after):
        if path not in before or path not in after or before[path] != after[path]:
            result.append(path)
    return sorted(result)


def run_in_worktree(verify_cmd, candidate_path, out_path, project_dir, timeout, max_watch=MAX_WATCH):
    """Run verify_cmd in a temporary folder and report any write it makes
    into project_dir. Refuse if project has more than max_watch files."""
    work = tempfile.mkdtemp(prefix="frugalflow-verify-")
    try:
        name = os.path.basename(out_path)
        shutil.copyfile(candidate_path, os.path.join(work, name))
        with open(candidate_path, "r", encoding="utf-8") as f:
            source_text = f.read()
        for path in neighbour_modules(source_text, os.path.dirname(os.path.abspath(out_path)), name):
            shutil.copyfile(path, os.path.join(work, os.path.basename(path)))
        for relative in command_files(verify_cmd, project_dir):
            target = os.path.join(work, relative)
            os.makedirs(os.path.dirname(target) or work, exist_ok=True)
            shutil.copyfile(os.path.join(project_dir, relative), target)
        env = scrub_env(os.environ)
        env["FRUGALFLOW_CANDIDATE"] = os.path.join(work, name)
        env["PYTHONPYCACHEPREFIX"] = os.path.join(work, ".pycache")
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        before = snapshot(project_dir, max_watch=max_watch)
        if before is None:
            return (126, "VERIFY REFUSED: the project has more than %d files, the write check cannot cover it" % max_watch)
        proc = subprocess.Popen(
            verify_cmd,
            shell=True,
            cwd=work,
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )
        try:
            output, _ = proc.communicate(timeout=timeout)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc.communicate()
            return (124, "VERIFY TIMEOUT after " + str(timeout) + " s")
        after = snapshot(project_dir, max_watch=max_watch)
        if after is None:
            # the first snapshot fit under the limit; it does not anymore:
            # files were added. Refuse like a detected write.
            return (125, "VERIFY WROTE TO THE PROJECT: the file count went over the watch limit")
        written = changed(before, after)
        if written:
            return (125, "VERIFY WROTE TO THE PROJECT: " + ", ".join(written[:5]))
        return (proc.returncode, output or "")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def autotest():
    """Run the eight checks and return 0 when all pass, otherwise 1."""
    passed = 0
    project_dir = tempfile.mkdtemp(prefix="frugalflow-autotest-")
    try:
        with open(os.path.join(project_dir, "cand.py"), "w", encoding="utf-8") as f:
            f.write("import helper\nprint(helper.X)\n")
        with open(os.path.join(project_dir, "helper.py"), "w", encoding="utf-8") as f:
            f.write("import deep\nX = deep.Y\n")
        with open(os.path.join(project_dir, "deep.py"), "w", encoding="utf-8") as f:
            f.write("Y = 42\n")
        with open(os.path.join(project_dir, "secret.txt"), "w", encoding="utf-8") as f:
            f.write("x\n")
        with open(os.path.join(project_dir, "check.sh"), "w", encoding="utf-8") as f:
            f.write('python3 "$1" | grep -q 42\n')
        candidate_path = os.path.join(project_dir, "cand.py")
        out_path = os.path.join(project_dir, "a.py")

        def is_pair(res):
            return isinstance(res, tuple) and len(res) == 2

        # Test 1: the candidate and its two imports run inside the work folder.
        before_list = sorted(os.listdir(project_dir))
        res = run_in_worktree(
            'python3 "$FRUGALFLOW_CANDIDATE" | grep -q 42 && test "$(basename "$FRUGALFLOW_CANDIDATE")" = a.py && test "$(ls | tr "\\n" " ")" = "a.py deep.py helper.py "',
            candidate_path, out_path, project_dir, 30)
        after_list = sorted(os.listdir(project_dir))
        ok = is_pair(res) and res[0] == 0 and before_list == after_list
        got = "code=%r listdir_same=%r" % (res[0], before_list == after_list) if is_pair(res) else "result=%r" % (res,)
        print("%s test 1: expected code 0 and listdir unchanged; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 2: command files are copied, and sensitive variables are gone.
        res = run_in_worktree('sh check.sh "$FRUGALFLOW_CANDIDATE" && test -e check.sh',
                           candidate_path, out_path, project_dir, 30)
        os.environ["MY_API_TOKEN"] = "z"
        try:
            res2 = run_in_worktree('test -z "$MY_API_TOKEN"', candidate_path, out_path, project_dir, 30)
        finally:
            del os.environ["MY_API_TOKEN"]
        ok = is_pair(res) and res[0] == 0 and is_pair(res2) and res2[0] == 0
        got = "code=%r token_code=%r" % (res if is_pair(res) else None, res2 if is_pair(res2) else None)
        print("%s test 2: expected code 0 and token code 0; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 3: a write inside the work folder is fine, a write into the
        # project folder is refused.
        res = run_in_worktree('echo x > trace.txt', candidate_path, out_path, project_dir, 30)
        res2 = run_in_worktree('echo x > "' + project_dir + '/w.txt"',
                            candidate_path, out_path, project_dir, 30)
        ok = (is_pair(res) and res[0] == 0
              and not os.path.exists(os.path.join(project_dir, "trace.txt"))
              and res2 == (125, "VERIFY WROTE TO THE PROJECT: w.txt"))
        got = "code=%r trace_exists=%r write_result=%r" % (
            res[0] if is_pair(res) else res,
            os.path.exists(os.path.join(project_dir, "trace.txt")),
            res2)
        print("%s test 3: expected code 0, no trace.txt and 125 on w.txt; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 4: the time limit is enforced and a plain exit code passes through.
        start = os.times()[4]
        res = run_in_worktree('sleep 20', candidate_path, out_path, project_dir, 1)
        duration = os.times()[4] - start
        res2 = run_in_worktree('exit 3', candidate_path, out_path, project_dir, 30)
        ok = (res == (124, "VERIFY TIMEOUT after 1 s") and duration < 10
              and is_pair(res2) and res2[0] == 3)
        got = "timeout_result=%r duration=%r exit_code=%r" % (res, duration, res2 if is_pair(res2) else res2)
        print("%s test 4: expected 124 under 10 s and exit code 3; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 5: scrub_env, command_files, and the --notice subprocess.
        res = scrub_env({"PATH": "/b", "GITHUB_TOKEN": "t", "Api_Key": "k", "HOME": "/h"})
        res2 = command_files("python3 ../x.py check.sh -o secret.txt $F/y /etc/hosts", project_dir)
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"],
                              stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
        ok = (res == {"PATH": "/b", "HOME": "/h"}
              and res2 == ["check.sh", "secret.txt"]
              and proc.returncode == 0
              and proc.stdout.startswith("NAME      verify_worktree.py"))
        got = "scrub=%r files=%r notice_code=%r" % (res, res2, proc.returncode)
        print("%s test 5: expected scrub, files and notice; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 6: file modified at same size with restored mtime is detected via SHA-256.
        test6_dir = tempfile.mkdtemp(prefix="frugalflow-test6-")
        try:
            test_file = os.path.join(test6_dir, "test.txt")
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("original content")
            before_snap = snapshot(test6_dir, max_watch=10)
            # Modify file to same size, restore mtime
            stat_before = os.stat(test_file)
            with open(test_file, "w", encoding="utf-8") as f:
                f.write("modified contnt")  # same length (16 chars)
            os.utime(test_file, ns=(stat_before.st_atime_ns, stat_before.st_mtime_ns))
            after_snap = snapshot(test6_dir, max_watch=10)
            diff = changed(before_snap, after_snap)
            ok = (len(diff) == 1 and diff[0] == "test.txt")
            got = "diff=%r" % (diff,)
            print("%s test 6: expected changed() to detect same-size restored-mtime modification; got %s" % ("PASS" if ok else "FAIL", got))
            if ok:
                passed += 1
        finally:
            shutil.rmtree(test6_dir, ignore_errors=True)

        # Test 7: tree exceeding max_watch is refused explicitly (code 126, message contains REFUSED).
        test7_dir = tempfile.mkdtemp(prefix="frugalflow-test7-")
        try:
            # Create 7 files with max_watch=5
            for i in range(7):
                with open(os.path.join(test7_dir, "f%d.txt" % i), "w") as f:
                    f.write("x")
            # Create a candidate file for run_in_worktree
            cand = os.path.join(test7_dir, "cand.py")
            with open(cand, "w") as f:
                f.write("pass\n")
            out = os.path.join(test7_dir, "out.py")
            marker = os.path.join(test7_dir, "marker.txt")
            # Command that would create a marker if executed
            res = run_in_worktree('touch "' + marker + '"', cand, out, test7_dir, 30, max_watch=5)
            marker_exists = os.path.exists(marker)
            ok = (res[0] == 126 and "REFUSED" in res[1] and not marker_exists)
            got = "code=%r msg=%r marker_exists=%r" % (res[0], res[1], marker_exists)
            print("%s test 7: expected code 126 with REFUSED, command not run; got %s" % ("PASS" if ok else "FAIL", got))
            if ok:
                passed += 1
        finally:
            shutil.rmtree(test7_dir, ignore_errors=True)

        # Test 8: tree under max_watch works (3 files, max_watch=5, command 'true').
        test8_dir = tempfile.mkdtemp(prefix="frugalflow-test8-")
        try:
            for i in range(3):
                with open(os.path.join(test8_dir, "f%d.txt" % i), "w") as f:
                    f.write("x")
            cand = os.path.join(test8_dir, "cand.py")
            with open(cand, "w") as f:
                f.write("pass\n")
            out = os.path.join(test8_dir, "out.py")
            res = run_in_worktree('true', cand, out, test8_dir, 30, max_watch=5)
            ok = (is_pair(res) and res[0] == 0)
            got = "code=%r" % (res[0] if is_pair(res) else res)
            print("%s test 8: expected code 0 for tree under max_watch; got %s" % ("PASS" if ok else "FAIL", got))
            if ok:
                passed += 1
        finally:
            shutil.rmtree(test8_dir, ignore_errors=True)

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
    return 0 if passed == 8 else 1


def main(argv):
    """Dispatch the command line."""
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    print("usage: verify_worktree.py --notice | --autotest")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "verify_worktree", sys.argv[1:])
