#!/usr/bin/env python3
import json
import os
import sys
import subprocess
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import brief_rules

NOTICE = (
    "NAME      brief_bench.py - replays a bench of delegation briefs through the brief rules and counts holes and false refusals separately, with the false refusals of each rule.\n"
    'READS     --cases FILE: {"cases": [{"id", "brief", "expected": "pass"|"refuse", "trust"?, "rules"?}]}; the rules from --rules, else FRUGALFLOW_BRIEF_RULES, else config/brief_rules.json.\n'
    "WRITES    one line per case that is not ok, one RATE line per rule, then the summary line; exit 0 with no hole and no false refusal, 1 otherwise, 2 on usage or unreadable file.\n"
    "EXAMPLE   python3 brief_bench.py --cases ../data/brief_cases.json\n"
    "PITFALLS  2026-09-25 a false refusal is a defect like a hole: users stop reading a guard that refuses honest briefs. Both are counted, never merged into one score."
)


def bench(cases_doc, rules_doc):
    total = 0
    honest = 0
    faulty = 0
    ok = 0
    holes = []
    false_refusals = []
    per_rule = {}
    lines = []
    for case in cases_doc["cases"]:
        total += 1
        cid = case["id"]
        expected = case["expected"]
        if expected not in ("pass", "refuse"):
            raise ValueError("bad case " + cid)
        got = [r["id"] for r in brief_rules.evaluate(case["brief"], rules_doc, case.get("trust", "private"))]
        if expected == "pass":
            honest += 1
            if not got:
                ok += 1
            else:
                false_refusals.append(cid)
                lines.append("FALSE-REFUSAL " + cid + " by " + ",".join(got))
                for x in got:
                    per_rule[x] = per_rule.get(x, 0) + 1
        else:
            faulty += 1
            missing = [x for x in case.get("rules", []) if x not in got]
            if not got or missing:
                holes.append(cid)
                missing_str = "all" if not got else ",".join(missing)
                got_str = ",".join(got) if got else "-"
                lines.append("HOLE " + cid + " missing " + missing_str + " got " + got_str)
            else:
                ok += 1
    return {"total": total, "honest": honest, "faulty": faulty, "ok": ok,
            "holes": holes, "false_refusals": false_refusals, "per_rule": per_rule, "lines": lines}


def summary_line(result):
    return (f"cases {result['total']} | honest {result['honest']} | faulty {result['faulty']}"
            f" | ok {result['ok']} | holes {len(result['holes'])} | false refusals {len(result['false_refusals'])}")


def rate_lines(result, rules_doc):
    out = []
    for rule in rules_doc["rules"]:
        rid = rule["id"]
        out.append(f"RATE {rid} {result['per_rule'].get(rid, 0)}/{result['honest']}")
    return out


def exit_code(result):
    return 0 if not result["holes"] and not result["false_refusals"] else 1


def _R(rid, trigger, requirement):
    return {"id": rid, "title": "t", "born_from": {"date": "2026-01-01", "incident": "i"},
            "fix": "f", "trigger": trigger, "requirement": requirement}


RULES = {"limits": {}, "rules": [
    _R("N1", {}, {"type": "regex_all", "patterns": ["nature:"]}),
    _R("G1", {"any": ["epreuve"]}, {"type": "regex_all", "patterns": ["grandeur"]}),  # lang-ok: French brief words the rules read
    _R("P1", {"trust": "untrusted_third_party"}, {"type": "regex_none", "patterns": ["/srv/"]})]}
P1C = {"id": "p1", "brief": "NATURE: x", "expected": "pass"}
P2C = {"id": "p2", "brief": "NATURE: x epreuve", "expected": "pass"}  # lang-ok
R1C = {"id": "r1", "brief": "hello", "expected": "refuse", "rules": ["N1"]}
R2C = {"id": "r2", "brief": "NATURE: x", "expected": "refuse"}
R3C = {"id": "r3", "brief": "hello epreuve", "expected": "refuse", "rules": ["N1", "X9"]}  # lang-ok
T1C = {"id": "t1", "brief": "NATURE: /srv/a", "expected": "refuse", "trust": "untrusted_third_party", "rules": ["P1"]}
CASES = {"cases": [P1C, P2C, R1C, R2C, R3C, T1C]}
GOOD = {"cases": [P1C, R1C, T1C]}


