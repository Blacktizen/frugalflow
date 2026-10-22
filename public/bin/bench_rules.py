import sys
import os
import subprocess

PROBES = [
    ("echo", "Reply with exactly the word PONG, nothing else.", "PONG"),
    ("calc", "What is 17 times 23? Reply with the number only.", "391"),
    ("instruction", "Reply only YES or NO. Is seven greater than three?", "YES"),
]

NOTICE = """NAME      bench_rules.py - judges a three-question bench: right answers, and answered by the expected model.
READS     nothing: pure module; it judges the answers it is given.
WRITES    nothing: verdict() returns ok and the reason, render() the report lines.
EXAMPLE   python3 bench_rules.py --notice
PITFALLS  2026-08-23 an engine answered with another model; an answer without the expected model field is now a refusal.
          2026-09-23 a number was found inside a longer one (391 in 3910); answers are compared whole."""

USAGE = "usage: bench_rules.py --notice | --autotest"

def ans(probe, content, model="alpha-7b", error=None, tokens=5, ms=100):
    return {"probe": probe, "model": model, "content": content, "error": error, "tokens": tokens, "ms": ms}

GOOD = [ans("echo", "  pong.  "), ans("calc", "391"), ans("instruction", "Yes!")]
WRONG = [ans("echo", "PONG"), ans("calc", "3910"), ans("instruction", "YES")]
SUBST = [ans("echo", "PONG"), ans("calc", "391", model=None), ans("instruction", "YES")]
DOWN = [ans("echo", None, model=None, error="refused", tokens=0, ms=3), ans("calc", None, model=None, error="refused", tokens=0, ms=3), ans("instruction", None, model=None, error="refused", tokens=0, ms=4)]

def normalize(text):
    if not isinstance(text, str):
        return ""
    return "".join(c for c in text.upper() if c.isalnum())

def judge_answer(content, expected):
    return normalize(content) == normalize(expected)

def _expected_for_probe(probe):
    for name, _, expected in PROBES:
        if probe == name:
            return expected
    return None

def _is_answer_ok(answer):
    """Return True if this answer passes the individual correctness checks."""
    error = answer.get("error")
    if error is not None:
        return False
    probe = answer.get("probe")
    expected = _expected_for_probe(probe)
    if expected is None:
        return False
    content = answer.get("content")
    return judge_answer(content, expected)

def verdict(expected_model, answers, required=3):
    total = len(answers)
    passed = 0
    failed = []
    for answer in answers:
        if _is_answer_ok(answer):
            passed += 1
        else:
            failed.append(answer.get("probe"))

    if total == 0:
        return {"ok": False, "reason": "no probe was answered", "passed": passed, "total": total, "failed": failed}

    # model substitution check: first answer without error and with wrong model
    for answer in answers:
        if answer.get("error") is None:
            model = answer.get("model")
            if model != expected_model:
                reason = "model substituted: expected " + expected_model + ", answered by " + str(model)
                return {"ok": False, "reason": reason, "passed": passed, "total": total, "failed": failed}

    if passed < required:
        reason = str(required) + " probes needed, " + str(passed) + " passed: " + ", ".join(failed)
        return {"ok": False, "reason": reason, "passed": passed, "total": total, "failed": failed}

    return {"ok": True, "reason": "", "passed": passed, "total": total, "failed": failed}

def throughput(answers):
    total_tokens = 0
    total_ms = 0
    for answer in answers:
        tokens = answer.get("tokens", 0)
        if tokens is None:
            tokens = 0
        ms = answer.get("ms", 0)
        if ms is None:
            ms = 0
        total_tokens += tokens
        total_ms += ms
    if total_ms == 0:
        return 0.0
    return round(total_tokens / (total_ms / 1000.0), 1)

def render(model_name, v, answers):
    lines = []
    thr = throughput(answers)
    if v["ok"]:
        first = "BENCH OK " + model_name + ": " + str(v["passed"]) + "/" + str(v["total"]) + ", " + str(thr) + " tokens/s"
    else:
        first = "BENCH REFUSED " + model_name + ": " + v["reason"]
    lines.append(first)

    for answer in answers:
        probe = answer.get("probe")
        error = answer.get("error")
        ms = answer.get("ms", 0)
        if ms is None:
            ms = 0
        if _is_answer_ok(answer):
            status = "ok"
        else:
            status = "NO"
        if error is not None:
            txt = "error: " + str(error)
        else:
            content = answer.get("content")
            txt = content if content is not None else ""
            txt = txt.replace("\n", " ")
            txt = txt[:60]
        lines.append("  " + status + " " + str(probe) + " (" + str(ms) + " ms) " + txt)
    return lines

