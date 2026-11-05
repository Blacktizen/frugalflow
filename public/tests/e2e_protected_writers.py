import json
import os
import subprocess
import sys
import tempfile

NOTICE = (
    "NAME      e2e_protected_writers.py - end-to-end test that the guard "
    "hook refuses writes to protected paths (preferences.json, models.json, "
    "guard.json, delegations.jsonl) and vault journals (log.md beside "
    "overview.md or SCHEMA.md).\n"
    "READS     the guard_hook.py in ../bin; the temporary home directory.\n"
    "WRITES    only in temporary folders, always removed. Exit 0 all "
    "steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_protected_writers.py\n"
    "PITFALLS  2026-11-05 deno/lua/osascript/Rscript/tclsh/awk writers were "
    "not covered: they can overwrite preferences.json without the hook "
    "seeing a Python-level write. 2026-11-05 git add/commit of a vault "
    "journal (log.md) are readers and must not be refused; only write/move/remove "
    "verbs that target the journal are denied.\n"
)

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
    # Vault directory V = h/vault with overview.md and log.md (L)
    v = os.path.join(h, "vault")
    os.makedirs(v, exist_ok=True)
    with open(os.path.join(v, "overview.md"), "w"):
        pass
    l = os.path.join(v, "log.md")
    with open(l, "w"):
        pass
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
    return p, m, l, content


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
        ("u", "deno eval \"Deno.writeTextFileSync('{P}','{{}}')\"", True),
        ("v", "lua -e \"io.open('{P}','w'):write('{{}}')\"", True),
        ("w", "osascript -e \"do shell script \\\"echo x > {P}\\\"\"", True),
        ("x", "Rscript -e \"writeLines('x', '{P}')\"", True),
        ("y", "tclsh <<EOF\nset f [open {P} w]; puts $f x; close $f\nEOF", True),
        ("z", "awk 'BEGIN{{print > \"{P}\"}}'", True),
        ("aa", "git config --file {P} core.bare true", True),
        # Git write verbs targeting P (preferences.json) - must be denied
        ("ab", "git checkout -- {P}", True),
        ("ac", "git restore {P}", True),
        ("ad", "git mv {P} {H}/x.json", True),
        ("ae", "git rm {P}", True),
        ("af", "git stash push -- {P}", True),
        ("ag", "git log > {P}", True),
        # Git write verbs targeting L (vault log.md) - must be denied
        ("ah", "git checkout -- {L}", True),
        ("ai", "git restore {L}", True),
        ("aj", "git mv {L} {V}/x.md", True),
        ("ak", "git rm {L}", True),
        ("al", "git status > {L}", True),
        ("am", "git blame {L} > {P}", True),
    ]


def allow_cases():
    return [
        ("u", "python3 -c \"print(open('{P}').read())\"", False),
        ("v", "cat {P}", False),
        ("w", "grep x {P}", False),
        ("x", "jq . {P}", False),
        ("y", "python3 -c \"print(open('{P}').read())\"", False),
        # Git readers and index/history for P (preferences.json) - must be allowed
        ("za", "git add {P}", False),
        ("zb", "git commit -m x {P}", False),
        ("zc", "git diff {P}", False),
        ("zd", "git log {P}", False),
        ("ze", "git show {P}", False),
        # Git readers and index/history for L (vault log.md) - must be allowed
        ("zf", "git add {L}", False),
        ("zg", "git commit -m x {L}", False),
        ("zh", "git status {L}", False),
        ("zi", "git blame {L}", False),
        # Control: non-protected path, same verbs - must be allowed
        ("zj", "git add notes.txt", False),
        ("zk", "git commit -m x notes.txt", False),
    ]


def run_e2e():
    fail_k = 0
    case_num = 0

    for label, cmd_tpl, expected_deny in deny_cases():
        h = tempfile.mkdtemp(prefix="b2home-", dir="/tmp")
        P, M, L, _ = write_fixtures(h, "active")
        G = os.path.join(h, "guard.json")
        V = os.path.join(h, "vault")

        cmd = cmd_tpl.format(P=P, M=M, G=G, H=h, V=V, L=L)
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
        P, M, L, _ = write_fixtures(h, "active")
        G = os.path.join(h, "guard.json")
        V = os.path.join(h, "vault")

        cmd = cmd_tpl.format(P=P, M=M, G=G, H=h, V=V, L=L)
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


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if len(argv) == 1 and argv[0] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(argv) > 0:
        sys.stderr.write("usage: e2e_protected_writers.py [--notice]\n")
        return 2

    fail_k = run_e2e()
    if fail_k == 0:
        print("E2E PROTECTED WRITERS OK")
        return 0
    else:
        print(f"E2E PROTECTED WRITERS FAILED {fail_k}")
        return 1


if __name__ == "__main__":
    sys.exit(main())