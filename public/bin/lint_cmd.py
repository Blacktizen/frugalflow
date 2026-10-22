#!/usr/bin/env python3
import os
import sys
import json
import shutil
import subprocess
import tempfile

BIN = os.path.dirname(os.path.abspath(__file__))
CONFIG = os.path.join(os.path.dirname(BIN), "config")
RULES = os.path.join(CONFIG, "brief_rules.json")
EXAMPLES = os.path.join(CONFIG, "brief_rules_examples.json")
BRIEF_CHECK = os.path.join(BIN, "brief_check.py")

USAGE = (
    "usage: lint_cmd.py BRIEF [--trust private|untrusted_third_party] [--waiver REASON] | "
    "--explain RULE_ID | --check-examples [--examples FILE] | --notice | --autotest"
)

NOTICE = (
    "NAME      lint_cmd.py - the frugalflow lint subcommand: checks a delegation brief against the rules, explains one rule with its examples, and self-checks the examples.\n"
    "READS     BRIEF, passed unchanged to brief_check.py; the rules from config/brief_rules.json beside the bin folder; the examples from --examples, default config/brief_rules_examples.json.\n"
    "WRITES    nothing of its own: the output of brief_check.py, unchanged, on lint BRIEF; the rule sheet on --explain; one line per rule (PASS, or its refusal), then CHECKED n rules, on --check-examples. Exits with brief_check.py's code, 2 on usage or unknown rule, 1 when an example fails.\n"
    "EXAMPLE   python3 lint_cmd.py brief.md --trust untrusted_third_party\n"
    "PITFALLS  2026-10-04 a checker copied into another folder drifts from its rules file: lint_cmd.py runs the brief_check.py that sits beside it and reads the config beside that bin folder, never an environment variable.\n"
)

ACCEPTED_BRIEF = (
    "NATURE: creation\n"
    "PRODUIT: controle\n"  # lang-ok
    "\n"
    "Write one new file: parse_csv.py. It reads a CSV file and prints the number of rows.\n"
    "FORBIDDEN: touching any other file.\n"
    "FORBIDDEN: accented byte literals in the code.\n"
    "Write nothing after the code block.\n"
)

REFUSED_BRIEF = "Do something nice.\n"


def _load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _example_lines(text):
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def _run_check(brief_path, trust):
    proc = subprocess.run(
        [sys.executable, BRIEF_CHECK, "--brief", brief_path, "--trust", trust],
        capture_output=True, text=True,
    )
    return proc.stdout.splitlines()


def explain(args):
    if len(args) != 1:
        print(USAGE)
        return 2
    rid = args[0]
    try:
        rules = _load_json(RULES)
        examples = _load_json(EXAMPLES)
    except (OSError, ValueError):
        sys.stderr.write("lint: rules or examples unreadable\n")
        return 2
    rule = None
    for r in rules.get("rules", []):
        if r.get("id") == rid:
            rule = r
            break
    ex_rules = examples.get("rules", {})
    if rule is None or rid not in ex_rules:
        sys.stderr.write("lint: unknown rule " + rid + "\n")
        return 2
    ex = ex_rules[rid]
    born = rule["born_from"]
    print(rid + " - " + rule["title"])
    print("why: " + born["date"] + ": " + born["incident"])
    print("fix: " + rule["fix"])
    print("refused example:")
    for line in _example_lines(ex["refused"]):
        print("  " + line)
    print("fixed example:")
    for line in _example_lines(ex["fixed"]):
        print("  " + line)
    print("limit: " + ex["limit"])
    print("test: frugalflow lint --check-examples")
    return 0