def _autotest():
    failed = 0

    # Test 1
    try:
        r = bench(CASES, RULES)
        exp = (r["total"] == 6 and r["honest"] == 2 and r["faulty"] == 4 and r["ok"] == 3
               and r["holes"] == ["r2", "r3"] and r["false_refusals"] == ["p2"]
               and r["per_rule"] == {"G1": 1})
        if exp:
            print("PASS test1 total=6 honest=2 faulty=4 ok=3 holes=['r2','r3'] false_refusals=['p2'] per_rule={'G1':1}")
        else:
            print(f"FAIL test1 expected total=6 honest=2 faulty=4 ok=3 holes=['r2','r3'] false_refusals=['p2'] per_rule={{'G1': 1}} got total={r['total']} honest={r['honest']} faulty={r['faulty']} ok={r['ok']} holes={r['holes']} false_refusals={r['false_refusals']} per_rule={r['per_rule']}")
            failed += 1
    except Exception as e:
        print(f"FAIL test1 exception {e}")
        failed += 1

    # Test 2
    try:
        r = bench(CASES, RULES)
        exp_lines = ["FALSE-REFUSAL p2 by G1", "HOLE r2 missing all got -", "HOLE r3 missing X9 got N1,G1"]
        exp_summary = "cases 6 | honest 2 | faulty 4 | ok 3 | holes 2 | false refusals 1"
        exp_rate = ["RATE N1 0/2", "RATE G1 1/2", "RATE P1 0/2"]
        exp2 = (r["lines"] == exp_lines and summary_line(r) == exp_summary and rate_lines(r, RULES) == exp_rate)
        if exp2:
            print("PASS test2 lines+summary+rate correct")
        else:
            print(f"FAIL test2 expected lines={exp_lines} summary={exp_summary!r} rate={exp_rate} got lines={r['lines']} summary={summary_line(r)!r} rate={rate_lines(r, RULES)}")
            failed += 1
    except Exception as e:
        print(f"FAIL test2 exception {e}")
        failed += 1

    # Test 3
    try:
        ok3 = True
        if exit_code(bench(GOOD, RULES)) != 0:
            ok3 = False
        if exit_code(bench(CASES, RULES)) != 1:
            ok3 = False
        try:
            bench({"cases": [{"id": "z", "brief": "x", "expected": "maybe"}]}, RULES)
            ok3 = False
        except ValueError:
            pass
        if ok3:
            print("PASS test3 exit_code GOOD=0 CASES=1 ValueError raised")
        else:
            print(f"FAIL test3 expected exit_code(GOOD)=0 exit_code(CASES)=1 ValueError")
            failed += 1
    except Exception as e:
        print(f"FAIL test3 exception {e}")
        failed += 1

    # Test 4
    try:
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "cases.json"), "w", encoding="utf-8") as f:
                json.dump(CASES, f)
            with open(os.path.join(d, "good.json"), "w", encoding="utf-8") as f:
                json.dump(GOOD, f)
            with open(os.path.join(d, "rules.json"), "w", encoding="utf-8") as f:
                json.dump(RULES, f)

            def RUN(args):
                p = subprocess.run([sys.executable, os.path.abspath(__file__)] + args,
                                   capture_output=True, text=True, cwd=d)
                return p.returncode, p.stdout

            code, out = RUN(["--cases", "cases.json", "--rules", "rules.json"])
            last_line = out.strip().split("\n")[-1] if out.strip() else ""
            ok4a = (code == 1 and "HOLE r2 missing all got -" in out and "RATE G1 1/2" in out)
            ok4b = (last_line == "cases 6 | honest 2 | faulty 4 | ok 3 | holes 2 | false refusals 1")
            code2, out2 = RUN(["--cases", "good.json", "--rules", "rules.json"])
            ok4c = (code2 == 0 and "holes 0 | false refusals 0" in out2)
            if ok4a and ok4b and ok4c:
                print("PASS test4 subprocess CASES code=1 and GOOD code=0")
            else:
                print(f"FAIL test4 code={code} out={out!r} last={last_line!r} code2={code2} out2={out2!r}")
                failed += 1
    except Exception as e:
        print(f"FAIL test4 exception {e}")
        failed += 1

    # Test 5
    try:
        with tempfile.TemporaryDirectory() as d:
            with open(os.path.join(d, "rules.json"), "w", encoding="utf-8") as f:
                json.dump(RULES, f)

            def RUN(args):
                p = subprocess.run([sys.executable, os.path.abspath(__file__)] + args,
                                   capture_output=True, text=True, cwd=d)
                return p.returncode, p.stdout

            code, out = RUN(["--cases", "absent.json", "--rules", "rules.json"])
            ok5a = (code == 2 and "BENCH UNREADABLE: " in out)
            code2, out2 = RUN([])
            ok5b = (code2 == 2 and out2 == "usage: brief_bench.py --cases FILE [--rules FILE] | --notice | --autotest\n")
            code3, out3 = RUN(["--notice"])
            ok5c = (code3 == 0 and out3.startswith("NAME      brief_bench.py"))
            if ok5a and ok5b and ok5c:
                print("PASS test5 unreadable=2 usage=2 notice=0")
            else:
                print(f"FAIL test5 5a code={code} out={out!r} 5b code={code2} out={out2!r} 5c code={code3} start={out3[:40]!r}")
                failed += 1
    except Exception as e:
        print(f"FAIL test5 exception {e}")
        failed += 1

    return failed == 0


