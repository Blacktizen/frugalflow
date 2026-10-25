import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anon_rules
import anon_core
import scan_files

NOTICE = (
    "NAME      scan_cmd.py - the frugalflow scan subcommand: looks for secrets and private data in a folder or a git repo, with no model.\n"
    "READS     the folder or file given; the rules file given by --rules, else FRUGALFLOW_HOME/anonymization.json, else ~/.frugalflow/anonymization.json, else the built-in rules; with --staged, the git index.\n"
    "WRITES    nothing: one line per leak with file, line, type and label, never the text found. Exit 0 clean, 12 leak found, 2 bad usage or path, 13 bad rules.\n"
    "EXAMPLE   python3 scan_cmd.py ./my-project\n"
    "PITFALLS  2026-10-25 printing the text found would copy the leak into CI logs; only its place, type and label are printed.\n"
    "          2026-10-25 a scan that finds no file used to print CLEAN; a path with nothing to read still says 0 files, so an empty scan is visible."
)

USAGE = "usage: scan_cmd.py [PATH] [--staged] [--quiet] [--rules FILE] | --notice | --autotest"

KEY_LINE = "api" + "_key = " + chr(34) + "abcd1234efgh5678ijkl" + chr(34) + "\n"
CLEAN_LINE = "def add(a, b):\n    return a + b\n"
PRIVATE_RULES = {"anonymizable": [{"pattern": "\\bPlimsoq\\b", "label": "person", "tag": "PERSON"}]}
PRIVATE_LINE = "hello Plimsoq\n"


def _load_rules_file(path):
    if not os.path.isfile(path):
        print("NO RULES FILE " + path)
        return None, 13
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("NO RULES " + path + ": not valid JSON")
        return None, 13
    return doc, 0


def main(argv):
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    path = None
    staged = False
    quiet = False
    rules_file = None
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--staged":
            staged = True
            i += 1
        elif arg == "--quiet":
            quiet = True
            i += 1
        elif arg == "--rules":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            rules_file = argv[i + 1]
            i += 2
        elif arg.startswith("--"):
            print(USAGE)
            return 2
        else:
            positional.append(arg)
            i += 1

    if len(positional) > 1:
        print(USAGE)
        return 2
    path = positional[0] if positional else "."

    # 1. Rules
    if rules_file is not None:
        doc, code = _load_rules_file(rules_file)
        if code != 0:
            return code
    else:
        home = os.environ.get("FRUGALFLOW_HOME", "")
        if not home:
            home = os.path.expanduser("~/.frugalflow")
        candidate = os.path.join(home, "anonymization.json")
        if os.path.isfile(candidate):
            doc, code = _load_rules_file(candidate)
            if code != 0:
                return code
        else:
            doc = {}

    anonymizable, irreducible, errors = anon_rules.load(doc)
    if errors:
        for err in errors:
            print("NO RULES " + err)
        return 13

    # 2. Files
    try:
        files = scan_files.list_files(path, staged=staged)
    except ValueError as exc:
        print("NO PATH " + str(exc))
        return 2

    # 3. Analysis
    is_dir = os.path.isdir(path)
    n_files = len(files)
    all_findings = []
    file_with_leak = 0
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        hits = anon_core.find(text, anonymizable, irreducible)
        if hits:
            file_with_leak += 1
        for line, kind, label, _excerpt in hits:
            all_findings.append((fpath, line, kind, label))

    # 4. Report
    h = len(all_findings)
    if not quiet:
        for fpath, line, kind, label in all_findings:
            if is_dir:
                rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(path))
            else:
                rel = path
            typ = "secret" if kind == "irreducible" else "private data"
            print(rel + ":" + str(line) + ": " + typ + " " + label)

    # 5. Summary and code
    if h == 0:
        print("CLEAN: " + str(n_files) + " file(s) scanned, no leak found")
        return 0
    print("FOUND " + str(h) + " leak(s) in " + str(file_with_leak) + " file(s)")
    if not quiet:
        print("Fix: remove the value and load it from an environment variable, then scan again.")
        print("False positive? Keep that file out of the scanned folder or list it in .gitignore.")
    return 12


def _autotest():
    tmp = tempfile.mkdtemp()
    try:
        leaky = os.path.join(tmp, "leaky")
        os.mkdir(leaky)
        with open(os.path.join(leaky, "leak.py"), "w", encoding="utf-8") as f:
            f.write(KEY_LINE)

        clean = os.path.join(tmp, "clean")
        os.mkdir(clean)
        with open(os.path.join(clean, "ok.py"), "w", encoding="utf-8") as f:
            f.write(CLEAN_LINE)

        priv = os.path.join(tmp, "priv")
        os.mkdir(priv)
        with open(os.path.join(priv, "p.txt"), "w", encoding="utf-8") as f:
            f.write(PRIVATE_LINE)

        rules_path = os.path.join(tmp, "rules.json")
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write("[]")

        private_rules_path = os.path.join(tmp, "private_rules.json")
        with open(private_rules_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(PRIVATE_RULES))

        env = os.environ.copy()
        env["HOME"] = tmp
        env["USERPROFILE"] = tmp
        env.pop("FRUGALFLOW_HOME", None)
        for key in list(env.keys()):
            if key.startswith("GIT_"):
                del env[key]

        def run(args):
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__)] + args,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            return proc.returncode, proc.stdout

        passed = 0
        self_path = os.path.abspath(__file__)

        # Test 1: leaky dir
        rc, out = run([leaky])
        ok = (rc == 12
              and "leak.py:1:" in out
              and "secret credential in clear" in out
              and "FOUND 1 leak(s) in 1 file(s)" in out
              and "abcd1234efgh5678ijkl" not in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 1: exit 12 + leak.py:1: + FOUND 1",
              "got rc=" + str(rc))

        # Test 2: clean dir
        rc, out = run([clean])
        ok = (rc == 0
              and "CLEAN: 1 file(s) scanned, no leak found" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 2: exit 0 + CLEAN: 1 file(s)",
              "got rc=" + str(rc))

        # Test 3: missing path
        rc, out = run([os.path.join(tmp, "nonexistent")])
        ok = (rc == 2 and "NO PATH " in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 3: exit 2 + NO PATH",
              "got rc=" + str(rc))

        # Test 4: bad rules file + unknown option
        rc1, out1 = run(["--rules", rules_path, clean])
        rc2, out2 = run(["--bogus"])
        ok = (rc1 == 13 and rc2 == 2 and "usage: scan_cmd.py" in out2)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 4: exit 13 + exit 2 + usage",
              "got rc1=" + str(rc1) + " rc2=" + str(rc2))

        # Test 5: private rules
        rc, out = run(["--rules", private_rules_path, priv])
        ok = (rc == 12
              and "p.txt:1: private data person" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 5: exit 12 + private data person",
              "got rc=" + str(rc))

        print("AUTOTEST " + str(passed) + "/5")
        return 0 if passed == 5 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
