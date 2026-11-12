import os
import sys
import subprocess
import tempfile
import shutil

NOTICE = (
    "NAME      e2e_cli_five.py - end-to-end test of the five visible commands: --help shows init, resume, delegate, close, doctor and run; the rest still works behind run or under its old name.\n"
    "READS     the tools in ../bin; it builds a temporary project with new-project and a temporary HOME.\n"
    "WRITES    only in temporary folders, always removed. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_cli_five.py\n"
    "PITFALLS  2026-11-12 --help listed 17 commands and a newcomer could not pick the five that matter; the visible set is fixed here so it cannot drift back.\n"
)

BIN_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin"
)
FF = os.path.join(BIN_DIR, "frugalflow.py")

VISIBLE = ["close", "delegate", "doctor", "init", "resume", "run"]


def make_env(home_path):
    env = {}
    for key, val in os.environ.items():
        if key.startswith("GIT_") or key == "CLAUDECODE" or key.startswith("FRUGALFLOW_"):
            continue
        env[key] = val
    env["HOME"] = home_path
    env["FRUGALFLOW_HOME"] = os.path.join(home_path, "ff")
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def run_ff(args, env, cwd=None):
    result = subprocess.run(
        [sys.executable, FF] + args,
        env=env,
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=120,
        stdin=subprocess.DEVNULL,
    )
    return result.returncode, result.stdout, result.stderr


def visible_commands(text):
    """Return the command names --help shows: lines that start with two spaces and a lowercase name."""
    result = []
    for line in text.splitlines()[1:]:
        if line.startswith("  options"):
            continue
        if len(line) >= 3 and line[0] == " " and line[1] == " " and line[2].islower():
            words = line.split()
            if words:
                result.append(words[0])
    return result


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        print(NOTICE)
        return 0
    if len(sys.argv) > 1:
        print("usage: e2e_cli_five.py [--notice]")
        return 2

    tmp = tempfile.mkdtemp()
    env = make_env(os.path.join(tmp, "home"))
    os.makedirs(env["FRUGALFLOW_HOME"], exist_ok=True)
    failed = 0

    def step(num, expected, ok, detail):
        nonlocal failed
        if ok:
            print("PASS step %d: %s" % (num, expected))
        else:
            print("FAIL step %d: expected %s, got %s" % (num, expected, detail))
            failed += 1

    try:
        # Step 1: --help shows exactly the six entries; no argument prints the same usage with exit 2.
        rc, out, err = run_ff(["--help"], env)
        names = sorted(visible_commands(out))
        step(1, "--help exit 0 with exactly " + str(VISIBLE),
             rc == 0 and names == VISIBLE, "rc=%d names=%r" % (rc, names))

        rc2, out2, err2 = run_ff([], env)
        step(2, "no argument exit 2 with the same usage",
             rc2 == 2 and out2.splitlines()[0] == out.splitlines()[0],
             "rc=%d first=%r" % (rc2, out2.splitlines()[0] if out2 else ""))

        # Step 3: help all lists every old command plus delegate and close.
        rc, out, err = run_ff(["help", "all"], env)
        missing = [w for w in ("scan", "new-project", "config", "notes", "delegate", "close")
                   if w not in out]
        step(3, "help all exit 0 listing scan, new-project, config, notes, delegate, close",
             rc == 0 and not missing, "rc=%d missing=%r" % (rc, missing))

        # Step 4: delegate without argument is refused with exit 2, without launching delegate.py.
        rc, out, err = run_ff(["delegate"], env)
        step(4, "delegate without argument exit 2 with the delegate usage line",
             rc == 2 and out.startswith("usage: frugalflow delegate")
             and "delegate.py" not in out,
             "rc=%d out=%r" % (rc, out[:80]))

        # Step 5: delegate --notice prints the notice of delegate.py with exit 0.
        rc, out, err = run_ff(["delegate", "--notice"], env)
        step(5, "delegate --notice exit 0 with the delegate.py notice",
             rc == 0 and out.startswith("NAME      delegate.py"),
             "rc=%d out=%r" % (rc, out[:80]))

        # Step 6: close without a vault is refused with exit 3.
        rc, out, err = run_ff(["close", "--vault", os.path.join(tmp, "absent")], env)
        step(6, "close without a vault exit 3 with NO VAULT",
             rc == 3 and "NO VAULT" in out, "rc=%d out=%r" % (rc, out[:80]))

        # Step 7: new-project, then close on its vault: exit 0, VAULT OK, the sealed line.
        root7 = os.path.join(tmp, "root")
        os.makedirs(root7, exist_ok=True)
        rc1, out1, err1 = run_ff(["new-project", "demo", "--root", root7], env)
        rc2, out2, err2 = run_ff(["close", "--vault", os.path.join(root7, "demo", "vault")], env)
        step(7, "new-project exit 0, then close exit 0 with VAULT OK and sealed",
             rc1 == 0 and rc2 == 0 and "VAULT OK" in out2
             and "sealed" in out2 and "frugalflow resume" in out2,
             "rc_new=%d rc_close=%d out=%r" % (rc1, rc2, out2[-120:]))

        # Step 8: scan keeps its old name and works behind run, on an empty folder.
        empty = os.path.join(tmp, "empty")
        os.makedirs(empty, exist_ok=True)
        rc1, out1, err1 = run_ff(["scan", empty], env)
        rc2, out2, err2 = run_ff(["run", "scan", empty], env)
        step(8, "scan and run scan on an empty folder exit 0 with CLEAN",
             rc1 == 0 and "CLEAN" in out1 and rc2 == 0 and "CLEAN" in out2,
             "rc_scan=%d rc_run=%d out1=%r out2=%r" % (rc1, rc2, out1[:60], out2[:60]))

        # Step 9: run does not change a setting: run off is refused with exit 2.
        rc, out, err = run_ff(["run", "off"], env)
        step(9, "run off exit 2 with the refusal to change a setting through run",
             rc == 2 and "run does not change settings: type frugalflow off yourself, in your own terminal." in out,
             "rc=%d out=%r" % (rc, out[:120]))

        # Step 10: off stays refused under CLAUDECODE without a terminal.
        env10 = dict(env)
        env10["CLAUDECODE"] = "1"
        rc, out, err = run_ff(["off"], env10)
        step(10, "off with CLAUDECODE=1 refused with exit 3",
             rc == 3 and "Refused" in out, "rc=%d out=%r" % (rc, out[:120]))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    if failed:
        print("E2E CLI FIVE %d step(s) failed" % failed)
        return 1
    print("E2E CLI FIVE ALL STEPS PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
