import sys
import os
import subprocess
import shutil
import tempfile
import glob
import json


def build_env():
    env = {}
    for k, v in os.environ.items():
        if not k.startswith("GIT_"):
            env[k] = v
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def collect_elements(root):
    elements = []
    bin_dir = os.path.join(root, "bin")
    if os.path.isdir(bin_dir):
        for name in sorted(os.listdir(bin_dir)):
            if name.endswith(".py"):
                full = os.path.join(bin_dir, name)
                if os.path.isfile(full):
                    elements.append(("autotest", name, full))
    tests_dir = os.path.join(root, "tests")
    if os.path.isdir(tests_dir):
        for name in sorted(os.listdir(tests_dir)):
            if name.startswith("e2e_") and name.endswith(".py"):
                full = os.path.join(tests_dir, name)
                if os.path.isfile(full):
                    elements.append(("e2e", name, full))
    return elements


def run_element(genre, name, full_path, root, env, base_env):
    try:
        proc = subprocess.run(
            [sys.executable, full_path, "--autotest"] if genre == "autotest" else [sys.executable, full_path],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=600,
            env=base_env,
        )
        rc = proc.returncode
        combined = proc.stdout + proc.stderr
    except subprocess.TimeoutExpired:
        rc = 124
        combined = ""
    except Exception:
        rc = 1
        combined = ""
    return rc, combined


def run_suite(root, fail_fast):
    if not os.path.isdir(root):
        print("RUN ALL FAILED: no such root")
        return 2

    elements = collect_elements(root)

    if not elements:
        print("RUN ALL FAILED 0 of 0")
        return 1

    tmp_dir = tempfile.mkdtemp()
    anon_data = {"anonymizable": [], "irreducible": [{"pattern": "zzleakword", "label": "autotest leak"}]}
    with open(os.path.join(tmp_dir, "anonymization.json"), "w") as f:
        f.write(json.dumps(anon_data))

    base_env = build_env()
    base_env["FRUGALFLOW_HOME"] = tmp_dir

    n_total = 0
    n_fail = 0
    try:
        for genre, name, full_path in elements:
            n_total += 1
            rc, combined = run_element(genre, name, full_path, root, base_env, base_env)
            if rc == 0:
                print("PASS {} {}".format(genre, name))
            else:
                n_fail += 1
                print("FAIL {} {} (rc={})".format(genre, name, rc))
                lines = combined.splitlines()
                tail = lines[-10:] if len(lines) > 10 else lines
                for line in tail:
                    print("    " + line)
            if fail_fast and n_fail > 0:
                break
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)

    if n_fail == 0:
        print("RUN ALL OK {}/{}".format(n_total, n_total))
        return 0
    else:
        print("RUN ALL FAILED {} of {}".format(n_fail, n_total))
        return 1


def write_fixture(root, genre, name, content):
    if genre == "autotest":
        d = os.path.join(root, "bin")
    else:
        d = os.path.join(root, "tests")
    os.makedirs(d, exist_ok=True)
    with open(os.path.join(d, name), "w") as f:
        f.write(content)


