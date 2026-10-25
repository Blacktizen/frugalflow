import json
import os
import shutil
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(os.path.dirname(HERE), "bin")
sys.path.insert(0, HERE)
import e2e_security as S

NAME = "Zorbax" + "Holt"
SECRET = "KEY=" + "QX7Z9ABCD1234"

NOTICE = (
    "NAME      e2e_outbound_system.py - proves the --system message of delegate.py is filtered like the prompt.\n"
    "READS     the tools in ../bin; a local fake engine captures the serialized request.\n"
    "WRITES    temporary folders only; one PASS or FAIL line per case, then E2E OUTBOUND OK (0) or FAILED (1).\n"
    "EXAMPLE   python3 e2e_outbound_system.py\n"
    "PITFALLS  2026-10-25 --system was sent verbatim while the prompt was filtered."
)


def run(port, role, system):
    home = S.make_home(port, None, None, with_rules=False)
    with open(os.path.join(home, "anonymization.json"), "w") as f:
        json.dump({
            "anonymizable": [{"pattern": "\\b" + NAME + "\\b", "label": "person", "tag": "PERSON"}],
            "irreducible": [{"pattern": "KEY=[A-Z0-9]{8,}", "label": "key"}],
        }, f)
    with open(os.path.join(home, "task.md"), "w") as f:
        f.write("NATURE: creation\nWrite print(42). Owner " + NAME + ".\n")
    env = os.environ.copy()
    env["FRUGALFLOW_HOME"] = home
    env["FRUGALFLOW_BRIEF_RULES"] = os.path.join(home, "rules.json")
    S.BODIES.clear()
    p = subprocess.run(
        [sys.executable, os.path.join(BIN, "delegate.py"), "--timeout", "10", "--file", "task.md",
         "--role", role, "--out", "a.py", "--system", system]
        + (["--trust", "untrusted_third_party"] if role == "far" else []),
        cwd=home, env=env, capture_output=True, text=True, timeout=180)
    wire = json.dumps(S.BODIES)
    shutil.rmtree(home, ignore_errors=True)
    return p.returncode, wire, len(S.BODIES)


def main():
    server, port = S.start_engine()
    results = []

    code, wire, calls = run(port, "code", "You work for " + NAME + ".")
    results.append(("control: private model receives the system text (capture works)",
                    calls >= 1 and NAME in wire and "work for" in wire))

    code, wire, calls = run(port, "far", "You work for " + NAME + ".")
    results.append(("untrusted: name in prompt AND --system never reaches the wire",
                    calls >= 1 and NAME not in wire and "work for" in wire))

    code, wire, calls = run(port, "far", "token " + SECRET)
    results.append(("untrusted: secret in --system refuses, nothing sent",
                    code == 4 and calls == 0 and SECRET not in wire))

    server.shutdown()
    ok = True
    for i, (name, good) in enumerate(results, 1):
        print(("PASS " if good else "FAIL ") + str(i) + " " + name)
        ok = ok and good
    print("E2E OUTBOUND OK" if ok else "E2E OUTBOUND FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--notice" in sys.argv:
        print(NOTICE)
        sys.exit(0)
    main()
