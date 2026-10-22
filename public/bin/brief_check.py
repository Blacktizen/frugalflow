#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile


def default_rules():
    return os.environ.get("FRUGALFLOW_BRIEF_RULES") or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "config", "brief_rules.json",
    )


USAGE = "usage: brief_check.py --brief FILE [--rules FILE] [--trust private|untrusted_third_party] [--waiver REASON] | --notice | --autotest"

NOTICE = (
    "NAME      brief_check.py - checks a delegation brief against the rules file before it is sent, and says for each refused rule how to fix the brief.\n"
    "READS     --brief FILE, byte-exact so CRLF is seen; the rules from --rules, else FRUGALFLOW_BRIEF_RULES, else config/brief_rules.json beside the bin folder.\n"
    "WRITES    one REFUSED block per refused rule, then a VERDICT line. Exits 0 accepted or waived, 2 bad argument, 3 unreadable brief, rules or engine (never an acceptance), 5 refused.\n"
    "EXAMPLE   python3 brief_check.py --brief task.md --trust untrusted_third_party\n"
    "PITFALLS  2026-09-23 a role missing from a list skipped the old brief guard with a note on stderr: nine briefs left unchecked. This tool never skips: what cannot be read refuses with code 3.\n"
    "          2026-10-05 a newcomer's first brief was refused 12 times with no model to follow: a refusal now names the brief template."
)


def parse_args(argv):
    brief = None
    rules = None
    trust = "private"
    waiver = None
    notice = False
    autotest = False
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--notice":
            notice = True
        elif arg == "--autotest":
            autotest = True
        elif arg == "--brief":
            if i + 1 >= len(argv):
                return None
            brief = argv[i + 1]
            i += 1
        elif arg == "--rules":
            if i + 1 >= len(argv):
                return None
            rules = argv[i + 1]
            i += 1
        elif arg == "--trust":
            if i + 1 >= len(argv):
                return None
            trust = argv[i + 1]
            i += 1
        elif arg == "--waiver":
            if i + 1 >= len(argv):
                return None
            waiver = argv[i + 1]
            i += 1
        else:
            return None
        i += 1
    return (brief, rules, trust, waiver, notice, autotest)


def main():
    parsed = parse_args(sys.argv[1:])
    if parsed is None:
        print(USAGE)
        sys.exit(2)
    brief, rules, trust, waiver, notice, autotest = parsed

    if notice:
        print(NOTICE)
        sys.exit(0)

    if autotest:
        run_autotest()
        return

    if brief is None:
        print(USAGE)
        sys.exit(2)

    if trust not in ("private", "untrusted_third_party"):
        print(USAGE)
        sys.exit(2)

    if waiver is not None and waiver.strip() == "":
        print(USAGE)
        sys.exit(2)

    if rules is None:
        rules = default_rules()

    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    try:
        import brief_rules
    except ImportError:
        print("RULES ENGINE MISSING")
        sys.exit(3)

    try:
        with open(brief, encoding="utf-8", newline="") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        print("BRIEF UNREADABLE: " + brief)
        sys.exit(3)

    try:
        with open(rules, encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, ValueError):
        print("RULES UNREADABLE: " + rules)
        sys.exit(3)

    defaults = brief_rules.check_doc(doc)
    if defaults:
        print("RULES INVALID: " + defaults[0])
        sys.exit(3)

    refused = brief_rules.evaluate(text, doc, trust)
    print("CHECKED " + str(len(doc["rules"])) + " rules, trust " + trust)
    for r in refused:
        print(brief_rules.explain(r))

    if not refused:
        print("VERDICT: ACCEPTED")
        sys.exit(0)
    elif waiver is not None:
        print("VERDICT: ACCEPTED WITH WAIVER: " + waiver)
        sys.exit(0)
    else:
        print("VERDICT: REFUSED " + str(len(refused)) + " rules, nothing sent")
        template = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            "examples", "brief_template.md",
        )
        print("START FROM: " + template + " (a brief that passes every rule: copy it, replace the task, keep its Rules section)")
        sys.exit(5)


RULES = {"limits": {}, "rules": [
    {"id": "N1", "title": "no nature", "born_from": {"date": "2026-01-01", "incident": "i"}, "fix": "write nature:", "trigger": {}, "requirement": {"type": "regex_all", "patterns": ["nature:"]}},
    {"id": "P1", "title": "path", "born_from": {"date": "2026-01-01", "incident": "i"}, "fix": "remove it", "trigger": {"trust": "untrusted_third_party"}, "requirement": {"type": "regex_none", "patterns": ["/srv/"]}},
    {"id": "C1", "title": "crlf", "born_from": {"date": "2026-01-01", "incident": "i"}, "fix": "unix endings", "trigger": {}, "requirement": {"type": "regex_none", "patterns": ["\\r"]}}]}


def _setup(d):
    with open(os.path.join(d, "rules.json"), "w", encoding="utf-8") as f:
        f.write(json.dumps(RULES))
    with open(os.path.join(d, "good.md"), "wb") as f:
        f.write(b"NATURE: creation\n")
    with open(os.path.join(d, "bad.md"), "wb") as f:
        f.write(b"hello\n")
    with open(os.path.join(d, "path.md"), "wb") as f:
        f.write(b"NATURE: x /srv/a\n")
    with open(os.path.join(d, "crlf.md"), "wb") as f:
        f.write(b"NATURE: a\r\n")
    with open(os.path.join(d, "latin.md"), "wb") as f:
        f.write(b"\xff\n")
    with open(os.path.join(d, "broken.json"), "wb") as f:
        f.write(b"{")
    with open(os.path.join(d, "invalid.json"), "wb") as f:
        f.write(b'{"limits": {}, "rules": 5}')


