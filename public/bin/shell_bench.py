#!/usr/bin/env python3
import json, os, sys, subprocess, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_rules

FAKE = {"a": "free", "b": "write", "c": "unknown", "d": "free", "e": "write"}
def FAKE_JUDGE(cmd, cfg):
    return {"verdict": FAKE[cmd], "targets": [], "reason": "x"}
DOC = {"config": {}, "cases": [
    {"id": "K1", "cmd": "a", "expect": "free"},
    {"id": "K2", "cmd": "b", "expect": "write"},
    {"id": "K3", "cmd": "a", "expect": "write"},
    {"id": "K4", "cmd": "d", "expect": "unknown"},
    {"id": "K5", "cmd": "e", "expect": "free"},
    {"id": "K6", "cmd": "c", "expect": "free", "known_limit": "x"},
    {"id": "K7", "cmd": "c", "expect": "write"},
]}
REAL = {"config": {"code_extensions": [".py"], "delegate_tools": []}, "cases": [
    {"id": "S1", "cmd": "cat > /tmp/s.py <<EOF\nx\nEOF", "expect": "write"},
    {"id": "S2", "cmd": "ls", "expect": "free"},
]}
REAL_HOLE = {"config": {"code_extensions": [".py"], "delegate_tools": []}, "cases": [
    {"id": "S2", "cmd": "ls", "expect": "write"},
]}

NOTICE = (
    "NAME      shell_bench.py - replays a bench of shell commands through shell_rules and counts holes and false refusals separately.\n"
    "READS     the JSON file given by --cases: {\"config\": {...}, \"cases\": [{\"id\", \"cmd\", \"expect\", \"known_limit\"?}]}.\n"
    "WRITES    nothing: one line per case that is not ok, then the summary line; exit 0 when there is no hole, no false refusal and no mismatch, 1 otherwise, 2 on usage or unreadable file.\n"
    "EXAMPLE   python3 shell_bench.py --cases ../data/shell_cases.json\n"
    "PITFALLS  2026-09-25 a false refusal is a defect like a hole: both are counted, never merged into one score.\n"
    "          A known_limit is a documented false refusal: it is printed, it does not fail the bench."
)

def bench(doc, judge=None):
    if judge is None:
        judge = shell_rules.judge_command
    total = len(doc["cases"])
    ok = 0
    holes = []
    false_refusals = []
    known_limits = []
    mismatches = []
    lines = []
    for case in doc["cases"]:
        got = judge(case["cmd"], doc["config"])["verdict"]
        expect = case["expect"]
        if got == expect:
            ok += 1
            continue
        preview = case["cmd"].split("\n")[0][:70]
        if expect in ("write", "unknown") and got == "free":
            holes.append(case["id"])
            lines.append(f"HOLE {case['id']} expect={expect} got={got} {preview}")
        elif expect == "free" and "known_limit" in case:
            known_limits.append(case["id"])
            lines.append(f"KNOWN-LIMIT {case['id']} expect={expect} got={got} {preview}")
        elif expect == "free":
            false_refusals.append(case["id"])
            lines.append(f"FALSE-REFUSAL {case['id']} expect={expect} got={got} {preview}")
        else:
            mismatches.append(case["id"])
            lines.append(f"MISMATCH {case['id']} expect={expect} got={got} {preview}")
    return {"total": total, "ok": ok, "holes": holes, "false_refusals": false_refusals,
            "known_limits": known_limits, "mismatches": mismatches, "lines": lines}

def summary_line(result):
    return (f"cases {result['total']} | ok {result['ok']} | holes {len(result['holes'])} | "
            f"false refusals {len(result['false_refusals'])} | known limits {len(result['known_limits'])} | "
            f"mismatches {len(result['mismatches'])}")

def exit_code(result):
    if not result["holes"] and not result["false_refusals"] and not result["mismatches"]:
        return 0
    return 1

