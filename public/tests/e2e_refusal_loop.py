"""End-to-end test: the refusal loop of a user project, from the mount to the commit."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.normpath(os.path.join(HERE, "..", "bin"))

GOOD_SRC = (
    "import sys\n"
    "import os\n"
    "sys.path.insert(0, os.environ[\"FF_BIN\"])\n"
    "import exit_log\n"
    "def main(argv):\n"
    "    if argv and argv[0] == \"--bad\":\n"
    "        print(\"REFUSED: bad\")\n"
    "        return 2\n"
    "    print(\"OK\")\n"
    "    return 0\n"
    "if __name__ == \"__main__\":\n"
    "    exit_log.run(main, \"good\", sys.argv[1:])\n"
)

JUST_BENCH = json.dumps([
    {"id": "g-ok", "tool": "good", "argv": [], "expected": "pass"},
    {"id": "g-bad", "tool": "good", "argv": ["--bad"], "expected": "refuse"},
])

GIT_ENV = {
    "GIT_AUTHOR_NAME": "e2e refusal loop",
    "GIT_AUTHOR_EMAIL": "e2e-refusal-loop@invalid",
    "GIT_COMMITTER_NAME": "e2e refusal loop",
    "GIT_COMMITTER_EMAIL": "e2e-refusal-loop@invalid",
}


def make_env(home):
    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home
    env["FF_BIN"] = BIN
    env.update(GIT_ENV)
    return env


def run(cmd, cwd=None, env=None):
    return subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True)


def git(project, env, *args):
    return run(["git"] + list(args), cwd=project, env=env)


def write_text(path, text):
    with open(path, "w", encoding="utf-8", newline="") as handle:
        handle.write(text)


def step_a(tmp, env):
    proc = run([sys.executable, os.path.join(BIN, "frugalflow.py"),
                "new-project", "demo", "--root", tmp], env=env)
    ok = proc.returncode == 0
    expected = "new-project demo exits 0"
    got = "code=" + str(proc.returncode) + " first=" + repr(proc.stdout.splitlines()[:1])
    return ok, expected, got


def step_b(project, env):
    write_text(os.path.join(project, "bin", "good.py"), GOOD_SRC)
    write_text(os.path.join(project, "bench", "cases.json"), JUST_BENCH + "\n")
    add = git(project, env, "add", "-A")
    commit = git(project, env, "commit", "-m", "mount good with its bench")
    notice = run([sys.executable, os.path.join(BIN, "refusal_loop.py"), "--notice"], env=env)
    out = commit.stdout + commit.stderr
    gate_line = "COMMIT ALLOWED" in out
    notice_line = "COMMIT ALLOWED" in notice.stdout
    ok = add.returncode == 0 and commit.returncode == 0 and gate_line and notice_line
    expected = ("commit of a logged tool with its bench exits 0, the gate prints "
                "COMMIT ALLOWED and the notice states COMMIT ALLOWED")
    got = ("add=" + str(add.returncode) + " commit=" + str(commit.returncode)
           + " gate_line=" + str(gate_line) + " notice_line=" + str(notice_line))
    return ok, expected, got


def step_c(project, home, env):
    proc = run([sys.executable, os.path.join(project, "bin", "good.py"), "--bad"],
               cwd=project, env=env)
    logged = False
    log_path = os.path.join(home, "blocks", "good.jsonl")
    if os.path.isfile(log_path):
        with open(log_path, "r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    record = json.loads(line)
                except ValueError:
                    continue
                if isinstance(record, dict) and record.get("rule") == "exit_2":
                    logged = True
    ok = proc.returncode == 2 and logged
    expected = "good --bad exits 2 and blocks/good.jsonl holds an exit_2 line"
    got = "code=" + str(proc.returncode) + " exit_2_logged=" + str(logged)
    return ok, expected, got


def step_d(project, env):
    proc = run([sys.executable, os.path.join(BIN, "refusal_loop.py"),
                "todo", "--project", project], env=env)
    todo = ""
    todo_path = os.path.join(project, "vault", "todo.md")
    if os.path.isfile(todo_path):
        with open(todo_path, "r", encoding="utf-8") as handle:
            todo = handle.read()
    ok = (proc.returncode == 0 and "TODO 1 new refusal(s)" in proc.stdout
          and "refusal" in todo and "good exit_2" in todo)
    expected = "todo prints TODO 1 new refusal(s) and todo.md holds refusal and good exit_2"
    got = ("code=" + str(proc.returncode) + " out=" + repr(proc.stdout.splitlines()[:1])
           + " refusal=" + str("refusal" in todo) + " good_exit_2=" + str("good exit_2" in todo))
    return ok, expected, got


def step_e(project, env):
    cases = json.loads(JUST_BENCH)
    cases.append({"id": "g-bad-pass", "tool": "good", "argv": ["--bad"], "expected": "pass"})
    write_text(os.path.join(project, "bench", "cases.json"), json.dumps(cases) + "\n")
    add = git(project, env, "add", "-A")
    commit = git(project, env, "commit", "-m", "regression: a false refusal case")
    out = commit.stdout + commit.stderr
    ok = add.returncode == 0 and commit.returncode != 0 and "FALSE REFUSAL g-bad-pass" in out
    expected = "commit with the false refusal case exits non-zero with FALSE REFUSAL g-bad-pass"
    got = ("add=" + str(add.returncode) + " commit=" + str(commit.returncode)
           + " false_refusal=" + str("FALSE REFUSAL g-bad-pass" in out))
    return ok, expected, got


def step_f(project, env):
    write_text(os.path.join(project, "bench", "cases.json"), JUST_BENCH + "\n")
    add = git(project, env, "add", "-A")
    commit = git(project, env, "commit", "-m", "drop the false refusal case")
    out = commit.stdout + commit.stderr
    ok = add.returncode == 0 and commit.returncode == 0 and "COMMIT ALLOWED" in out
    expected = "commit after dropping the case exits 0 with COMMIT ALLOWED"
    got = ("add=" + str(add.returncode) + " commit=" + str(commit.returncode)
           + " gate_line=" + str("COMMIT ALLOWED" in out))
    return ok, expected, got


def main():
    tmp = tempfile.mkdtemp()
    try:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        project = os.path.join(tmp, "demo")
        env = make_env(home)
        steps = [
            ("a", lambda: step_a(tmp, env)),
            ("b", lambda: step_b(project, env)),
            ("c", lambda: step_c(project, home, env)),
            ("d", lambda: step_d(project, env)),
            ("e", lambda: step_e(project, env)),
            ("f", lambda: step_f(project, env)),
        ]
        results = []
        for label, fn in steps:
            try:
                ok, expected, got = fn()
            except Exception as error:
                ok, expected, got = False, "the step runs", "exception: " + str(error)
            results.append((label, bool(ok), expected, got))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    passed = 0
    for label, ok, expected, got in results:
        if ok:
            passed += 1
            print("PASS " + label)
        else:
            print("FAIL {}: expected {}, got {}".format(label, expected, got))
    print("E2E REFUSAL LOOP: {}/6".format(passed))
    return 0 if passed == 6 else 1


if __name__ == "__main__":
    sys.exit(main())
