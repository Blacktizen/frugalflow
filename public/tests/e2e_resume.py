import os
import sys
import subprocess
import tempfile
import shutil

NOTICE = (
    "NAME      e2e_resume.py - end-to-end test of frugalflow resume: the text built from a vault and its sealed log.\n"
    "READS     the tools in ../bin; it builds a temporary vault with vault_new.py and journal_add.py.\n"
    "WRITES    only in temporary folders, always removed. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_resume.py\n"
    "PITFALLS  2026-10-25 the session handoff text lived outside the public repo, so a newcomer had nothing to paste into a new session.\n"
)

FIXTURE_TODO_APPEND = "- [ ] (me) Write the parser tests\n- [x] (me) Pick a license\n"

FIXTURE_TODO_REWRITE = "# demo - todo\n\n- [x] (me) done\n"

BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"
)


def make_env(home_path):
    env = {}
    for key, val in os.environ.items():
        if key.startswith("GIT_") or key.startswith("FRUGALFLOW_"):
            continue
        env[key] = val
    env["HOME"] = home_path
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_cmd(args, env, cwd=None):
    result = subprocess.run(
        args,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    return result.returncode, result.stdout, result.stderr


def setup_project(base_dir, env):
    proj = os.path.join(base_dir, "proj")
    os.makedirs(proj, exist_ok=True)
    vault_new = os.path.join(BIN_DIR, "vault_new.py")
    rc, out, err = run_cmd(
        [sys.executable, vault_new, "--root", proj, "--name", "demo", "--today", "2026-01-05"],
        env,
    )
    if rc != 0:
        return None, "vault_new failed: " + err
    vault = os.path.join(proj, "vault")
    journal_add = os.path.join(BIN_DIR, "journal_add.py")
    entries = [
        ("Picked sqlite", "Decision=Picked sqlite", "Why=one file, no server"),
        ("Dropped the cache", "Decision=Dropped the cache", "Why=stale reads seen twice"),
    ]
    for title, f1, f2 in entries:
        rc, out, err = run_cmd(
            [sys.executable, journal_add, "--vault", vault, "--title", title, "--field", f1, "--field", f2],
            env,
        )
        if rc != 0:
            return None, "journal_add failed: " + err
    todo_path = os.path.join(vault, "todo.md")
    with open(todo_path, "a", encoding="ascii") as fh:
        fh.write(FIXTURE_TODO_APPEND)
    return proj, None


def test_1(vault, env):
    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--vault", vault]
    rc, out, err = run_cmd(cmd, env)
    if not out.strip():
        return False, "expected output; got empty stdout"
    checks = [
        rc == 0,
        "Write the parser tests" in out,
        "Dropped the cache" in out,
        "stale reads seen twice" in out,
        "Picked sqlite" in out,
        "demo" in out,
        "overview.md" in out,
        "todo.md" in out,
        "sealed, 3 entries" in out,
        "Pick a license" not in out,
        "Traceback" not in out,
    ]
    vault_base = os.path.dirname(vault)
    if vault_base in out:
        checks.append(False)
    failed = [c for c in checks if not c]
    if failed:
        expected = "exit 0 with expected strings, no 'Pick a license', no temp path, no Traceback"
        return False, "expected: " + expected + "; got: rc=" + str(rc) + " err=" + err.strip()
    return True, "exit 0, all strings present, none excluded"


def test_2(vault, env):
    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--vault", vault, "--entries", "1"]
    rc, out, err = run_cmd(cmd, env)
    if not out.strip():
        return False, "expected output; got empty stdout"
    ok = rc == 0 and "Dropped the cache" in out and "Picked sqlite" not in out
    if not ok:
        return False, "expected: exit 0 with 'Dropped the cache' without 'Picked sqlite'; got: rc=" + str(rc)
    return True, "exit 0, 1 entry shown"


def test_3(vault, env):
    log_path = os.path.join(vault, "log.md")
    with open(log_path, "r", encoding="ascii") as fh:
        original = fh.read()
    modified = original.replace("Picked sqlite", "Picked postgres", 1)
    with open(log_path, "w", encoding="ascii") as fh:
        fh.write(modified)
    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--vault", vault]
    rc, out, err = run_cmd(cmd, env)
    with open(log_path, "w", encoding="ascii") as fh:
        fh.write(original)
    if not out.strip():
        return False, "expected output; got empty stdout"
    ok = rc == 4 and "LOG CHAIN BROKEN" in out
    if not ok:
        return False, "expected: exit 4 with 'LOG CHAIN BROKEN'; got: rc=" + str(rc) + " err=" + err.strip()
    return True, "exit 4, chain broken detected"


def test_4(vault, env):
    todo_path = os.path.join(vault, "todo.md")
    with open(todo_path, "w", encoding="ascii") as fh:
        fh.write(FIXTURE_TODO_REWRITE)
    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--vault", vault]
    rc, out, err = run_cmd(cmd, env)
    if not out.strip():
        return False, "expected output; got empty stdout"
    ok = rc == 0 and "NOTHING FOUND" in out
    if not ok:
        return False, "expected: exit 0 with 'NOTHING FOUND'; got: rc=" + str(rc)
    return True, "exit 0, no open task found"


def test_5(proj, vault, env):
    errors = []

    nonexistent = os.path.join(proj, "nonexistent_vault")
    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--vault", nonexistent]
    rc, out, err = run_cmd(cmd, env)
    if not out.strip():
        errors.append("sub1: empty stdout")
    elif not (rc == 3 and "NO VAULT" in out):
        errors.append("sub1: expected exit 3 with 'NO VAULT'; got rc=" + str(rc))

    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume", "--bogus"]
    rc, out, err = run_cmd(cmd, env)
    if rc != 2:
        errors.append("sub2: expected exit 2; got rc=" + str(rc))

    cmd = [sys.executable, os.path.join(BIN_DIR, "frugalflow.py"), "resume"]
    rc, out, err = run_cmd(cmd, env, cwd=proj)
    if not out.strip():
        errors.append("sub3: empty stdout")
    elif not (rc == 0 and "demo" in out):
        errors.append("sub3: expected exit 0 with 'demo'; got rc=" + str(rc))

    cmd = [sys.executable, os.path.join(BIN_DIR, "resume_cmd.py"), "--notice"]
    rc, out, err = run_cmd(cmd, env)
    if not out.strip():
        errors.append("sub4: empty stdout")
    elif not (rc == 0 and out.startswith("NAME      resume_cmd.py")):
        errors.append("sub4: expected exit 0 starting with 'NAME      resume_cmd.py'; got rc=" + str(rc))

    cmd = [sys.executable, os.path.join(BIN_DIR, "resume_cmd.py"), "--autotest"]
    rc, out, err = run_cmd(cmd, env)
    if rc != 0:
        errors.append("sub5: expected exit 0; got rc=" + str(rc))

    cmd = [sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "e2e_resume.py"), "--bogus"]
    rc, out, err = run_cmd(cmd, env)
    if rc != 2:
        errors.append("sub6: expected exit 2; got rc=" + str(rc))

    if errors:
        return False, "; ".join(errors)
    return True, "all sub-cases pass"


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(argv) > 0:
        print("usage: e2e_resume.py [--notice]")
        return 2

    tmp_root = tempfile.mkdtemp()
    home_dir = os.path.join(tmp_root, "home")
    os.makedirs(home_dir, exist_ok=True)
    env = make_env(home_dir)

    results = []
    try:
        proj, setup_err = setup_project(tmp_root, env)
        if proj is None:
            for i in range(1, 6):
                results.append((i, False, "setup failed: " + setup_err))
        else:
            vault = os.path.join(proj, "vault")

            ok, msg = test_1(vault, env)
            results.append((1, ok, msg))

            ok, msg = test_2(vault, env)
            results.append((2, ok, msg))

            ok, msg = test_3(vault, env)
            results.append((3, ok, msg))

            ok, msg = test_4(vault, env)
            results.append((4, ok, msg))

            ok, msg = test_5(proj, vault, env)
            results.append((5, ok, msg))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    fail_count = 0
    for idx, ok, msg in results:
        if ok:
            print("PASS " + str(idx) + " - " + msg)
        else:
            fail_count += 1
            print("FAIL " + str(idx) + " - " + msg)

    if fail_count == 0:
        print("E2E RESUME OK")
        return 0
    else:
        print("E2E RESUME FAILED " + str(fail_count))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
