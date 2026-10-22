import sys
import os
import re
import subprocess

PATTERNS = [
    r"max_model_len\D*([\d,]{2,})",
    r"maximum context length is\s*([\d,]{2,})",
    r"context (?:length|size|window)\D*([\d,]{2,})",
    r"n_ctx\s*=\s*([\d,]{2,})",
]

VLLM = "max_completion_tokens=99002 cannot be greater than max_model_len=max_total_tokens=65536"
OPENAI = "This model's maximum context length is 65,536 tokens. However, you requested 70,000 tokens."
LLAMA = "request (9000 tokens) exceeds the available context size (8192 tokens), try increasing it"
NCTX = "failed to fit: n_ctx = 4096"
OTHER = "rate limit reached, retry in 20 s"

def read_overflow(text):
    if not isinstance(text, str) or text == "":
        return None
    for pattern in PATTERNS:
        m = re.search(pattern, text, re.I)
        if m:
            cleaned = m.group(1).replace(",", "")
            if re.fullmatch(r"\d{2,}", cleaned) and int(cleaned) > 0:
                return int(cleaned)
    return None

def estimate_prompt(chars, messages):
    return (chars + 2) // 3 + 64 * messages + 512

def plan_max_tokens(window, chars, messages, max_output, floor=256):
    room = window - estimate_prompt(chars, messages)
    if room < floor:
        return (None, "the prompt leaves " + str(room) + " tokens in a window of " + str(window) + ": split the task")
    if max_output is None:
        return (room, None)
    else:
        return (min(max_output, room), None)

def print_notice():
    notice = """NAME      budget_rules.py - sizes the output budget so a prompt fits the window, and reads the real limit from an engine's overflow error.
READS     nothing: pure module; it works on the numbers and the error text it is given.
WRITES    nothing: plan_max_tokens() returns the budget or a refusal; read_overflow() the limit or None.
EXAMPLE   python3 budget_rules.py --notice
PITFALLS  2026-09-17 the advertised window was not the served one; the engine's own error states the real limit.
          A prompt that leaves less than the floor is refused: split the task."""
    print(notice)

def run_autotest():
    failures = 0

    # Test 1
    actual = (read_overflow(VLLM), read_overflow(OPENAI), read_overflow(LLAMA))
    expected = (65536, 65536, 8192)
    condition = actual == expected
    if condition:
        print(f"PASS test 1: expected {expected}, got {actual}")
    else:
        print(f"FAIL test 1: expected {expected}, got {actual}")
        failures += 1

    # Test 2
    actual = (read_overflow(NCTX), read_overflow(OTHER), read_overflow(""), read_overflow(None))
    expected = (4096, None, None, None)
    condition = actual == expected
    if condition:
        print(f"PASS test 2: expected {expected}, got {actual}")
    else:
        print(f"FAIL test 2: expected {expected}, got {actual}")
        failures += 1

    # Test 3
    r1 = estimate_prompt(3000, 2)
    r2 = estimate_prompt(3001, 2)
    r3 = plan_max_tokens(8192, 3000, 2, 60000)
    r4 = plan_max_tokens(8192, 3000, 2, 4000)
    cond1 = r1 == 1640
    cond2 = r2 == 1641
    cond3 = r3 == (6552, None)
    cond4 = r4 == (4000, None)
    condition = cond1 and cond2 and cond3 and cond4
    print(f"{'PASS' if condition else 'FAIL'} test 3: estimate_prompt(3000,2)==1640 (got {r1}), estimate_prompt(3001,2)==1641 (got {r2}), plan_max_tokens(8192,3000,2,60000)==(6552,None) (got {r3}), plan_max_tokens(8192,3000,2,4000)==(4000,None) (got {r4})")
    if not condition:
        failures += 1

    # Test 4
    r1 = plan_max_tokens(2000, 3000, 2, 4000)
    r2 = plan_max_tokens(1800, 3000, 2, 4000)
    r3 = plan_max_tokens(8192, 3000, 2, None)
    cond1 = r1 == (360, None)
    cond2 = r2 == (None, "the prompt leaves 160 tokens in a window of 1800: split the task")
    cond3 = r3 == (6552, None)
    condition = cond1 and cond2 and cond3
    print(f"{'PASS' if condition else 'FAIL'} test 4: plan_max_tokens(2000,3000,2,4000)==(360,None) (got {r1}), plan_max_tokens(1800,3000,2,4000)==(None, message) (got {r2}), plan_max_tokens(8192,3000,2,None)==(6552,None) (got {r3})")
    if not condition:
        failures += 1

    # Test 5
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        code = proc.returncode
        stdout = proc.stdout
        condition = (code == 0) and stdout.startswith("NAME      budget_rules.py")
        print(f"{'PASS' if condition else 'FAIL'} test 5: returncode==0 and stdout starts with 'NAME      budget_rules.py'; got returncode={code}, stdout start={stdout[:30]!r}")
        if not condition:
            failures += 1
    except Exception as e:
        print(f"FAIL test 5: exception {e}")
        failures += 1

    if failures:
        sys.exit(1)
    else:
        sys.exit(0)

def main():
    if len(sys.argv) == 1:
        print("usage: budget_rules.py --notice | --autotest")
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        print_notice()
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        run_autotest()
    else:
        print("usage: budget_rules.py --notice | --autotest")
        sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "budget_rules", sys.argv[1:])
