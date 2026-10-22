import sys
import os
import json
import shutil
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anon_rules
import anon_core

NOTICE = (
    "NAME      anon_check.py - refuses files that carry a private name, a personal path, an address or a secret.\n"
    "READS     the pattern file: --rules, else FRUGALFLOW_HOME/anonymization.json, else ~/.frugalflow/anonymization.json; then the files after --scan.\n"
    "WRITES    nothing: one line per hit, file and line and kind, never the text found.\n"
    "EXAMPLE   python3 anon_check.py --scan README.md\n"
    "PITFALLS  2026-08-27 the old anonymiser was switched off and nothing said so; a missing pattern file now refuses with code 13.\n"
    "          2026-09-23 printing the text found would copy the leak into the logs; only its place and kind are printed."
)

USAGE = "usage: anon_check.py --notice | --autotest | [--rules FILE] --scan FILE..."

FIXTURES_RULES = '{"anonymizable": [{"pattern": "\\\\bPlimsoq\\\\b", "label": "person", "tag": "PERSON"}]}'
FIXTURES_BAD = '{"anonymizable": "x"}'
FIXTURES_LEAK = "a\nhello Plimsoq\n"
FIXTURES_CLEAN = "nothing here\n"


def _scan():
    args = sys.argv[1:]
    rules_path = None
    scan_files = []
    i = 0
    while i < len(args):
        if args[i] == "--rules":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            rules_path = args[i]
        elif args[i] == "--scan":
            i += 1
            scan_files = args[i:]
            break
        else:
            i += 1

    if not scan_files:
        print(USAGE)
        sys.exit(2)

    if rules_path is None:
        home = os.environ.get("FRUGALFLOW_HOME", "")
        if home:
            rules_path = os.path.join(home, "anonymization.json")
        else:
            rules_path = os.path.expanduser("~/.frugalflow/anonymization.json")

    if not os.path.isfile(rules_path):
        print("NO RULES FILE " + rules_path)
        sys.exit(13)

    try:
        with open(rules_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("NO RULES " + rules_path + ": not valid JSON")
        sys.exit(13)

    anonymizable, irreducible, errors = anon_rules.load(doc)
    if errors:
        for err in errors:
            print("NO RULES " + err)
        sys.exit(13)

    for fp in scan_files:
        if not os.path.isfile(fp):
            print("NO FILE " + fp)
            sys.exit(2)

    total = 0
    touched = 0
    for fp in scan_files:
        with open(fp, "r", encoding="utf-8", errors="replace") as f:
            text = f.read()
        hits = anon_core.find(text, anonymizable, irreducible)
        if hits:
            touched += 1
            total += len(hits)
            for line, kind, label, excerpt in hits:
                print(fp + ":" + str(line) + ": " + kind + " " + label)

    if total == 0:
        print("CLEAN " + str(len(scan_files)) + " files")
        sys.exit(0)
    else:
        print("FOUND " + str(total) + " in " + str(touched) + " of " + str(len(scan_files)) + " files")
        sys.exit(12)


def _autotest():
    self = os.path.abspath(__file__)
    all_pass = True

    def run(args, env=None):
        return subprocess.run(
            [sys.executable, self] + args,
            capture_output=True, text=True, env=env
        )

    # Test 1
    with tempfile.TemporaryDirectory() as tmp:
        rp = os.path.join(tmp, "rules.json")
        lp = os.path.join(tmp, "leak.txt")
        with open(rp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_RULES)
        with open(lp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_LEAK)
        r = run(["--rules", rp, "--scan", lp])
        lines = r.stdout.splitlines()
        exp_line = lp + ":2: anonymizable person"
        exp_last = "FOUND 1 in 1 of 1 files"
        ok = r.returncode == 12 and lines and exp_line in lines and lines[-1] == exp_last
        if ok:
            print("PASS test 1: code 12, line " + exp_line)
        else:
            print("FAIL test 1: expected code 12 + " + exp_line + " + " + exp_last + " got code " + str(r.returncode) + " out " + repr(r.stdout))
            all_pass = False

    # Test 2
    with tempfile.TemporaryDirectory() as tmp:
        rp = os.path.join(tmp, "rules.json")
        cp = os.path.join(tmp, "clean.txt")
        with open(rp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_RULES)
        with open(cp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_CLEAN)
        r = run(["--rules", rp, "--scan", cp])
        lines = r.stdout.splitlines()
        exp_last = "CLEAN 1 files"
        ok = r.returncode == 0 and lines and lines[-1] == exp_last
        if ok:
            print("PASS test 2: code 0, last " + exp_last)
        else:
            print("FAIL test 2: expected code 0 + " + exp_last + " got code " + str(r.returncode) + " out " + repr(r.stdout))
            all_pass = False

    # Test 3
    with tempfile.TemporaryDirectory() as tmp:
        cp = os.path.join(tmp, "clean.txt")
        with open(cp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_CLEAN)
        absent = os.path.join(tmp, "absent.json")
        r = run(["--rules", absent, "--scan", cp])
        ok = r.returncode == 13 and r.stdout.startswith("NO RULES FILE ")
        if ok:
            print("PASS test 3: code 13, NO RULES FILE")
        else:
            print("FAIL test 3: expected code 13 + NO RULES FILE got code " + str(r.returncode) + " out " + repr(r.stdout))
            all_pass = False

    # Test 4
    with tempfile.TemporaryDirectory() as tmp:
        bp = os.path.join(tmp, "bad.json")
        cp = os.path.join(tmp, "clean.txt")
        with open(bp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_BAD)
        with open(cp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_CLEAN)
        r1 = run(["--rules", bp, "--scan", cp])
        ok1 = r1.returncode == 13 and "NO RULES anonymizable must be a list" in r1.stdout
        rp2 = os.path.join(tmp, "rules.json")
        with open(rp2, "w", encoding="utf-8") as f:
            f.write(FIXTURES_RULES)
        absent2 = os.path.join(tmp, "no_such.txt")
        r2 = run(["--rules", rp2, "--scan", absent2])
        ok2 = r2.returncode == 2 and r2.stdout.startswith("NO FILE ")
        ok = ok1 and ok2
        if ok:
            print("PASS test 4: code 13 NO RULES + code 2 NO FILE")
        else:
            print("FAIL test 4: expected 13+2 got r1=" + str(r1.returncode) + " r2=" + str(r2.returncode) + " r1out=" + repr(r1.stdout) + " r2out=" + repr(r2.stdout))
            all_pass = False

    # Test 5
    with tempfile.TemporaryDirectory() as tmp:
        ap = os.path.join(tmp, "anonymization.json")
        with open(ap, "w", encoding="utf-8") as f:
            f.write(FIXTURES_RULES)
        lp = os.path.join(tmp, "leak.txt")
        with open(lp, "w", encoding="utf-8") as f:
            f.write(FIXTURES_LEAK)
        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = tmp
        r1 = run(["--scan", lp], env=env)
        ok1 = r1.returncode == 12
        r2 = run(["--notice"])
        ok2 = r2.returncode == 0 and r2.stdout.startswith("NAME      anon_check.py")
        ok = ok1 and ok2
        if ok:
            print("PASS test 5: code 12 via FRUGALFLOW_HOME + notice code 0")
        else:
            print("FAIL test 5: expected 12+0 got r1=" + str(r1.returncode) + " r2=" + str(r2.returncode) + " r2out=" + repr(r2.stdout))
            all_pass = False

    sys.exit(0 if all_pass else 1)


def main():
    args = sys.argv[1:]
    if "--notice" in args:
        print(NOTICE)
        sys.exit(0)
    if "--autotest" in args:
        _autotest()
        return
    _scan()


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "anon_check", sys.argv[1:])