def main():
    args = sys.argv[1:]

    if not args:
        print("usage: brief_bench.py --cases FILE [--rules FILE] | --notice | --autotest")
        sys.exit(2)

    if args[0] == "--notice":
        print(NOTICE)
        sys.exit(0)

    if args[0] == "--autotest":
        ok = _autotest()
        sys.exit(0 if ok else 1)

    if args[0] == "--cases":
        if len(args) < 2:
            print("usage: brief_bench.py --cases FILE [--rules FILE] | --notice | --autotest")
            sys.exit(2)
        cases_path = args[1]
        rules_path = None
        if len(args) == 4 and args[2] == "--rules":
            rules_path = args[3]
        elif len(args) > 2:
            print("usage: brief_bench.py --cases FILE [--rules FILE] | --notice | --autotest")
            sys.exit(2)

        try:
            with open(cases_path, "r", encoding="utf-8") as f:
                cases_doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            print("BENCH UNREADABLE: " + cases_path)
            sys.exit(2)

        if rules_path is None:
            rules_path = os.environ.get("FRUGALFLOW_BRIEF_RULES")
        if rules_path is None:
            rules_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "brief_rules.json")

        try:
            with open(rules_path, "r", encoding="utf-8") as f:
                rules_doc = json.load(f)
        except (OSError, json.JSONDecodeError):
            print("BENCH UNREADABLE: " + cases_path)
            sys.exit(2)

        defects = brief_rules.check_doc(rules_doc)
        if defects:
            print("RULES INVALID: " + defects[0])
            sys.exit(2)

        try:
            result = bench(cases_doc, rules_doc)
        except ValueError:
            print("BENCH UNREADABLE: " + cases_path)
            sys.exit(2)

        for line in result["lines"]:
            print(line)
        for line in rate_lines(result, rules_doc):
            print(line)
        print(summary_line(result))
        sys.exit(exit_code(result))
    else:
        print("usage: brief_bench.py --cases FILE [--rules FILE] | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "brief_bench", sys.argv[1:])
