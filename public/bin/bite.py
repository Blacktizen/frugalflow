import sys, os, json, subprocess, tempfile, shutil, datetime

NOTICE = """NAME      bite.py - proves that an end-to-end suite bites, and writes the receipt the gate reads.
READS     the suite and the target named on the command line; the target is broken once, then restored byte for byte.
WRITES    suite<N>.json in --out, by default the bite folder next to the suite, only when the suite went green, red, then green.
EXAMPLE   python3 bite.py --suite 1 --e2e ../tests/e2e_contracts.py --target layers.py --find "exceeds ceiling" --replace "exceeds celing"
PITFALLS  2026-09-22 a receipt written by hand can be faked; only the procedure may write it.
          2026-09-22 a backup taken after the break restored the broken file; the original bytes now stay in memory and are compared after restore.
          2026-09-23 a same-size break was masked by stale bytecode; every run now gets a fresh PYTHONPYCACHEPREFIX.
"""

USAGE = "usage: bite.py --suite N --e2e SUITE --target FILE --find TEXT --replace TEXT [--out DIR] | --notice | --autotest"


def run_suite(e2e):
    cache = tempfile.mkdtemp()
    env = dict(os.environ)
    env["PYTHONPYCACHEPREFIX"] = cache
    rc = subprocess.run([sys.executable, e2e], capture_output=True, env=env).returncode
    shutil.rmtree(cache, ignore_errors=True)
    return rc


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()

    suite = None
    e2e = None
    target = None
    find = None
    replace = None
    out = None

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--suite":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            suite = argv[i + 1]
            i += 2
        elif arg == "--e2e":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            e2e = argv[i + 1]
            i += 2
        elif arg == "--target":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            target = argv[i + 1]
            i += 2
        elif arg == "--find":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            find = argv[i + 1]
            i += 2
        elif arg == "--replace":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            replace = argv[i + 1]
            i += 2
        elif arg == "--out":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            out = argv[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2

    if suite is None or e2e is None or target is None or find is None or replace is None:
        print(USAGE)
        return 2

    try:
        suite = int(suite)
    except ValueError:
        print(USAGE)
        return 2

    if out is None:
        out = os.path.join(os.path.dirname(os.path.abspath(e2e)), "bite")

    if not os.path.isfile(e2e):
        print("missing file: " + e2e)
        return 2
    if not os.path.isfile(target):
        print("missing file: " + target)
        return 2

    if find == replace:
        print("find and replace are identical")
        return 2

    with open(target, "rb") as fh:
        original = fh.read()
    f = find.encode("utf-8")
    n = original.count(f)
    if n == 0:
        print("text to break not found in " + target)
        return 2
    if n > 1:
        print("text to break found " + str(n) + " times in " + target + ", it must be unique")
        return 2

    green = run_suite(e2e)
    print("GREEN rc=" + str(green))

    broken = original.replace(f, replace.encode("utf-8"), 1)
    with open(target, "wb") as fh:
        fh.write(broken)
    try:
        red = run_suite(e2e)
    finally:
        with open(target, "wb") as fh:
            fh.write(original)
    print("RED rc=" + str(red))

    with open(target, "rb") as fh:
        restored = fh.read()
    if restored != original:
        print("RESTORE FAILED: " + target + " differs from its original")
        return 9

    again = run_suite(e2e)
    print("RESTORED rc=" + str(again))

    if green != 0:
        print("NOT GREEN on sound code, no receipt")
        return 10
    if red == 0:
        print("DOES NOT BITE: e2e stayed green on broken code, no receipt")
        return 10
    if again != 0:
        print("NOT GREEN after restore, no receipt")
        return 10

    os.makedirs(out, exist_ok=True)
    receipt_path = os.path.join(out, "suite" + str(suite) + ".json")
    receipt = {
        "suite": suite,
        "green_rc": green,
        "red_rc": red,
        "restored_rc": again,
        "broken": os.path.basename(target) + ": " + find + " -> " + replace,
        "date": datetime.date.today().isoformat()
    }
    with open(receipt_path, "w", encoding="utf-8") as fh:
        json.dump(receipt, fh)
    print("BITES: receipt written to " + receipt_path)
    return 0


def autotest():
    D = tempfile.mkdtemp()
    with open(os.path.join(D, "target.txt"), "w", encoding="utf-8") as fh:
        fh.write("VALUE = 1\n")
    with open(os.path.join(D, "e2e_ok.py"), "w", encoding="utf-8") as fh:
        fh.write('import os, sys\nhere = os.path.dirname(os.path.abspath(__file__))\ntext = open(os.path.join(here, "target.txt"), encoding="utf-8").read()\nsys.exit(0 if "VALUE = 1" in text else 1)\n')
    with open(os.path.join(D, "e2e_soft.py"), "w", encoding="utf-8") as fh:
        fh.write("import sys\nsys.exit(0)\n")
    with open(os.path.join(D, "mod.py"), "w", encoding="utf-8") as fh:
        fh.write("VALUE = 1\n")
    with open(os.path.join(D, "e2e_mod.py"), "w", encoding="utf-8") as fh:
        fh.write('import os, sys\nsys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))\nimport mod\nsys.exit(0 if mod.VALUE == 1 else 1)\n')

    self = os.path.abspath(__file__)
    all_pass = True

    # Proof 1
    args = ["--suite", "7", "--e2e", os.path.join(D, "e2e_ok.py"),
            "--target", os.path.join(D, "target.txt"),
            "--find", "VALUE = 1", "--replace", "VALUE = 2",
            "--out", os.path.join(D, "bite")]
    r = subprocess.run([sys.executable, self] + args, capture_output=True, text=True)
    ok = r.returncode == 0
    if ok:
        p = os.path.join(D, "bite", "suite7.json")
        if not os.path.isfile(p):
            ok = False
        else:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("green_rc") != 0 or data.get("red_rc") != 1 or data.get("restored_rc") != 0 or data.get("suite") != 7:
                ok = False
    with open(os.path.join(D, "target.txt"), "r", encoding="utf-8") as fh:
        if fh.read() != "VALUE = 1\n":
            ok = False
    if ok:
        print("PASS proof 1: expected code 0, receipt green=0 red=1 restored=0 suite=7, target restored; got code " + str(r.returncode))
    else:
        print("FAIL proof 1: expected code 0, receipt green=0 red=1 restored=0 suite=7, target restored; got code " + str(r.returncode))
        all_pass = False

    # Proof 2
    args = ["--suite", "7", "--e2e", os.path.join(D, "e2e_soft.py"),
            "--target", os.path.join(D, "target.txt"),
            "--find", "VALUE = 1", "--replace", "VALUE = 2",
            "--out", os.path.join(D, "bite2")]
    r = subprocess.run([sys.executable, self] + args, capture_output=True, text=True)
    lines = r.stdout.splitlines()
    ok = r.returncode == 10
    if ok and "DOES NOT BITE: e2e stayed green on broken code, no receipt" not in lines:
        ok = False
    if ok and os.path.isfile(os.path.join(D, "bite2", "suite7.json")):
        ok = False
    with open(os.path.join(D, "target.txt"), "r", encoding="utf-8") as fh:
        if fh.read() != "VALUE = 1\n":
            ok = False
    if ok:
        print("PASS proof 2: expected code 10, no receipt, target restored; got code " + str(r.returncode))
    else:
        print("FAIL proof 2: expected code 10, no receipt, target restored; got code " + str(r.returncode))
        all_pass = False

    # Proof 3
    args = ["--suite", "7", "--e2e", os.path.join(D, "e2e_ok.py"),
            "--target", os.path.join(D, "target.txt"),
            "--find", "ABSENT", "--replace", "VALUE = 2",
            "--out", os.path.join(D, "bite3")]
    r = subprocess.run([sys.executable, self] + args, capture_output=True, text=True)
    lines = r.stdout.splitlines()
    ok3a = r.returncode == 2
    if ok3a and not any(l.startswith("text to break not found in ") for l in lines):
        ok3a = False
    with open(os.path.join(D, "target.txt"), "r", encoding="utf-8") as fh:
        if fh.read() != "VALUE = 1\n":
            ok3a = False

    args = ["--suite", "7", "--e2e", os.path.join(D, "nope.py"),
            "--target", os.path.join(D, "target.txt"),
            "--find", "VALUE = 1", "--replace", "VALUE = 2",
            "--out", os.path.join(D, "bite3")]
    r2 = subprocess.run([sys.executable, self] + args, capture_output=True, text=True)
    lines2 = r2.stdout.splitlines()
    ok3b = r2.returncode == 2
    if ok3b and not any(l.startswith("missing file: ") for l in lines2):
        ok3b = False

    ok = ok3a and ok3b
    if ok:
        print("PASS proof 3: expected code 2 (absent text) and code 2 (missing file); got codes " + str(r.returncode) + " and " + str(r2.returncode))
    else:
        print("FAIL proof 3: expected code 2 (absent text) and code 2 (missing file); got codes " + str(r.returncode) + " and " + str(r2.returncode))
        all_pass = False

    # Proof 4
    subprocess.run([sys.executable, os.path.join(D, "e2e_mod.py")], capture_output=True)
    args = ["--suite", "8", "--e2e", os.path.join(D, "e2e_mod.py"),
            "--target", os.path.join(D, "mod.py"),
            "--find", "VALUE = 1", "--replace", "VALUE = 2",
            "--out", os.path.join(D, "bite4")]
    r = subprocess.run([sys.executable, self] + args, capture_output=True, text=True)
    ok = r.returncode == 0
    if ok:
        p = os.path.join(D, "bite4", "suite8.json")
        if not os.path.isfile(p):
            ok = False
        else:
            with open(p, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            if data.get("red_rc") != 1 or data.get("restored_rc") != 0:
                ok = False
    with open(os.path.join(D, "mod.py"), "r", encoding="utf-8") as fh:
        if fh.read() != "VALUE = 1\n":
            ok = False
    if ok:
        print("PASS proof 4: expected code 0, red_rc 1, restored_rc 0, mod.py restored; got code " + str(r.returncode))
    else:
        print("FAIL proof 4: expected code 0, red_rc 1, restored_rc 0, mod.py restored; got code " + str(r.returncode))
        all_pass = False

    # Proof 5
    r = subprocess.run([sys.executable, self, "--notice"], capture_output=True, text=True)
    ok = r.returncode == 0 and r.stdout.startswith("NAME      bite.py")
    if ok:
        print("PASS proof 5: expected code 0, notice starts with 'NAME      bite.py'; got code " + str(r.returncode))
    else:
        print("FAIL proof 5: expected code 0, notice starts with 'NAME      bite.py'; got code " + str(r.returncode))
        all_pass = False

    shutil.rmtree(D, ignore_errors=True)
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bite", sys.argv[1:])
