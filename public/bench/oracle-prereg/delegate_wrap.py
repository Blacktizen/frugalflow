import sys
import os
import subprocess
import tempfile
import shutil


def run_delegate(args):
    real = os.environ.get("FRUGAL_REAL_DELEGATE", "")
    if not real:
        sys.stderr.write("FRUGAL_REAL_DELEGATE missing\n")
        return 2

    cmd = [sys.executable, real] + args
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1200)
    except subprocess.TimeoutExpired:
        return 124

    target_line = None
    for line in proc.stderr.splitlines():
        s = line.strip()
        if s.startswith("[qwen") and s.endswith("tokens]"):
            target_line = s

    if target_line is not None:
        sys.stdout.write(target_line + "\n")

    sys.stdout.write(proc.stdout)
    return proc.returncode


def autotest():
    tmpdir = tempfile.mkdtemp()
    try:
        fake_path = os.path.join(tmpdir, "fake_real.py")
        with open(fake_path, "w") as f:
            f.write("import sys\n"
                    "sys.stderr.write(\"noise\\n[qwen - 11->22 tokens]\\n\")\n"
                    "sys.stdout.write(\"ANSWER\\nTESTS: GREEN\\n\")\n"
                    "sys.exit(int(sys.argv[1]) if len(sys.argv) > 1 else 0)\n")

        passed = 0

        env1 = os.environ.copy()
        env1["FRUGAL_REAL_DELEGATE"] = fake_path
        r1 = subprocess.run(
            [sys.executable, __file__],
            capture_output=True, text=True, env=env1
        )
        lines1 = r1.stdout.splitlines()
        if (r1.returncode == 0
                and len(lines1) == 3
                and lines1[0] == "[qwen - 11->22 tokens]"
                and lines1[1] == "ANSWER"
                and lines1[2] == "TESTS: GREEN"):
            print("PASS 1")
            passed += 1
        else:
            print("FAIL 1")

        env2 = os.environ.copy()
        env2["FRUGAL_REAL_DELEGATE"] = fake_path
        r2 = subprocess.run(
            [sys.executable, __file__, "5"],
            capture_output=True, text=True, env=env2
        )
        if r2.returncode == 5:
            print("PASS 2")
            passed += 1
        else:
            print("FAIL 2")

        env3 = os.environ.copy()
        env3.pop("FRUGAL_REAL_DELEGATE", None)
        r3 = subprocess.run(
            [sys.executable, __file__],
            capture_output=True, text=True, env=env3
        )
        if r3.returncode == 2:
            print("PASS 3")
            passed += 1
        else:
            print("FAIL 3")

        print("AUTOTEST {}/3".format(passed))
        return 0 if passed == 3 else 1
    finally:
        shutil.rmtree(tmpdir)


def main():
    argv = sys.argv[1:]
    if "--autotest" in argv:
        sys.exit(autotest())
    rc = run_delegate(argv)
    sys.exit(rc)


if __name__ == "__main__":
    main()
