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


def deny_cases():
    return [
        ("a", "python3 -c \"open('{P}','w').write('{{}}')\"", True),
        ("b", "python3 -c \"import pathlib; pathlib.Path('{P}').write_text('{{}}')\"", True),
        ("c", "python3 - <<EOF\nopen('{P}','w').write('{{}}')\nEOF", True),
        ("d", "python3 - <<'EOF'\nopen('{P}','w').write('{{}}')\nEOF", True),
        ("e", "perl -e 'open(F,\">{G}\",\"w\")'", True),
        ("f", "ruby -e 'File.write(\"{G}\",\"{{}}\")'", True),
        ("g", "node -e \"require('fs').writeFileSync('{G}','{{}}')\"", True),
        ("h", "sh -c \"echo x > {M}\"", True),
        ("i", "echo x | tee {P}", True),
        ("j", "cp /tmp/x {G}", True),
        ("k", "mv /tmp/x {G}", True),
        ("l", "ln -sf /tmp/x {P}", True),
        ("m", "dd if=/dev/zero of={P} count=1", True),
        ("n", "python3 -c \"import os; os.system('echo x > {P}')\"", True),
        ("o", "python3 -c \"open('{P}','a').write('x')\"", True),
        ("p", "php -r \"file_put_contents('{P}','{{}}');\"", True),
        ("q", "truncate -s0 {P}", True),
        ("r", "sed -i 's/true/false/' {P}", True),
        ("s", "awk 'BEGIN{{print > \"{P}\"}}'", True),
        ("t", "python -c \"open('{P}','w')\"", True),
    ]


def allow_cases():
    return [
        ("u", "python3 -c \"print(open('{P}').read())\"", False),
        ("v", "cat {P}", False),
    ]


def run_e2e():
    fail_k = 0
    case_num = 0

    for label, cmd_tpl, expected_deny in deny_cases():
        h = tempfile.mkdtemp(prefix="b2home-", dir="/tmp")
        P, M, _ = write_fixtures(h, "active")
        G = os.path.join(h, "guard.json")

        cmd = cmd_tpl.format(P=P, M=M, G=G)
        got = call_guard(h, "Bash", {"command": cmd})
        case_num += 1
        expected_str = "deny" if expected_deny else "allow"
        got_str = "deny" if got else "allow"
        ok = (got == expected_deny)
        tag = "PASS" if ok else "FAIL"
        if not ok:
            fail_k += 1
        print(f"{tag} {case_num} {label} | expected {expected_str} | got {got_str}")

    for label, cmd_tpl, expected_deny in allow_cases():
        h = tempfile.mkdtemp(prefix="b2home-", dir="/tmp")
        P, M, _ = write_fixtures(h, "active")
        G = os.path.join(h, "guard.json")

        cmd = cmd_tpl.format(P=P, M=M, G=G)
        got = call_guard(h, "Bash", {"command": cmd})
        case_num += 1
        expected_str = "deny" if expected_deny else "allow"
        got_str = "deny" if got else "allow"
        ok = (got == expected_deny)
        tag = "PASS" if ok else "FAIL"
        if not ok:
            fail_k += 1
        print(f"{tag} {case_num} {label} | expected {expected_str} | got {got_str}")

    return fail_k


def main():
    fail_k = run_e2e()
    if fail_k == 0:
        print("E2E PROTECTED WRITERS OK")
        sys.exit(0)
    else:
        print(f"E2E PROTECTED WRITERS FAILED {fail_k}")
        sys.exit(1)


if __name__ == "__main__":
    main()