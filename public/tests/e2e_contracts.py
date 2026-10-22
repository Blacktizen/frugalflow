import sys
import os
import json
import subprocess
import tempfile
import shutil

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

TOOLS = [
    "notice_rules.py",
    "notice_check.py",
    "config_rules.py",
    "layers.py",
    "ceilings.py",
    "config_check.py",
    "bite.py",
    "install_hooks.py",
]


def run(tool, args, D):
    return subprocess.run(
        [sys.executable, os.path.join(BIN, tool)] + args,
        capture_output=True,
        text=True,
        cwd=D,
    )


def check(r, expected_code, expected_line=None):
    lines = r.stdout.splitlines()
    if not lines:
        return False, "empty stdout"
    if r.returncode != expected_code:
        return False, "code={} expected={}".format(r.returncode, expected_code)
    if expected_line is not None and expected_line not in lines:
        return False, "missing exact line (code={})".format(r.returncode)
    return True, "code={}".format(r.returncode)


def main():
    D = tempfile.mkdtemp()
    try:
        os.makedirs(os.path.join(D, "home"), exist_ok=True)
        os.makedirs(os.path.join(D, "leaky"), exist_ok=True)
        os.makedirs(os.path.join(D, "repo", ".git", "hooks"), exist_ok=True)
        os.makedirs(os.path.join(D, "repo", "public", "hooks"), exist_ok=True)

        models = {
            "schema_version": "1",
            "models": [
                {
                    "id": "a",
                    "name": "m",
                    "location": "local",
                    "endpoint": "http://127.0.0.1:8000/v1",
                    "context_window": 65536,
                    "paid": False,
                    "trust": "private",
                    "key_env": "",
                },
                {
                    "id": "r",
                    "name": "n",
                    "location": "remote",
                    "endpoint": "https://api.example.com/v1",
                    "context_window": 131072,
                    "paid": True,
                    "trust": "untrusted_third_party",
                    "key_env": "REMOTE_KEY",
                },
            ],
            "layers": [
                {"name": "reading", "delegable": True},
                {"name": "kept", "delegable": False},
            ],
            "roles": [
                {"name": "code", "layer": "reading", "model": "a"},
                {"name": "remote", "layer": "reading", "model": "r"},
                {"name": "judgment", "layer": "kept", "model": ""},
            ],
        }
        with open(os.path.join(D, "home", "models.json"), "w", encoding="utf-8") as f:
            json.dump(models, f)

        leaky_models = json.loads(json.dumps(models))
        leaky_models["models"][0]["api_key"] = "abc123"
        with open(os.path.join(D, "leaky", "models.json"), "w", encoding="utf-8") as f:
            json.dump(leaky_models, f)

        prefs = {
            "schema_version": "1",
            "verbosity": {"final_answer_words": 150, "step_message_words": 35},
            "ceilings": {
                "max_trust": "trusted_third_party",
                "max_tries": 3,
                "max_output_tokens": 60000,
            },
            "splitting": {"max_proofs_per_task": 5, "max_brief_lines": 140},
            "grouping": {"independent_calls_same_turn": True},
        }
        with open(os.path.join(D, "home", "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs, f)
        with open(os.path.join(D, "leaky", "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs, f)

        with open(os.path.join(D, "tight.json"), "w", encoding="utf-8") as f:
            json.dump({"schema_version": "1", "ceilings": {"max_trust": "private"}}, f)
        with open(os.path.join(D, "loose.json"), "w", encoding="utf-8") as f:
            json.dump(
                {"schema_version": "1", "ceilings": {"max_trust": "untrusted_third_party"}},
                f,
            )

        with open(os.path.join(D, "silent.py"), "w", encoding="utf-8") as f:
            f.write("import sys\n")

        with open(
            os.path.join(D, "repo", "public", "hooks", "pre-commit"), "wb"
        ) as f:
            f.write(b"#!/bin/sh\nexit 0\n")

        # --- Test 1 ---
        e1_expected = "code=0+NOTICES OK 8 / code=7+NO silent.py: empty notice"
        r = run("notice_check.py", [os.path.join(BIN, t) for t in TOOLS], D)
        ok, detail = check(r, 0, "NOTICES OK 8")
        if not ok:
            e1_got = detail
        else:
            r2 = run("notice_check.py", [os.path.join(D, "silent.py")], D)
            ok, e1_got = check(r2, 7, "NO silent.py: empty notice")
        results = [("PASS" if ok else "FAIL", "1", e1_expected, e1_got)]

        # --- Test 2 ---
        e2_expected = (
            "code=0+ceilings.max_trust=trusted_third_party(preferences) / "
            "code=0+ceilings.max_trust=private(project)"
        )
        r = run("config_check.py", ["--home", os.path.join(D, "home")], D)
        ok, detail = check(r, 0, "  ceilings.max_trust = trusted_third_party  (preferences)")
        if not ok:
            e2_got = detail
        else:
            r2 = run(
                "config_check.py",
                ["--home", os.path.join(D, "home"), "--project", os.path.join(D, "tight.json")],
                D,
            )
            ok, e2_got = check(r2, 0, "  ceilings.max_trust = private  (project)")
        results.append(("PASS" if ok else "FAIL", "2", e2_expected, e2_got))

        # --- Test 3 ---
        e3_expected = "code=8+NO loose.json: project loosens ceilings.max_trust"
        r = run(
            "config_check.py",
            ["--home", os.path.join(D, "home"), "--project", os.path.join(D, "loose.json")],
            D,
        )
        ok, e3_got = check(
            r,
            8,
            "  NO loose.json: project loosens ceilings.max_trust: untrusted_third_party > trusted_third_party",
        )
        results.append(("PASS" if ok else "FAIL", "3", e3_expected, e3_got))

        # --- Test 4 ---
        e4_expected = (
            "code=8+ROUTE remote REFUSED / "
            "code=8+ROUTE judgment REFUSED / "
            "code=8+NO models.json: secret value at models[0].api_key"
        )
        r = run(
            "config_check.py",
            ["--home", os.path.join(D, "home"), "--project", os.path.join(D, "tight.json"), "--role", "remote"],
            D,
        )
        ok, detail = check(
            r,
            8,
            "ROUTE remote REFUSED: model r trust untrusted_third_party exceeds ceiling private",
        )
        if not ok:
            e4_got = detail
        else:
            r2 = run(
                "config_check.py",
                ["--home", os.path.join(D, "home"), "--role", "judgment"],
                D,
            )
            ok, detail = check(
                r2,
                8,
                "ROUTE judgment REFUSED: role judgment is in kept layer kept: it is never delegated",
            )
            if not ok:
                e4_got = detail
            else:
                r3 = run("config_check.py", ["--home", os.path.join(D, "leaky")], D)
                ok, e4_got = check(
                    r3,
                    8,
                    "  NO models.json: secret value at models[0].api_key: name an environment variable in key_env instead",
                )
        results.append(("PASS" if ok else "FAIL", "4", e4_expected, e4_got))

        # --- Test 5 ---
        e5_expected = "code=11 / code=0 / code=0+HOOK OK"
        r = run(
            "install_hooks.py",
            ["--repo", os.path.join(D, "repo"), "--check"],
            D,
        )
        ok, detail = check(r, 11)
        if not ok:
            e5_got = detail
        else:
            r2 = run("install_hooks.py", ["--repo", os.path.join(D, "repo")], D)
            ok, detail = check(r2, 0)
            if not ok:
                e5_got = detail
            else:
                r3 = run(
                    "install_hooks.py",
                    ["--repo", os.path.join(D, "repo"), "--check"],
                    D,
                )
                ok, e5_got = check(r3, 0, "HOOK OK")
        results.append(("PASS" if ok else "FAIL", "5", e5_expected, e5_got))

        for status, num, expected, got in results:
            print("{} {} | expected: {} | got: {}".format(status, num, expected, got))

        n_pass = sum(1 for s, _, _, _ in results if s == "PASS")
        print("E2E CONTRACTS: {} of 5".format(n_pass))
        return 0 if n_pass == 5 else 1
    finally:
        shutil.rmtree(D, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