def _run_autotest():
    failures = 0

    # Test 1
    expected1 = ("PONG", "", False, True)
    got1 = (normalize("  pong. "), normalize(None), judge_answer("3910", "391"), judge_answer("Yes!", "YES"))
    if got1 == expected1:
        print("PASS test 1")
    else:
        print(f"FAIL test 1: expected={expected1} got={got1}")
        failures += 1

    # Test 2
    v_good = verdict("alpha-7b", GOOD)
    thr_good = throughput(GOOD)
    expected_v_good = {"ok": True, "reason": "", "passed": 3, "total": 3, "failed": []}
    if not isinstance(v_good, dict):
        print(f"FAIL test 2: verdict expected type dict, got {type(v_good).__name__}")
        failures += 1
    elif not isinstance(thr_good, float):
        print(f"FAIL test 2: throughput expected type float, got {type(thr_good).__name__}")
        failures += 1
    elif v_good == expected_v_good and thr_good == 50.0:
        print("PASS test 2")
    else:
        print(f"FAIL test 2: expected verdict={expected_v_good}, throughput={50.0}; got verdict={v_good}, throughput={thr_good}")
        failures += 1

    # Test 3
    v_wrong = verdict("alpha-7b", WRONG)
    expected_wrong = {"ok": False, "reason": "3 probes needed, 2 passed: calc", "passed": 2, "total": 3, "failed": ["calc"]}
    if not isinstance(v_wrong, dict):
        print(f"FAIL test 3: verdict wrong expected type dict, got {type(v_wrong).__name__}")
        failures += 1
    else:
        reason_subst_expected = "model substituted: expected alpha-7b, answered by None"
        reason_empty_expected = "no probe was answered"
        v_subst = verdict("alpha-7b", SUBST)
        v_empty = verdict("alpha-7b", [])
        if v_wrong == expected_wrong and v_subst["reason"] == reason_subst_expected and v_empty["reason"] == reason_empty_expected:
            print("PASS test 3")
        else:
            print(f"FAIL test 3: expected wrong={expected_wrong}, subst_reason={reason_subst_expected}, empty_reason={reason_empty_expected}; got wrong={v_wrong}, subst_reason={v_subst.get('reason')}, empty_reason={v_empty.get('reason')}")
            failures += 1

    # Test 4
    v_down = verdict("alpha-7b", DOWN)
    thr_down = throughput(DOWN)
    rendered_good = render("alpha-7b", verdict("alpha-7b", GOOD), GOOD)
    rendered_down = render("alpha-7b", v_down, DOWN)
    reason_down_expected = "3 probes needed, 0 passed: echo, calc, instruction"
    expected_rendered_good = ["BENCH OK alpha-7b: 3/3, 50.0 tokens/s", "  ok echo (100 ms)   pong.  ", "  ok calc (100 ms) 391", "  ok instruction (100 ms) Yes!"]
    expected_down_line1 = "  NO echo (3 ms) error: refused"
    if not isinstance(v_down, dict):
        print(f"FAIL test 4: verdict down expected type dict, got {type(v_down).__name__}")
        failures += 1
    elif not isinstance(thr_down, float):
        print(f"FAIL test 4: throughput expected type float, got {type(thr_down).__name__}")
        failures += 1
    elif not isinstance(rendered_good, list) or not isinstance(rendered_down, list):
        print(f"FAIL test 4: render expected type list, got {type(rendered_good).__name__} and {type(rendered_down).__name__}")
        failures += 1
    elif v_down["reason"] == reason_down_expected and thr_down == 0.0 and rendered_good == expected_rendered_good and rendered_down[1] == expected_down_line1:
        print("PASS test 4")
    else:
        print(f"FAIL test 4: expected reason={reason_down_expected}, throughput={0.0}, rendered_good={expected_rendered_good}, down_line1={expected_down_line1}; got reason={v_down.get('reason')}, throughput={thr_down}, rendered_good={rendered_good}, rendered_down={rendered_down}")
        failures += 1

    # Test 5
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        out = proc.stdout
        code = proc.returncode
    except Exception as e:
        print(f"FAIL test 5: subprocess error: {e}")
        failures += 1
        out = ""
        code = -1
    else:
        if code == 0 and out.startswith("NAME      bench_rules.py"):
            print("PASS test 5")
        else:
            print(f"FAIL test 5: expected returncode=0 and stdout startswith 'NAME      bench_rules.py', got returncode={code}, stdout prefix={out[:50]!r}")
            failures += 1

    return failures

def main():
    args = sys.argv[1:]
    if len(args) == 0:
        print(USAGE)
        sys.exit(2)
    elif args[0] == "--notice":
        print(NOTICE, end="")
        sys.exit(0)
    elif args[0] == "--autotest":
        failures = _run_autotest()
        sys.exit(0 if failures == 0 else 1)
    else:
        print(USAGE)
        sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bench_rules", sys.argv[1:])
