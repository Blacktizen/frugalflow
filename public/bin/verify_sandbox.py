"""Run a delegation check in an isolated temporary folder.

The check command runs with only the candidate file, the sibling modules the
candidate imports, and the project files the command names.  Sensitive
environment variables are stripped, a time limit applies, and any write the
check still makes into the project folder is reported instead of applied.
"""

import ast
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
    "NAME      verify_sandbox.py - runs a delegation check in a temporary folder holding only the useful files, without sensitive variables, under a time limit, and reports any write into the project.",
    "READS     the candidate, the sibling modules it imports, and the project files the check command names.",
    "WRITES    a temporary folder, removed afterwards; never the project: run_isolated() returns (code, output), 124 on timeout, 125 when the check wrote into the project.",
    "EXAMPLE   python3 verify_sandbox.py --autotest",
    "PITFALLS  2026-10-03 a check ran in the project folder with every secret of the environment: it could write beside the code and read the keys; it now runs in a copy, and a write it still makes through an absolute path is caught and refused.",
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


def snapshot(project_dir):
    """Walk project_dir and map each relative path to (st_mtime_ns, st_size),
    or return None once the file count exceeds MAX_WATCH."""
    result = {}
    count = 0
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [dirname for dirname in dirnames if dirname not in SKIP_DIRS]
        for filename in filenames:
            count += 1
            if count > MAX_WATCH:
                return None
            full = os.path.join(dirpath, filename)
            relative = os.path.relpath(full, project_dir)
            try:
                stat_result = os.stat(full)
            except OSError:
                continue
            result[relative] = (stat_result.st_mtime_ns, stat_result.st_size)
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


def run_isolated(verify_cmd, candidate_path, out_path, project_dir, timeout):
    """Run verify_cmd in a temporary folder and report any write it makes
    into project_dir."""
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
        before = snapshot(project_dir)
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
        written = changed(before, snapshot(project_dir))
        if written:
            return (125, "VERIFY WROTE TO THE PROJECT: " + ", ".join(written[:5]))
        return (proc.returncode, output or "")
    finally:
        shutil.rmtree(work, ignore_errors=True)


def autotest():
    """Run the five checks and return 0 when all pass, otherwise 1."""
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
        res = run_isolated(
            'python3 "$FRUGALFLOW_CANDIDATE" | grep -q 42 && test "$(basename "$FRUGALFLOW_CANDIDATE")" = a.py && test "$(ls | tr "\\n" " ")" = "a.py deep.py helper.py "',
            candidate_path, out_path, project_dir, 30)
        after_list = sorted(os.listdir(project_dir))
        ok = is_pair(res) and res[0] == 0 and before_list == after_list
        got = "code=%r listdir_same=%r" % (res[0], before_list == after_list) if is_pair(res) else "result=%r" % (res,)
        print("%s test 1: expected code 0 and listdir unchanged; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 2: command files are copied, and sensitive variables are gone.
        res = run_isolated('sh check.sh "$FRUGALFLOW_CANDIDATE" && test -e check.sh',
                           candidate_path, out_path, project_dir, 30)
        os.environ["MY_API_TOKEN"] = "z"
        try:
            res2 = run_isolated('test -z "$MY_API_TOKEN"', candidate_path, out_path, project_dir, 30)
        finally:
            del os.environ["MY_API_TOKEN"]
        ok = is_pair(res) and res[0] == 0 and is_pair(res2) and res2[0] == 0
        got = "code=%r token_code=%r" % (res if is_pair(res) else None, res2 if is_pair(res2) else None)
        print("%s test 2: expected code 0 and token code 0; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

        # Test 3: a write inside the work folder is fine, a write into the
        # project folder is refused.
        res = run_isolated('echo x > trace.txt', candidate_path, out_path, project_dir, 30)
        res2 = run_isolated('echo x > "' + project_dir + '/w.txt"',
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
        res = run_isolated('sleep 20', candidate_path, out_path, project_dir, 1)
        duration = os.times()[4] - start
        res2 = run_isolated('exit 3', candidate_path, out_path, project_dir, 30)
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
              and proc.stdout.startswith("NAME      verify_sandbox.py"))
        got = "scrub=%r files=%r notice_code=%r" % (res, res2, proc.returncode)
        print("%s test 5: expected scrub, files and notice; got %s" % ("PASS" if ok else "FAIL", got))
        if ok:
            passed += 1

    finally:
        shutil.rmtree(project_dir, ignore_errors=True)
    return 0 if passed == 5 else 1


def main(argv):
    """Dispatch the command line."""
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    print("usage: verify_sandbox.py --notice | --autotest")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "verify_sandbox", sys.argv[1:])