def check_examples(args):
    examples_path = EXAMPLES
    i = 0
    while i < len(args):
        if args[i] == "--examples":
            if i + 1 >= len(args):
                print(USAGE)
                return 2
            examples_path = args[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2
    try:
        rules = _load_json(RULES)
        examples = _load_json(examples_path)
    except (OSError, ValueError):
        sys.stderr.write("lint: rules or examples unreadable\n")
        return 2
    ex_rules = examples.get("rules", {})
    lines = []
    failed = 0
    with tempfile.TemporaryDirectory() as d:
        for rule in rules.get("rules", []):
            rid = rule["id"]
            if rid not in ex_rules:
                lines.append("FAIL " + rid + " refused=no fixed=no")
                failed += 1
                continue
            ex = ex_rules[rid]
            trust = ex.get("trust", "private")
            refused_path = os.path.join(d, rid + "_refused.txt")
            fixed_path = os.path.join(d, rid + "_fixed.txt")
            with open(refused_path, "w", encoding="utf-8", newline="") as f:
                f.write(ex["refused"])
            with open(fixed_path, "w", encoding="utf-8", newline="") as f:
                f.write(ex["fixed"])
            marker = "REFUSED " + rid + " - "
            refused_ok = any(l.startswith(marker) for l in _run_check(refused_path, trust))
            fixed_ok = not any(l.startswith(marker) for l in _run_check(fixed_path, trust))
            if refused_ok and fixed_ok:
                lines.append("PASS " + rid)
            else:
                lines.append("FAIL %s refused=%s fixed=%s" % (
                    rid, "yes" if refused_ok else "no", "yes" if fixed_ok else "no"))
                failed += 1
    for line in lines:
        print(line)
    print("CHECKED %d rules, %d failed" % (len(lines), failed))
    return 0 if failed == 0 else 1


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    if not argv:
        print(USAGE)
        return 2
    if argv[0] == "--explain":
        return explain(argv[1:])
    if argv[0] == "--check-examples":
        return check_examples(argv[1:])
    trust = "private"
    waiver = None
    brief = argv[0]
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--trust":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            trust = argv[i + 1]
            i += 2
        elif a == "--waiver":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            waiver = argv[i + 1]
            i += 2
        else:
            print(USAGE)
            return 2
    cmd = [sys.executable, BRIEF_CHECK, "--brief", brief, "--trust", trust]
    if waiver is not None:
        cmd += ["--waiver", waiver]
    proc = subprocess.run(cmd)
    return proc.returncode


def _autotest_run(args):
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True, text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def autotest():
    base = tempfile.mkdtemp()
    try:
        accepted = os.path.join(base, "accepted.md")
        with open(accepted, "w", encoding="utf-8") as f:
            f.write(ACCEPTED_BRIEF)
        refused = os.path.join(base, "refused.md")
        with open(refused, "w", encoding="utf-8") as f:
            f.write(REFUSED_BRIEF)

        # Test 1: the accepted brief is accepted.
        rc, out, err = _autotest_run([accepted])
        expected = "code 0, non-empty output"
        ok = rc == 0 and out != ""
        got = "code=0" if ok else "code=" + str(rc) + " out=" + repr(out) + " err=" + repr(err)
        cases = [(1, expected, got, ok)]

        # Test 2: the refused brief is refused, with the E5 line.
        rc, out, err = _autotest_run([refused])
        expected = "code 5, a line starting with 'REFUSED E5 - '"
        ok = rc == 5 and any(l.startswith("REFUSED E5 - ") for l in out.splitlines())
        got = "code=5, REFUSED E5 line" if ok else "code=" + str(rc) + " out=" + repr(out)
        cases.append((2, expected, got, ok))

        # Test 3: --explain E4 prints the rule sheet.
        rc, out, err = _autotest_run(["--explain", "E4"])
        expected = "code 0, first line 'E4 - ', the refused example:/fixed example:/limit: lines"
        lines = out.splitlines()
        ok = (
            rc == 0
            and lines
            and lines[0].startswith("E4 - ")
            and "refused example:" in lines
            and "fixed example:" in lines
            and any(l.startswith("limit: ") for l in lines)
        )
        got = "code=0, sheet present" if ok else "code=" + str(rc) + " lines=" + repr(lines[:4])
        cases.append((3, expected, got, ok))

        # Test 4: --explain on an unknown rule.
        rc, out, err = _autotest_run(["--explain", "ZZ9"])
        expected = "code 2, 'unknown rule' on stderr"
        ok = rc == 2 and "unknown rule" in err
        got = "code=2, unknown rule" if ok else "code=" + str(rc) + " err=" + repr(err)
        cases.append((4, expected, got, ok))

        # Test 5: --check-examples on a broken copy, then on the real file.
        with open(EXAMPLES, "r", encoding="utf-8") as f:
            doc = json.load(f)
        doc["rules"]["E5"]["refused"] = ACCEPTED_BRIEF
        broken = os.path.join(base, "examples_broken.json")
        with open(broken, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        rc1, out1, err1 = _autotest_run(["--check-examples", "--examples", broken])
        rc2, out2, err2 = _autotest_run(["--check-examples"])
        expected = "code 1 with the E5 refusal line on the broken copy, code 0 on the real file"
        ok = (
            rc1 == 1
            and any(l.startswith("FAIL E5") for l in out1.splitlines())
            and rc2 == 0
            and any(l.startswith("CHECKED ") for l in out2.splitlines())
        )
        got = ("code1=1 with the E5 refusal line, code2=0" if ok
               else "code1=" + str(rc1) + " code2=" + str(rc2)
               + " out1=" + repr(out1[-200:]) + " out2=" + repr(out2[-200:]))
        cases.append((5, expected, got, ok))

        passed = 0
        failed = 0
        for num, exp, got, ok in cases:
            if ok:
                print("PASS " + str(num) + ": expected " + exp + " | got " + got)
                passed += 1
            else:
                print("FAIL " + str(num) + ": expected " + exp + " | got " + got)
                failed += 1
                break
        if failed == 0:
            print("AUTOTEST " + str(passed) + " PASS")
        else:
            print("AUTOTEST " + str(passed) + " PASS / " + str(failed) + " FAIL")
        return 0 if failed == 0 else 1
    finally:
        shutil.rmtree(base, ignore_errors=True)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "lint_cmd", sys.argv[1:])