def _run(d, args, script=None):
    if script is None:
        script = os.path.abspath(__file__)
    env = dict(os.environ)
    env["FRUGALFLOW_BRIEF_RULES"] = os.path.join(d, "rules.json")
    r = subprocess.run(
        [sys.executable, script] + args,
        capture_output=True, text=True, cwd=d, env=env,
    )
    return (r.returncode, r.stdout)


def _test1(d):
    code, out = _run(d, ["--brief", "good.md"])
    assert code == 0, "code=" + str(code)
    assert "VERDICT: ACCEPTED" in out, "missing VERDICT: ACCEPTED"
    assert "CHECKED 3 rules, trust private" in out, "missing CHECKED line"
    code, out = _run(d, ["--brief", "bad.md"])
    assert code == 5, "code=" + str(code)
    assert "REFUSED N1 - no nature" in out, "missing REFUSED N1"
    assert "  To fix: write nature:" in out, "missing To fix"
    assert "VERDICT: REFUSED 1 rules, nothing sent" in out, "missing VERDICT REFUSED"


def _test2(d):
    code, out = _run(d, ["--brief", "bad.md", "--waiver", "known"])
    assert code == 0, "code=" + str(code)
    assert "REFUSED N1 - " in out, "missing REFUSED N1"
    assert "VERDICT: ACCEPTED WITH WAIVER: known" in out, "missing WAIVER verdict"
    code, _ = _run(d, ["--brief", "bad.md", "--waiver", "  "])
    assert code == 2, "code=" + str(code)
    code, out = _run(d, [])
    assert code == 2, "code=" + str(code)
    assert out.startswith("usage: brief_check.py"), "missing usage"


def _test3(d):
    code, _ = _run(d, ["--brief", "path.md"])
    assert code == 0, "code=" + str(code)
    code, out = _run(d, ["--brief", "path.md", "--trust", "untrusted_third_party"])
    assert code == 5, "code=" + str(code)
    assert "REFUSED P1 - path" in out, "missing REFUSED P1"
    code, _ = _run(d, ["--brief", "path.md", "--trust", "bogus"])
    assert code == 2, "code=" + str(code)
    code, out = _run(d, ["--brief", "crlf.md"])
    assert code == 5, "code=" + str(code)
    assert "REFUSED C1 - crlf" in out, "missing REFUSED C1"


def _test4(d):
    code, out = _run(d, ["--brief", "absent.md"])
    assert code == 3, "code=" + str(code)
    assert "BRIEF UNREADABLE: " in out, "missing BRIEF UNREADABLE"
    code, out2 = _run(d, ["--brief", "latin.md"])
    assert code == 3, "code=" + str(code)
    code, out3 = _run(d, ["--brief", "good.md", "--rules", "broken.json"])
    assert code == 3, "code=" + str(code)
    assert "RULES UNREADABLE: " in out3, "missing RULES UNREADABLE"
    code, out4 = _run(d, ["--brief", "good.md", "--rules", "invalid.json"])
    assert code == 3, "code=" + str(code)
    assert "RULES INVALID: rules must be a list" in out4, "missing RULES INVALID"
    for o in (out, out2, out3, out4):
        assert "VERDICT: ACCEPTED" not in o, "found VERDICT: ACCEPTED in exit-3 output"


def _test5(d):
    # the copied file imports exit_log at startup, so the support modules ride along.
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    for module in ("exit_log.py", "block_log.py", "block_rules.py"):
        shutil.copy(os.path.join(bin_dir, module), os.path.join(d, module))
    shutil.copy(os.path.abspath(__file__), os.path.join(d, "alone.py"))
    code, out = _run(d, ["--brief", "good.md"], script=os.path.join(d, "alone.py"))
    assert code == 3, "code=" + str(code)
    assert "RULES ENGINE MISSING" in out, "missing RULES ENGINE MISSING"
    code, out = _run(d, ["--notice"])
    assert code == 0, "code=" + str(code)
    assert out.startswith("NAME      brief_check.py"), "missing NAME line"


def _test6(d):
    with open(os.path.join(d, "newcomer.md"), "wb") as f:
        f.write(b"Write a function.\n")
    code, out = _run(d, ["--brief", "newcomer.md"])
    assert code == 5, "code=" + str(code)
    suffix = "brief_template.md (a brief that passes every rule: copy it, replace the task, keep its Rules section)"
    starts = [ln for ln in out.splitlines() if ln.startswith("START FROM: ")]
    assert len(starts) == 1, "expected one START FROM line, got " + str(len(starts))
    assert starts[0].endswith(suffix), "START FROM line does not name the brief template"


def run_autotest():
    tests = [
        ("code 0 ACCEPTED + code 5 REFUSED N1", _test1),
        ("waiver + empty waiver + no args", _test2),
        ("trust private ok + untrusted P1 + bogus trust + crlf", _test3),
        ("absent + latin + broken + invalid, no ACCEPTED", _test4),
        ("engine missing + notice", _test5),
        ("refusal names the brief template", _test6),
    ]
    all_pass = True
    for idx, (desc, fn) in enumerate(tests, 1):
        with tempfile.TemporaryDirectory() as d:
            _setup(d)
            try:
                fn(d)
                print("PASS " + str(idx) + ": " + desc)
            except AssertionError as e:
                print("FAIL " + str(idx) + ": expected " + desc + " got " + str(e))
                all_pass = False
    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "brief_check", sys.argv[1:])
