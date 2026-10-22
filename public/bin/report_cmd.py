import os
import sys
import json
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_rules
import ledger_rules
import report_rules
import usage_report

USAGE = (
    "usage: report_cmd.py TRACE [--log DELEGATIONS] [--models MODELS] [--summary] | --notice | --autotest"
)

NOTICE = (
    "NAME      report_cmd.py - the frugalflow report subcommand: shows where a session's tokens went, from its transcript, and sums the delegation log in tokens only.\n"
    "READS     the TRACE transcript; with --log the delegation log, one JSON object per line; with --models the models document, else an empty index.\n"
    "WRITES    nothing: the lines of report_rules.render, or summary_lines with --summary, then the first two lines of the ledger report with [observed]; a missing trace gives 2.\n"
    "EXAMPLE   python3 report_cmd.py public/examples/report_trace.jsonl\n"
    "PITFALLS  2026-10-04 the unit is tokens only: the third line of the ledger report, a price, is never printed by this tool.\n"
)

BIN = os.path.dirname(os.path.abspath(__file__))
EXAMPLES = os.path.join(os.path.dirname(BIN), "examples")


def _delegation_lines(log_path, models_path):
    with open(log_path, "r", encoding="utf-8") as f:
        text = f.read()
    records = []
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            continue
        if isinstance(obj, dict):
            records.append(obj)
    if models_path is not None:
        try:
            with open(models_path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except (OSError, ValueError):
            doc = {}
    else:
        doc = {}
    summary = ledger_rules.summarize(records, ledger_rules.model_index(doc))
    lines = ledger_rules.report(summary, None)
    return [line + " [observed]" for line in lines[:2]]


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    if not argv:
        print(USAGE)
        return 2
    trace = argv[0]
    log_path = None
    models_path = None
    summary = False
    i = 1
    while i < len(argv):
        a = argv[i]
        if a == "--log":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            log_path = argv[i + 1]
            i += 2
        elif a == "--models":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            models_path = argv[i + 1]
            i += 2
        elif a == "--summary":
            summary = True
            i += 1
        else:
            print(USAGE)
            return 2
    try:
        objs = usage_report.load_transcript(trace)
    except (OSError, UnicodeDecodeError):
        sys.stderr.write("report: cannot read " + trace + "\n")
        return 2
    a = report_rules.analyze(usage_rules.group(objs))
    lines = report_rules.summary_lines(a) if summary else report_rules.render(a)
    for line in lines:
        print(line)
    if log_path is not None:
        try:
            extra = _delegation_lines(log_path, models_path)
        except (OSError, UnicodeDecodeError):
            sys.stderr.write("report: cannot read " + log_path + "\n")
            return 2
        for line in extra:
            print(line)
    return 0


def _run(args):
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True,
        text=True,
        timeout=20,
    )
    return proc.returncode, proc.stdout.strip().splitlines(), proc.stderr


def autotest():
    trace = os.path.join(EXAMPLES, "report_trace.jsonl")
    delegations = os.path.join(EXAMPLES, "report_delegations.jsonl")
    passed = 0
    failed = 0

    # Test 1
    expected = "code 0, a line 'turns: 4 [observed]' and the costliest turn 2 line"
    rc, lines, err = _run([trace])
    ok = (
        rc == 0
        and "turns: 4 [observed]" in lines
        and "costliest turn 2: +30 010 tokens after Read: big.log [observed]" in lines
    )
    if ok:
        print("PASS test 1: expected " + expected + " | got code=" + str(rc))
    else:
        print("FAIL test 1: expected " + expected + " | got code=" + str(rc) + " lines=" + repr(lines) + " stderr=" + repr(err))
    if ok:
        passed += 1
    else:
        failed += 1

    # Test 2
    expected = "code 0, a DELEGATIONS 3 | success 2 line ending with [observed], no COUNTERFACTUAL line"
    rc, lines, err = _run([trace, "--log", delegations])
    ok = (
        rc == 0
        and any(l.startswith("DELEGATIONS 3 | success 2") and l.endswith(" [observed]") for l in lines)
        and not any(l.startswith("COUNTERFACTUAL") for l in lines)
    )
    if ok:
        print("PASS test 2: expected " + expected + " | got code=" + str(rc))
    else:
        print("FAIL test 2: expected " + expected + " | got code=" + str(rc) + " lines=" + repr(lines) + " stderr=" + repr(err))
    if ok:
        passed += 1
    else:
        failed += 1

    # Test 3
    expected = "code 0, 4 lines, first 'FrugalFlow - session summary'"
    rc, lines, err = _run([trace, "--summary"])
    ok = rc == 0 and len(lines) == 4 and lines[0] == "FrugalFlow - session summary"
    if ok:
        print("PASS test 3: expected " + expected + " | got code=" + str(rc))
    else:
        print("FAIL test 3: expected " + expected + " | got code=" + str(rc) + " lines=" + repr(lines) + " stderr=" + repr(err))
    if ok:
        passed += 1
    else:
        failed += 1

    # Test 4
    tmp = tempfile.mkdtemp()
    absent = os.path.join(tmp, "absent.jsonl")
    expected = "code 2, 'cannot read' on stderr"
    rc, lines, err = _run([absent])
    ok = rc == 2 and "cannot read" in err
    if ok:
        print("PASS test 4: expected " + expected + " | got code=" + str(rc))
    else:
        print("FAIL test 4: expected " + expected + " | got code=" + str(rc) + " lines=" + repr(lines) + " stderr=" + repr(err))
    if ok:
        passed += 1
    else:
        failed += 1

    # Test 5
    expected = "code 2, the usage on stdout"
    rc, lines, err = _run([])
    ok = rc == 2 and lines and lines[0] == USAGE
    if ok:
        print("PASS test 5: expected " + expected + " | got code=" + str(rc))
    else:
        print("FAIL test 5: expected " + expected + " | got code=" + str(rc) + " lines=" + repr(lines) + " stderr=" + repr(err))
    if ok:
        passed += 1
    else:
        failed += 1

    if failed == 0:
        print("AUTOTEST " + str(passed) + " PASS")
    else:
        print("AUTOTEST " + str(passed) + " PASS / " + str(failed) + " FAIL")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "report_cmd", sys.argv[1:])