def _autotest():
    passed = 0

    # Test 1
    r = bench(DOC, FAKE_JUDGE)
    ok1 = (r["total"] == 7 and r["ok"] == 2 and r["holes"] == ["K3", "K4"]
           and r["false_refusals"] == ["K5"] and r["known_limits"] == ["K6"]
           and r["mismatches"] == ["K7"]
           and r["lines"][0] == "HOLE K3 expect=write got=free a"
           and r["lines"][2] == "FALSE-REFUSAL K5 expect=free got=write e")
    if ok1:
        print("PASS 1 total=7 ok=2 holes=[K3,K4] false_refusals=[K5] known_limits=[K6] mismatches=[K7] lines[0]+lines[2] correct")
        passed += 1
    else:
        print(f"FAIL 1 expected total=7 ok=2 holes=[K3,K4] false_refusals=[K5] known_limits=[K6] mismatches=[K7] | got total={r['total']} ok={r['ok']} holes={r['holes']} false_refusals={r['false_refusals']} known_limits={r['known_limits']} mismatches={r['mismatches']}")

    # Test 2
    sl = summary_line(bench(DOC, FAKE_JUDGE))
    ec1 = exit_code(bench(DOC, FAKE_JUDGE))
    ec2 = exit_code(bench({"config": {}, "cases": [DOC["cases"][5]]}, FAKE_JUDGE))
    sl0 = summary_line(bench({"config": {}, "cases": []}, FAKE_JUDGE))
    ok2 = (sl == "cases 7 | ok 2 | holes 2 | false refusals 1 | known limits 1 | mismatches 1"
           and ec1 == 1 and ec2 == 0
           and sl0 == "cases 0 | ok 0 | holes 0 | false refusals 0 | known limits 0 | mismatches 0")
    if ok2:
        print("PASS 2 summary_line and exit_code values correct")
        passed += 1
    else:
        print(f"FAIL 2 expected summary/exit codes | got sl={sl} ec1={ec1} ec2={ec2} sl0={sl0}")

    # Test 3
    configs = []
    def _recording_judge(cmd, cfg):
        configs.append(cfg)
        return {"verdict": "free", "targets": [], "reason": "x"}
    bench({"config": {"k": 1}, "cases": [DOC["cases"][0]]}, _recording_judge)
    r_real = bench(REAL)
    ok3 = configs == [{"k": 1}] and r_real["ok"] == 2
    if ok3:
        print("PASS 3 config recorded as [{k:1}] and real judge ok=2")
        passed += 1
    else:
        print(f"FAIL 3 expected configs=[{{'k': 1}}] ok=2 | got configs={configs} ok={r_real['ok']}")

    # Test 4
    with tempfile.TemporaryDirectory() as td:
        p_real = os.path.join(td, "real.json")
        p_hole = os.path.join(td, "hole.json")
        with open(p_real, "w", encoding="utf-8") as f:
            json.dump(REAL, f)
        with open(p_hole, "w", encoding="utf-8") as f:
            json.dump(REAL_HOLE, f)
        proc_r = subprocess.run([sys.executable, os.path.abspath(__file__), "--cases", p_real],
                                capture_output=True, text=True)
        proc_h = subprocess.run([sys.executable, os.path.abspath(__file__), "--cases", p_hole],
                                capture_output=True, text=True)
    rl = proc_r.stdout.strip().split("\n") if proc_r.stdout.strip() else []
    hl = proc_h.stdout.strip().split("\n") if proc_h.stdout.strip() else []
    ok4 = (proc_r.returncode == 0
           and (rl[-1] if rl else "") == "cases 2 | ok 2 | holes 0 | false refusals 0 | known limits 0 | mismatches 0"
           and proc_h.returncode == 1
           and (hl[0] if hl else "") == "HOLE S2 expect=write got=free ls")
    if ok4:
        print("PASS 4 subprocess REAL rc=0 last-line summary; REAL_HOLE rc=1 first-line HOLE")
        passed += 1
    else:
        print(f"FAIL 4 expected REAL rc=0+summary, HOLE rc=1+line | got rc={proc_r.returncode}/{proc_h.returncode} last={rl[-1] if rl else ''} first={hl[0] if hl else ''}")

    # Test 5
    proc_n = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"],
                            capture_output=True, text=True)
    proc_0 = subprocess.run([sys.executable, os.path.abspath(__file__)],
                            capture_output=True, text=True)
    with tempfile.TemporaryDirectory() as td:
        p_miss = os.path.join(td, "nope.json")
        proc_m = subprocess.run([sys.executable, os.path.abspath(__file__), "--cases", p_miss],
                                capture_output=True, text=True)
    ok5 = (proc_n.returncode == 0
           and proc_n.stdout.startswith("NAME      shell_bench.py")
           and proc_0.returncode == 2
           and proc_0.stdout == "usage: shell_bench.py --cases FILE | --notice | --autotest\n"
           and proc_m.returncode == 2
           and proc_m.stdout == "error: cannot read cases file\n")
    if ok5:
        print("PASS 5 notice rc=0, noarg rc=2 usage, missing rc=2 error")
        passed += 1
    else:
        print(f"FAIL 5 expected notice/noarg/missing | got n_rc={proc_n.returncode} 0_rc={proc_0.returncode} 0_out={repr(proc_0.stdout)} m_rc={proc_m.returncode} m_out={repr(proc_m.stdout)}")

    sys.exit(0 if passed == 5 else 1)

def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        _autotest()
        return
    if len(sys.argv) == 3 and sys.argv[1] == "--cases":
        path = sys.argv[2]
        try:
            with open(path, "r", encoding="utf-8") as f:
                doc = json.load(f)
        except Exception:
            print("error: cannot read cases file")
            sys.exit(2)
        if "cases" not in doc:
            print("error: cannot read cases file")
            sys.exit(2)
        result = bench(doc)
        for line in result["lines"]:
            print(line)
        print(summary_line(result))
        sys.exit(exit_code(result))
    print("usage: shell_bench.py --cases FILE | --notice | --autotest")
    sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "shell_bench", sys.argv[1:])
