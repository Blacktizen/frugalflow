import sys
import os
import subprocess

GROUPS = [
    ("checks", ["card_rules.py", "card_check.py", "sampling_rules.py", "sampling_check.py", "bench_rules.py", "bench_check.py"]),
    ("measure", ["journal_rules.py", "journal_log.py", "usage_rules.py", "ledger_rules.py", "usage_report.py"]),
    ("send", ["send_rules.py", "budget_rules.py", "answer_rules.py"]),
    ("delegate", ["engine_lock.py", "delegate_call.py", "delegate_prep.py", "delegate.py"]),
]
PURE = ["card_rules.py", "sampling_rules.py", "bench_rules.py", "journal_rules.py", "usage_rules.py", "ledger_rules.py", "send_rules.py", "budget_rules.py", "answer_rules.py"]

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

def run(name, args):
    cmd = [sys.executable, os.path.join(BIN, name)] + args
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180, cwd=BIN)
        return result.returncode
    except subprocess.TimeoutExpired:
        return -1

def run_tests():
    global_ok = True

    # Tests 1 to 4
    for idx, (group_name, tools) in enumerate(GROUPS, start=1):
        failures = []
        for tool in tools:
            code = run(tool, ["--autotest"])
            if code != 0:
                failures.append((tool, code))
        if len(tools) == 0 or failures:
            global_ok = False
            print(f"FAIL {idx} {group_name}: expected 0 for all, got {failures}")
        else:
            k = len(tools)
            print(f"PASS {idx} {group_name}: {k}/{k} autotests at 0")

    # Test 5
    pure_failures = []
    for tool in PURE:
        code = run(tool, [])
        if code != 2:
            pure_failures.append((tool, code))
    if len(PURE) == 0 or pure_failures:
        global_ok = False
        print(f"FAIL 5 pure: expected 2, got {pure_failures}")
    else:
        k = len(PURE)
        print(f"PASS 5 pure: {k}/{k} exit 2 without argument")

    if global_ok:
        print("E2E DELEGATION CORE OK")
    else:
        print("E2E DELEGATION CORE FAILED")
    return 0 if global_ok else 1

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        print("NAME      e2e_delegation_core.py - runs the self-test of the 18 tools of the delegation core and checks the pure modules refuse to run without an argument.")
        print("READS     the tools in ../bin next to this file.")
        print("WRITES    nothing: one PASS or FAIL line per group, then E2E DELEGATION CORE OK (0) or E2E DELEGATION CORE FAILED (1).")
        print("EXAMPLE   python3 e2e_delegation_core.py")
        print("PITFALLS  2026-09-23 a green self-test proves nothing alone; this suite must be seen red by bite.py before it is trusted.")
        sys.exit(0)
    else:
        sys.exit(run_tests())
