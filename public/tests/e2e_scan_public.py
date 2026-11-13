import os
import sys
import json
import subprocess
import tempfile
import shutil

TOOL = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bin",
    "scan_cmd.py",
)

PUBLIC_FILE = ".frugalflow-public"
HANDLE = "Zorb" + "axe"
URL = "github.com/" + HANDLE + "/demo-tool"
RULES = {"anonymizable": [{"pattern": "\\b" + HANDLE + "\\b", "label": "handle", "tag": "PERSON"}],
         "irreducible": []}


def _make_env(tmp_home):
    env = os.environ.copy()
    env["HOME"] = tmp_home
    env["USERPROFILE"] = tmp_home
    env.pop("FRUGALFLOW_HOME", None)
    for k in list(env):
        if k.startswith("GIT_"):
            del env[k]
    return env


def run_scan(args, env):
    return subprocess.run(
        [sys.executable, TOOL] + args,
        capture_output=True,
        text=True,
        timeout=300,
        env=env,
    )


def make_folder(base, name, note, pub=None):
    d = os.path.join(base, name)
    os.makedirs(d)
    with open(os.path.join(d, "notes.md"), "w", encoding="utf-8") as f:
        f.write(note)
    if pub is not None:
        with open(os.path.join(d, PUBLIC_FILE), "w", encoding="utf-8") as f:
            f.write(pub)
    return d


def main():
    TMP = tempfile.mkdtemp()
    tmp_home = tempfile.mkdtemp()
    env = _make_env(tmp_home)
    results = []

    def step(n, name, ok, detail):
        results.append((ok, ("PASS " if ok else "FAIL ") + str(n) + " " + name
                        + ("" if ok else ": " + detail)))

    try:
        rules_path = os.path.join(TMP, "rules.json")
        with open(rules_path, "w", encoding="utf-8") as f:
            json.dump(RULES, f)

        two_lines = "Install from " + URL + "\nAsk " + HANDLE + " for help\n"

        # Test 1: no declaration - both lines are leaks
        d1 = make_folder(TMP, "f1", two_lines)
        r = run_scan(["--rules", rules_path, d1], env)
        leak_lines = [l for l in r.stdout.splitlines() if "notes.md:" in l]
        ok = (r.returncode == 12 and len(leak_lines) == 2
              and "FOUND 2 leak(s) in 1 file(s)" in r.stdout
              and "set aside" not in r.stdout)
        step(1, "no declaration: 2 leaks, exit 12", ok,
             "rc=%d out=%r" % (r.returncode, r.stdout))

        # Test 2: declared URL - only the bare handle stays a leak
        d2 = make_folder(TMP, "f2", two_lines, URL + "\n")
        r = run_scan(["--rules", rules_path, d2], env)
        leak_lines = [l for l in r.stdout.splitlines() if "notes.md:" in l]
        ok = (r.returncode == 12 and len(leak_lines) == 1
              and leak_lines[0].startswith("notes.md:2:")
              and "FOUND 1 leak(s) in 1 file(s)" in r.stdout
              and "1 public value match" in r.stdout)
        step(2, "declared URL: 1 leak (the bare handle), exit 12", ok,
             "rc=%d out=%r" % (r.returncode, r.stdout))

        # Test 3: only the URL line - clean, with the set-aside count
        d3 = make_folder(TMP, "f3", "Install from " + URL + "\n", URL + "\n")
        r = run_scan(["--rules", rules_path, d3], env)
        ok = (r.returncode == 0
              and "notes.md:" not in r.stdout
              and "CLEAN" in r.stdout
              and "1 public value match" in r.stdout)
        step(3, "URL line only: exit 0 + 1 public value match", ok,
             "rc=%d out=%r" % (r.returncode, r.stdout))

        # Test 4: a value shorter than 8 characters is ignored, with a warning
        d4 = make_folder(TMP, "f4", two_lines, HANDLE + "\n")
        r = run_scan(["--rules", rules_path, d4], env)
        leak_lines = [l for l in r.stdout.splitlines() if "notes.md:" in l]
        ok = (r.returncode == 12 and len(leak_lines) == 2
              and "public value too short, ignored: " + HANDLE in r.stderr)
        step(4, "short value ignored + warning on stderr", ok,
             "rc=%d out=%r err=%r" % (r.returncode, r.stdout, r.stderr))

        # Test 5: the same handle elsewhere on the same line stays a leak
        d5 = make_folder(TMP, "f5", "Install from " + URL + "; ask " + HANDLE + " now\n", URL + "\n")
        r = run_scan(["--rules", rules_path, d5], env)
        leak_lines = [l for l in r.stdout.splitlines() if "notes.md:" in l]
        ok = (r.returncode == 12 and len(leak_lines) == 1
              and leak_lines[0].startswith("notes.md:1:")
              and "1 public value match" in r.stdout)
        step(5, "handle outside the occurrence on the same line: still a leak", ok,
             "rc=%d out=%r" % (r.returncode, r.stdout))

    finally:
        shutil.rmtree(TMP, ignore_errors=True)
        shutil.rmtree(tmp_home, ignore_errors=True)

    n_pass = 0
    for ok, line in results:
        print(line)
        if ok:
            n_pass += 1

    print("E2E SCAN PUBLIC %d/5" % n_pass)
    sys.exit(0 if n_pass == 5 else 1)


if __name__ == "__main__":
    main()