def autotest_run(runner_path):
    failures = 0

    # Test 1: healthy tree, code 0
    tmp = tempfile.mkdtemp()
    try:
        write_fixture(tmp, "autotest", "ok.py", "import sys\nsys.exit(0)\n")
        write_fixture(tmp, "e2e", "e2e_ok.py", "import sys\nsys.exit(0)\n")
        proc = subprocess.run(
            [sys.executable, runner_path, "--root", tmp],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout
        last_line = out.strip().splitlines()[-1] if out.strip() else ""
        if proc.returncode == 0 and last_line == "RUN ALL OK 2/2":
            print("PASS test1 healthy tree: rc=0 last='RUN ALL OK 2/2'")
        else:
            failures += 1
            print("FAIL test1 healthy tree: rc={} last='{}' expected rc=0 last='RUN ALL OK 2/2'".format(
                proc.returncode, last_line))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 2: broken tree, code 1, contains both PASS and FAIL lines
    tmp = tempfile.mkdtemp()
    try:
        write_fixture(tmp, "autotest", "a_bad.py", 'import sys\nprint("PASS 1 looks fine")\nsys.exit(1)\n')
        write_fixture(tmp, "autotest", "b_ok.py", "import sys\nsys.exit(0)\n")
        proc = subprocess.run(
            [sys.executable, runner_path, "--root", tmp],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout
        last_line = out.strip().splitlines()[-1] if out.strip() else ""
        cond = (
            proc.returncode == 1
            and "FAIL autotest a_bad.py" in out
            and "PASS autotest b_ok.py" in out
            and last_line == "RUN ALL FAILED 1 of 2"
        )
        if cond:
            print("PASS test2 broken tree: rc=1 has FAIL a_bad has PASS b_ok last='RUN ALL FAILED 1 of 2'")
        else:
            failures += 1
            print("FAIL test2 broken tree: rc={} cond={}".format(proc.returncode, cond))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 3: broken tree with --fail-fast, code 1, no b_ok.py in output
    tmp = tempfile.mkdtemp()
    try:
        write_fixture(tmp, "autotest", "a_bad.py", 'import sys\nprint("PASS 1 looks fine")\nsys.exit(1)\n')
        write_fixture(tmp, "autotest", "b_ok.py", "import sys\nsys.exit(0)\n")
        proc = subprocess.run(
            [sys.executable, runner_path, "--root", tmp, "--fail-fast"],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout
        cond = (proc.returncode == 1 and "b_ok.py" not in out)
        if cond:
            print("PASS test3 fail-fast: rc=1 no b_ok.py in output")
        else:
            failures += 1
            print("FAIL test3 fail-fast: rc={} b_ok_present={}".format(
                proc.returncode, "b_ok.py" in out))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # Test 4: non-existent root, code 2, contains "no such root"
    tmp = tempfile.mkdtemp()
    try:
        fake_root = os.path.join(tmp, "does_not_exist_xyz")
        proc = subprocess.run(
            [sys.executable, runner_path, "--root", fake_root],
            capture_output=True, text=True, timeout=30,
        )
        out = proc.stdout
        cond = (proc.returncode == 2 and "no such root" in out)
        if cond:
            print("PASS test4 missing root: rc=2 'no such root' present")
        else:
            failures += 1
            print("FAIL test4 missing root: rc={} 'no such root'={}".format(
                proc.returncode, "no such root" in out))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    total = 4
    print("AUTOTEST {}/{}".format(total - failures, total))
    return 0 if failures == 0 else 1


def notice():
    print("NAME: run_all.py - runs every autotest and E2E and exits non-zero on the first failure or at the end.")
    print("READS: ROOT/bin/*.py, ROOT/tests/e2e_*.py, environment variables (GIT_* excluded), FRUGALFLOW_HOME/anonymization.json")
    print("WRITES: FRUGALFLOW_HOME temp dir with anonymization.json (deleted at end), stdout for report lines")
    print("EXAMPLE: python3 run_all.py --root /path/to/project --fail-fast")
    print("PITFALLS: exit code is the sole verdict source; PASS/FAIL text printed by the element itself is ignored; timeout of 600s yields rc=124")
    return 0


def main():
    args = sys.argv[1:]

    if "--notice" in args:
        sys.exit(notice())

    if "--autotest" in args:
        runner = os.path.abspath(__file__)
        sys.exit(autotest_run(runner))

    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    fail_fast = False

    i = 0
    while i < len(args):
        if args[i] == "--root":
            i += 1
            if i < len(args):
                root = args[i]
        elif args[i] == "--fail-fast":
            fail_fast = True
        i += 1

    sys.exit(run_suite(root, fail_fast))


if __name__ == "__main__":
    main()
