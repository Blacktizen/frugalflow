import sys
import os
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from notice_rules import check


def inspect(path):
    tmpdir = tempfile.mkdtemp()
    env = dict(os.environ)
    env["HOME"] = tmpdir
    try:
        result = subprocess.run(
            [sys.executable, os.path.abspath(path), "--notice"],
            cwd=tmpdir,
            env=env,
            capture_output=True,
            text=True,
            timeout=20,
        )
    except subprocess.TimeoutExpired:
        defects = ["--notice did not finish within 20 s"]
    else:
        defects = []
        if result.returncode != 0:
            defects.append("--notice exit code " + str(result.returncode))
        entries = os.listdir(tmpdir)
        if entries:
            defects.append("--notice wrote to disk: " + ", ".join(sorted(entries)))
        defects.extend(check(result.stdout, os.path.basename(path)))
    shutil.rmtree(tmpdir, ignore_errors=True)
    return defects


def main(argv):
    if not argv:
        print("usage: notice_check.py TOOL.py [TOOL.py ...] | --notice | --autotest")
        sys.exit(2)

    if argv[0] == "--notice":
        print("NAME      notice_check.py - refuses a tool whose --notice output breaks the contract.")
        print("READS     the tool files named on the command line; runs each with --notice in an empty directory.")
        print("WRITES    nothing: one OK or NO line per tool, then NOTICES OK or NOTICES REFUSED.")
        print("EXAMPLE   python3 notice_check.py notice_rules.py")
        print("PITFALLS  2026-09-22 a tool was counted as documented because the word NOTICE: appeared in it.")
        print("          2026-09-23 a --notice that writes a file is refused: a notice must not run anything.")
        sys.exit(0)

    if argv[0] == "--autotest":
        autotest()
        return

    refused = 0
    for p in argv:
        if not os.path.isfile(p):
            print("missing file: " + p)
            sys.exit(2)
        defects = inspect(p)
        name = os.path.basename(p)
        if not defects:
            print("OK " + name)
        else:
            for d in defects:
                print("NO " + name + ": " + d)
            refused += 1
    total = len(argv)
    if refused == 0:
        print("NOTICES OK " + str(total))
        sys.exit(0)
    else:
        print("NOTICES REFUSED " + str(refused) + " of " + str(total))
        sys.exit(7)


def autotest():
    tmpdir = tempfile.mkdtemp()
    try:
        good_path = os.path.join(tmpdir, "good.py")
        silent_path = os.path.join(tmpdir, "silent.py")
        writer_path = os.path.join(tmpdir, "writer.py")
        nope_path = os.path.join(tmpdir, "nope.py")

        with open(good_path, "w", encoding="utf-8") as f:
            f.write('import sys\nif "--notice" in sys.argv:\n    print("NAME      good.py - prints hello.")\n    print("READS     nothing.")\n    print("WRITES    nothing.")\n    print("EXAMPLE   python3 good.py")\n    print("PITFALLS  2026-09-23 none recorded yet.")\n')

        with open(silent_path, "w", encoding="utf-8") as f:
            f.write("import sys\n")

        with open(writer_path, "w", encoding="utf-8") as f:
            f.write('import sys\nif "--notice" in sys.argv:\n    open("trace.txt", "w").write("x")\n    print("NAME      writer.py - prints hello.")\n    print("READS     nothing.")\n    print("WRITES    nothing.")\n    print("EXAMPLE   python3 writer.py")\n    print("PITFALLS  2026-09-23 none recorded yet.")\n')

        me = os.path.abspath(__file__)
        all_pass = True

        r = subprocess.run([sys.executable, me, good_path], capture_output=True, text=True)
        lines = [l.rstrip() for l in r.stdout.splitlines()]
        ok = (r.returncode == 0 and "OK good.py" in lines and "NOTICES OK 1" in lines)
        if ok:
            print("PASS test 1: rc=0, 'OK good.py', 'NOTICES OK 1' | got rc=" + str(r.returncode))
        else:
            print("FAIL test 1: expected rc=0, 'OK good.py', 'NOTICES OK 1' | got rc=" + str(r.returncode) + " stdout=" + repr(r.stdout))
            all_pass = False

        r = subprocess.run([sys.executable, me, silent_path], capture_output=True, text=True)
        lines = [l.rstrip() for l in r.stdout.splitlines()]
        ok = (r.returncode == 7 and "NO silent.py: empty notice" in lines and "NOTICES REFUSED 1 of 1" in lines)
        if ok:
            print("PASS test 2: rc=7, 'NO silent.py: empty notice', 'NOTICES REFUSED 1 of 1' | got rc=" + str(r.returncode))
        else:
            print("FAIL test 2: expected rc=7, 'NO silent.py: empty notice', 'NOTICES REFUSED 1 of 1' | got rc=" + str(r.returncode) + " stdout=" + repr(r.stdout))
            all_pass = False

        r = subprocess.run([sys.executable, me, writer_path], capture_output=True, text=True)
        lines = [l.rstrip() for l in r.stdout.splitlines()]
        ok = (r.returncode == 7 and "NO writer.py: --notice wrote to disk: trace.txt" in lines)
        if ok:
            print("PASS test 3: rc=7, 'NO writer.py: --notice wrote to disk: trace.txt' | got rc=" + str(r.returncode))
        else:
            print("FAIL test 3: expected rc=7, 'NO writer.py: --notice wrote to disk: trace.txt' | got rc=" + str(r.returncode) + " stdout=" + repr(r.stdout))
            all_pass = False

        r = subprocess.run([sys.executable, me, nope_path], capture_output=True, text=True)
        lines = [l.rstrip() for l in r.stdout.splitlines()]
        ok = (r.returncode == 2 and any(l.startswith("missing file: ") for l in lines))
        if ok:
            print("PASS test 4: rc=2, 'missing file: ' | got rc=" + str(r.returncode))
        else:
            print("FAIL test 4: expected rc=2, 'missing file: ' | got rc=" + str(r.returncode) + " stdout=" + repr(r.stdout))
            all_pass = False

        r = subprocess.run([sys.executable, me, "--notice"], capture_output=True, text=True)
        ok = (r.returncode == 0 and check(r.stdout, "notice_check.py") == [])
        if ok:
            print("PASS test 5: rc=0, check(stdout,'notice_check.py')==[] | got rc=" + str(r.returncode))
        else:
            print("FAIL test 5: expected rc=0, check==[] | got rc=" + str(r.returncode) + " check=" + repr(check(r.stdout, "notice_check.py")))
            all_pass = False

        sys.exit(0 if all_pass else 1)
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "notice_check", sys.argv[1:])
