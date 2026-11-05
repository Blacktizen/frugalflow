import json
import os
import subprocess
import sys
import tempfile


HOOK = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "bin",
    "guard_hook.py",
)


def call_guard(h, tool_name, tool_input):
    env = os.environ.copy()
    env["FRUGALFLOW_HOME"] = h
    payload = {"tool_name": tool_name, "tool_input": tool_input, "cwd": h}
    result = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
    )
    return '"deny"' in (result.stdout or "")


def write_fixtures(h, mode):
    p = os.path.join(h, "preferences.json")
    m = os.path.join(h, "models.json")
    with open(os.path.join(h, "guard.json"), "w") as f:
        json.dump(
            {
                "code_extensions": [".py"],
                "delegation_logs": [os.path.join(h, "delegations.jsonl")],
                "audit_log": os.path.join(h, "audit.jsonl"),
                "max_lines": 3,
            },
            f,
        )
    with open(os.path.join(h, "delegations.jsonl"), "w"):
        pass
    content = '{"switch": {"enabled": true, "mode": "' + mode + '"}}'
    with open(p, "w") as f:
        f.write(content)
    return p, m, content


def denial_calls(p, m):
    return [
        ("Write", {"file_path": p, "content": "{}"}),
        ("Edit", {"file_path": p, "old_string": "true", "new_string": "false"}),
        ("Write", {"file_path": m, "content": "{}"}),
        ("Bash", {"command": "printf x > " + p}),
        ("Bash", {"command": "frugalflow off"}),
        ("Bash", {"command": "frugalflow mode observe"}),
        ("Bash", {"command": "frugalflow config set switch.enabled false"}),
    ]


def read_calls(p):
    return [
        ("Bash", {"command": "frugalflow config"}),
        ("Bash", {"command": "frugalflow doctor"}),
        ("Bash", {"command": "cat " + p}),
    ]


def run_e2e():
    fail_k = 0

    h1 = tempfile.mkdtemp()
    p1, m1, content1 = write_fixtures(h1, "active")
    got1 = sum(1 for tn, ti in denial_calls(p1, m1) if call_guard(h1, tn, ti))
    ok1 = got1 == 7
    tag1 = "PASS" if ok1 else "FAIL"
    print(f"{tag1} 1 deny mutations active | expected 7 | got {got1}")
    if not ok1:
        fail_k += 1

    h2 = tempfile.mkdtemp()
    p2, m2, _ = write_fixtures(h2, "observe")
    got2 = sum(1 for tn, ti in denial_calls(p2, m2) if call_guard(h2, tn, ti))
    ok2 = got2 == 7
    tag2 = "PASS" if ok2 else "FAIL"
    print(f"{tag2} 2 deny mutations observe | expected 7 | got {got2}")
    if not ok2:
        fail_k += 1

    h3 = tempfile.mkdtemp()
    p3, m3, _ = write_fixtures(h3, "active")
    got3 = sum(1 for tn, ti in read_calls(p3) if not call_guard(h3, tn, ti))
    ok3 = got3 == 3
    tag3 = "PASS" if ok3 else "FAIL"
    print(f"{tag3} 3 allow reads | expected 3 | got {got3}")
    if not ok3:
        fail_k += 1

    with open(p1, "rb") as f:
        actual = f.read()
    expected_bytes = content1.encode("utf-8")
    got4 = 1 if actual == expected_bytes else 0
    ok4 = got4 == 1
    tag4 = "PASS" if ok4 else "FAIL"
    print(f"{tag4} 4 preferences intact | expected 1 | got {got4}")
    if not ok4:
        fail_k += 1

    # C3 cases
    fail_k += run_c3_cases()

    return fail_k


def run_c3_cases():
    """Test C3: Claude settings and .githooks protection."""
    fail_k = 0

    # H serves as both home and project (U = H, cwd = W = H)
    H = tempfile.mkdtemp()
    W = H
    U = H

    # Create minimal guard.json fixture like write_fixtures does
    with open(os.path.join(H, "guard.json"), "w") as f:
        json.dump(
            {
                "code_extensions": [".py"],
                "delegation_logs": [os.path.join(H, "delegations.jsonl")],
                "audit_log": os.path.join(H, "audit.jsonl"),
                "max_lines": 3,
            },
            f,
        )
    with open(os.path.join(H, "delegations.jsonl"), "w"):
        pass
    # preferences.json and models.json for the switch
    for name in ("preferences.json", "models.json"):
        with open(os.path.join(H, name), "w") as f:
            f.write('{"switch": {"enabled": true, "mode": "active"}}')

    # Ensure .claude and .githooks directories exist
    os.makedirs(os.path.join(W, ".claude"), exist_ok=True)
    os.makedirs(os.path.join(U, ".claude"), exist_ok=True)
    os.makedirs(os.path.join(W, ".githooks"), exist_ok=True)

    # a. Write W/.claude/settings.json -> deny
    tool_input = {"file_path": os.path.join(W, ".claude", "settings.json"), "content": "{}"}
    got = call_guard(H, "Write", tool_input)
    expected = True
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} a Write W/.claude/settings.json -> deny | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # b. Write W/.claude/settings.local.json -> deny
    tool_input = {"file_path": os.path.join(W, ".claude", "settings.local.json"), "content": "{}"}
    got = call_guard(H, "Write", tool_input)
    expected = True
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} b Write W/.claude/settings.local.json -> deny | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # c. Write U/.claude/settings.local.json -> deny
    tool_input = {"file_path": os.path.join(U, ".claude", "settings.local.json"), "content": "{}"}
    got = call_guard(H, "Write", tool_input)
    expected = True
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} c Write U/.claude/settings.local.json -> deny | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # d. Write W/.githooks/pre-commit -> deny
    tool_input = {"file_path": os.path.join(W, ".githooks", "pre-commit"), "content": "#!/bin/sh\nexit 0"}
    got = call_guard(H, "Write", tool_input)
    expected = True
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} d Write W/.githooks/pre-commit -> deny | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # e. Bash `echo '{"disableAllHooks":true}' > W/.claude/settings.json` -> deny
    tool_input = {"command": f"echo '{{\"disableAllHooks\":true}}' > {os.path.join(W, '.claude', 'settings.json')}"}
    got = call_guard(H, "Bash", tool_input)
    expected = True
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} e Bash echo > W/.claude/settings.json -> deny | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # f. Witness: Write W/.claude/agents/x.md -> allow
    os.makedirs(os.path.join(W, ".claude", "agents"), exist_ok=True)
    tool_input = {"file_path": os.path.join(W, ".claude", "agents", "x.md"), "content": "# Agent"}
    got = call_guard(H, "Write", tool_input)
    expected = False
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} f Write W/.claude/agents/x.md -> allow | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # g. Witness: Write W/notes.txt -> allow
    tool_input = {"file_path": os.path.join(W, "notes.txt"), "content": "notes"}
    got = call_guard(H, "Write", tool_input)
    expected = False
    ok = got == expected
    tag = "PASS" if ok else "FAIL"
    print(f"{tag} g Write W/notes.txt -> allow | expected {expected} | got {got}")
    if not ok:
        fail_k += 1

    # Cleanup
    import shutil
    shutil.rmtree(H, ignore_errors=True)

    return fail_k


def main():
    fail_k = run_e2e()
    if fail_k == 0:
        print("E2E SETTINGS GUARD OK")
        sys.exit(0)
    else:
        print(f"E2E SETTINGS GUARD FAILED {fail_k}")
        sys.exit(1)


if __name__ == "__main__":
    main()
