#!/usr/bin/env python3
# e2e_false_refusals.py - end-to-end test for false refusals on proven-read unzip and safe writes

import json
import os
import shutil
import subprocess
import sys
import tempfile

# The hook is at ../bin/guard_hook.py relative to this test file
HOOK = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin", "guard_hook.py")

# Guard settings copied from guard.example.json
SETTINGS = {
    "code_extensions": [".py", ".sh", ".js", ".ts"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "quarantine_minutes": 45,
    "read_waiver_minutes": 10,
    "intake_max_lines": 300,
    "intake_max_bytes": 40000,
    "digest_extensions": [".md", ".log", ".txt", ".jsonl"],
    "digest_max_bytes": 70000,
    "digest_waiver": "manual-digest",
    "delegate_tools": ["delegate.py"],
    "fix_hint": "Delegate it: python3 bin/delegate.py --role code --file task.md --out <file>.",
    "checks": ["quarantine_read", "intake", "digest"]
}

MARKDOWN_30_LINES = "\n".join(f"# Line {i}\nSome content for line {i}." for i in range(1, 16)) + "\n"


def CALL(tool, inp):
    return json.dumps({"tool_name": tool, "tool_input": inp})


def run_hook(home, call, cwd="/tmp"):
    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home
    # Clean up guard-related env vars
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY"):
        env.pop(key, None)
    try:
        r = subprocess.run(
            [sys.executable, HOOK, "--hook"],
            input=call,
            capture_output=True,
            text=True,
            env=env,
            cwd=cwd,
            timeout=30,
        )
        return r.returncode, r.stdout.strip()
    except subprocess.TimeoutExpired:
        return -1, "timeout"


def decision(stdout):
    """Return 'allow' if stdout is empty, 'deny' if it contains permissionDecision deny, 'error' otherwise."""
    if stdout == "":
        return "allow"
    try:
        d = json.loads(stdout)
        pd = d.get("hookSpecificOutput", {}).get("permissionDecision")
        if pd == "deny":
            return "deny"
        return "allow"
    except Exception:
        return "error"


def setup_home(home):
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(SETTINGS, f)
    with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write("")


def run_case(name, home, tool, inp, expected, cwd="/tmp"):
    code, stdout = run_hook(home, CALL(tool, inp), cwd=cwd)
    got = decision(stdout)
    if code != 0:
        got = f"error(code={code})"
    ok = (got == expected)
    status = "PASS" if ok else "FAIL"
    print(f"{status} {name}: expected {expected} | got {got}")
    return ok


def main():
    all_pass = True
    with tempfile.TemporaryDirectory() as home:
        setup_home(home)

        # --- PERMITTED cases (expected allow) ---
        # 1. Bash "unzip -l /tmp/a.zip"
        all_pass &= run_case("1 unzip -l", home, "Bash", {"command": "unzip -l /tmp/a.zip"}, "allow")

        # 2. Bash "unzip -t /tmp/a.zip"
        all_pass &= run_case("2 unzip -t", home, "Bash", {"command": "unzip -t /tmp/a.zip"}, "allow")

        # 3. Bash "unzip -Z /tmp/a.zip"
        all_pass &= run_case("3 unzip -Z", home, "Bash", {"command": "unzip -Z /tmp/a.zip"}, "allow")

        # 4. Bash "unzip -v /tmp/a.zip"
        all_pass &= run_case("4 unzip -v", home, "Bash", {"command": "unzip -v /tmp/a.zip"}, "allow")

        # 5. Write file_path "/tmp/jetable/guard.json", content "{}\n"
        all_pass &= run_case("5 write /tmp/jetable/guard.json", home, "Write",
                             {"file_path": "/tmp/jetable/guard.json", "content": "{}\n"}, "allow")

        # 6. Write file_path "/tmp/x/consignes/a7d.md", content: 30 lines of markdown
        all_pass &= run_case("6 write /tmp/x/consignes/a7d.md", home, "Write",
                             {"file_path": "/tmp/x/consignes/a7d.md", "content": MARKDOWN_30_LINES}, "allow")

        # 7. Bash "cp /tmp/x/e2e_a.py /tmp/wt/base/public/tests/ && cd /tmp/wt/base && python3 public/tests/e2e_a.py; rm /tmp/wt/base/public/tests/e2e_a.py; git -C /tmp/wt/base status --short"
        cmd7 = "cp /tmp/x/e2e_a.py /tmp/wt/base/public/tests/ && cd /tmp/wt/base && python3 public/tests/e2e_a.py; rm /tmp/wt/base/public/tests/e2e_a.py; git -C /tmp/wt/base status --short"
        all_pass &= run_case("7 complex cp+git", home, "Bash", {"command": cmd7}, "allow")

        # 8. Bash "git -C /tmp/r status --short"
        all_pass &= run_case("8 git status", home, "Bash", {"command": "git -C /tmp/r status --short"}, "allow")

        # 9. Bash "git -C /tmp/r show HEAD --stat"
        all_pass &= run_case("9 git show", home, "Bash", {"command": "git -C /tmp/r show HEAD --stat"}, "allow")

        # --- DENIED cases (expected deny) ---
        # 10. Write file_path "{home}/guard.json", content "{}\n"
        all_pass &= run_case("10 write home/guard.json", home, "Write",
                             {"file_path": os.path.join(home, "guard.json"), "content": "{}\n"}, "deny")

        # 11. Bash "unzip a.zip -d {home}"
        all_pass &= run_case("11 unzip -d home", home, "Bash",
                             {"command": f"unzip a.zip -d {home}"}, "deny")

        # 12. Bash "cp /tmp/x {home}/preferences.json"
        all_pass &= run_case("12 cp to home/preferences.json", home, "Bash",
                             {"command": f"cp /tmp/x {home}/preferences.json"}, "deny")

        # 13. Bash "rm {home}/blocks/guard.jsonl"
        all_pass &= run_case("13 rm home/blocks/guard.jsonl", home, "Bash",
                             {"command": f"rm {home}/blocks/guard.jsonl"}, "deny")

        # 14. Bash "unzip a.zip" (extraction in current directory: deny)
        all_pass &= run_case("14 unzip extract cwd", home, "Bash",
                             {"command": "unzip a.zip"}, "deny")

        # 15. Bash "unzip -o a.zip" (forced extraction: deny)
        all_pass &= run_case("15 unzip -o forced", home, "Bash",
                             {"command": "unzip -o a.zip"}, "deny")

    if all_pass:
        print("ALL 15 CASES PASS")
        sys.exit(0)
    else:
        print("SOME CASES FAILED")
        sys.exit(1)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(
            "NAME      e2e_false_refusals.py - end-to-end test for false refusals on proven-read unzip and safe writes\n"
            "READS     ../bin/guard_hook.py; creates a temporary FRUGALFLOW_HOME with guard.json and delegations.jsonl\n"
            "WRITES    one PASS or FAIL line per case (15 total), then summary. Exits 0 if all pass, 1 otherwise.\n"
            "EXAMPLE   python3 e2e_false_refusals.py\n"
            "PITFALLS  The test never executes the commands; they are only given to the hook as text."
        )
        sys.exit(0)
    main()