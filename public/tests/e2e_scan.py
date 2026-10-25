import os
import sys
import subprocess
import tempfile
import shutil

TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bin",
    "frugalflow.py",
)

KEY_LINE = "api" + "_key = " + chr(34) + "abcd1234efgh5678ijkl" + chr(34) + "\n"
MAIL_LINE = "contact: dev" + "@acme-corp" + ".org\n"
PEM_LINE = "-----BEGIN RSA PRIV" + "ATE KEY-----\n"
CLEAN_LINE = "def add(a, b):\n    return a + b\n"

LEAKY = {
    "app/config.py": KEY_LINE,
    "docs/notes.md": MAIL_LINE,
    "deploy/id_rsa.pem": PEM_LINE,
    "src/clean.py": CLEAN_LINE,
    "ignored.txt": KEY_LINE,
    ".gitignore": "ignored.txt\n",
}

HEALTHY = {
    "src/one.py": CLEAN_LINE,
    "src/two.py": CLEAN_LINE,
}

FOUND_3 = "FOUND 3 leak(s) in 3 file(s)"
FOUND_1 = "FOUND 1 leak(s) in 1 file(s)"
CLEAN_2 = "CLEAN: 2 file(s) scanned, no leak found"
SECRET_VALUES = ["abcd1234efgh5678ijkl", "acme-corp", "BEGIN RSA"]


def _clean_env(tmp_home):
    env = os.environ.copy()
    env["HOME"] = tmp_home
    env["USERPROFILE"] = tmp_home
    env.pop("FRUGALFLOW_HOME", None)
    for k in list(env):
        if k.startswith("GIT_"):
            del env[k]
    return env


def _make_env(tmp_home):
    env = os.environ.copy()
    env["HOME"] = tmp_home
    env["USERPROFILE"] = tmp_home
    env.pop("FRUGALFLOW_HOME", None)
    for k in list(env):
        if k.startswith("GIT_"):
            del env[k]
    return env


def run_scan(args, cwd, env=None):
    cmd = [sys.executable, TOOL, "scan"] + args
    if env is None:
        env = os.environ.copy()
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=300,
        cwd=cwd,
        env=env,
    )
    return result


def make_tree(base, files):
    for rel, content in files.items():
        full = os.path.join(base, rel)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        with open(full, "w", encoding="utf-8") as f:
            f.write(content)


def git_init(base, env):
    subprocess.run(
        ["git", "init", "-q"],
        cwd=base,
        env=env,
        capture_output=True,
        timeout=300,
    )
    rc = subprocess.run(
        ["git", "status"],
        cwd=base,
        env=env,
        capture_output=True,
        timeout=300,
    )
    if rc.returncode != 0:
        raise RuntimeError("git init failed")


def main():
    TMP = tempfile.mkdtemp()
    tmp_home = tempfile.mkdtemp()
    env = _make_env(tmp_home)
    results = []

    try:
        # Test 1: leaky repo
        try:
            repo1 = os.path.join(TMP, "leaky")
            make_tree(repo1, LEAKY)
            git_init(repo1, env)
            r = run_scan([repo1], cwd=TMP, env=env)
            ok = True
            ok = ok and r.returncode == 12
            ok = ok and r.stdout != ""
            ok = ok and "app/config.py:1" in r.stdout
            ok = ok and "docs/notes.md:1" in r.stdout
            ok = ok and "deploy/id_rsa.pem:1" in r.stdout
            ok = ok and FOUND_3 in r.stdout
            ok = ok and "ignored.txt" not in r.stdout
            for sv in SECRET_VALUES:
                if sv in r.stdout:
                    ok = False
            if ok:
                results.append(("PASS", "PASS 1 leaky repo exits 12"))
            else:
                results.append(("FAIL", "FAIL 1 unexpected result"))
        except Exception as e:
            results.append(("FAIL", "FAIL 1 " + repr(e)))

        # Test 2: healthy repo
        try:
            repo2 = os.path.join(TMP, "healthy")
            make_tree(repo2, HEALTHY)
            git_init(repo2, env)
            r = run_scan([repo2], cwd=TMP, env=env)
            ok = True
            ok = ok and r.returncode == 0
            ok = ok and r.stdout != ""
            ok = ok and CLEAN_2 in r.stdout
            if ok:
                results.append(("PASS", "PASS 2 healthy repo exits 0"))
            else:
                results.append(("FAIL", "FAIL 2 unexpected result"))
        except Exception as e:
            results.append(("FAIL", "FAIL 2 " + repr(e)))

        # Test 3: staged mode
        try:
            repo3 = os.path.join(TMP, "leaky")
            subprocess.run(
                ["git", "add", "app/config.py"],
                cwd=repo3,
                env=env,
                capture_output=True,
                timeout=300,
            )
            r = run_scan(["--staged", repo3], cwd=TMP, env=env)
            ok = True
            ok = ok and r.returncode == 12
            ok = ok and r.stdout != ""
            ok = ok and "app/config.py:1" in r.stdout
            ok = ok and FOUND_1 in r.stdout
            ok = ok and "docs/notes.md" not in r.stdout
            if ok:
                results.append(("PASS", "PASS 3 staged mode sees only the staged file"))
            else:
                results.append(("FAIL", "FAIL 3 unexpected result"))
        except Exception as e:
            results.append(("FAIL", "FAIL 3 " + repr(e)))

        # Test 4: usage errors
        try:
            absent = os.path.join(TMP, "absent")
            r = run_scan([absent], cwd=TMP, env=env)
            ok = True
            ok = ok and r.returncode == 2
            ok = ok and "NO PATH" in r.stdout

            badrules_path = os.path.join(TMP, "badrules.json")
            with open(badrules_path, "w", encoding="utf-8") as f:
                f.write("[]")
            healthy2 = os.path.join(TMP, "healthy")
            r2 = run_scan(["--rules", badrules_path, healthy2], cwd=TMP, env=env)
            ok = ok and r2.returncode == 13

            if ok:
                results.append(("PASS", "PASS 4 usage errors exit 2 and 13"))
            else:
                results.append(("FAIL", "FAIL 4 unexpected result"))
        except Exception as e:
            results.append(("FAIL", "FAIL 4 " + repr(e)))

        # Test 5: plain folder and quiet mode
        try:
            plain = os.path.join(TMP, "plain")
            plain_files = {k: v for k, v in LEAKY.items()
                           if k != ".gitignore" and k != "ignored.txt"}
            make_tree(plain, plain_files)
            r = run_scan(["--quiet", plain], cwd=TMP, env=env)
            ok = True
            ok = ok and r.returncode == 12
            ok = ok and r.stdout != ""
            ok = ok and r.stdout.strip().splitlines() == [FOUND_3]
            if ok:
                results.append(("PASS", "PASS 5 plain folder and quiet mode"))
            else:
                results.append(("FAIL", "FAIL 5 unexpected result"))
        except Exception as e:
            results.append(("FAIL", "FAIL 5 " + repr(e)))

    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        shutil.rmtree(tmp_home, ignore_errors=True)

    n_pass = 0
    for status, line in results:
        print(line)
        if status == "PASS":
            n_pass += 1

    print("E2E SCAN %d/5" % n_pass)
    sys.exit(0 if n_pass == 5 else 1)


if __name__ == "__main__":
    main()
