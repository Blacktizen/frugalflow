#!/usr/bin/env python3
"""
End-to-end test for finding C8: a hand-typed remote access point must not
land as location local with trust private, and a --models file from another
folder must not bring that folder's preferences.json as the ceilings.
"""

import os
import sys
import json
import shutil
import tempfile
import subprocess

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(TESTS_DIR))
sys.path.insert(0, os.path.join(ROOT, "public", "bin"))

import config_rules  # noqa: E402
import onboard_choice  # noqa: E402

DOC = {
    "schema_version": "1",
    "models": [
        {
            "id": "local-reader",
            "name": "m",
            "location": "local",
            "endpoint": "http://127.0.0.1:9000/v1",
            "context_window": 65536,
            "paid": False,
            "trust": "private",
            "key_env": "",
        },
        {
            "id": "remote-coder",
            "name": "n",
            "location": "remote",
            "endpoint": "https://api.example.com/v1",
            "context_window": 131072,
            "paid": True,
            "trust": "trusted_third_party",
            "key_env": "REMOTE_KEY",
        },
    ],
    "layers": [
        {"name": "reading", "delegable": True},
        {"name": "kept", "delegable": False},
    ],
    "roles": [
        {"name": "code", "layer": "reading", "model": "local-reader"},
        {"name": "judgment", "layer": "kept", "model": ""},
    ],
}

PREFS = {
    "schema_version": "1",
    "verbosity": {"final_answer_words": 120, "step_message_words": 30},
    "ceilings": {"max_trust": "trusted_third_party", "max_tries": 2, "max_output_tokens": 100},
    "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
    "grouping": {"independent_calls_same_turn": True},
}


def fresh_doc(endpoint=None, private_hosts=None):
    doc = json.loads(json.dumps(DOC))
    if endpoint is not None:
        doc["models"][0]["endpoint"] = endpoint
    if private_hosts is not None:
        doc["private_hosts"] = private_hosts
    return doc


def case1_apply_choice():
    doc = fresh_doc()
    choice = {"kind": "openai", "endpoint": "https://api.openai.com/v1", "model": "gpt-x", "key_env": ""}
    out = onboard_choice.apply_choice(doc, choice)
    local = out["models"][0]
    remote = out["models"][1]
    ok = (
        local["endpoint"] == "http://127.0.0.1:9000/v1"
        and local["name"] == "m"
        and remote["endpoint"] == "https://api.openai.com/v1"
        and remote["name"] == "gpt-x"
        and remote["key_env"] == "REMOTE_KEY"
    )
    detail = "local endpoint=" + local["endpoint"] + " remote endpoint=" + remote["endpoint"]
    return ok, detail


def case_validate(endpoint, private_hosts, expected):
    doc = fresh_doc(endpoint=endpoint, private_hosts=private_hosts)
    errs = config_rules.validate_models(doc)
    return errs == expected, "validate=" + repr(errs)


def case6_delegate_ceiling(tmp_root):
    home = os.path.join(tmp_root, "home")
    alt = os.path.join(tmp_root, "alt")
    proj = os.path.join(tmp_root, "proj")
    os.makedirs(home)
    os.makedirs(alt)
    os.makedirs(proj)

    models = {
        "schema_version": "1",
        "models": [
            {
                "id": "own",
                "name": "alpha-7b",
                "location": "remote",
                "endpoint": "http://127.0.0.1:1/v1",
                "context_window": 8192,
                "paid": False,
                "trust": "trusted_third_party",
                "key_env": "",
            }
        ],
        "layers": [{"name": "work", "delegable": True}],
        "roles": [{"name": "code", "layer": "work", "model": "own"}],
    }
    wide = json.loads(json.dumps(PREFS))
    wide["ceilings"]["max_output_tokens"] = 100000

    with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
        json.dump(models, f)
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    with open(os.path.join(alt, "models.json"), "w", encoding="utf-8") as f:
        json.dump(models, f)
    with open(os.path.join(alt, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(wide, f)
    with open(os.path.join(proj, "task.md"), "w", encoding="utf-8") as f:
        f.write("NATURE: creation\nWrite print(42).\n")

    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home
    cmd = [
        sys.executable,
        os.path.join(ROOT, "public", "bin", "delegate.py"),
        "--bench",
        "--models", os.path.join(alt, "models.json"),
        "--role", "code",
        "--file", os.path.join(proj, "task.md"),
        "--max-tokens", "5000",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=180, env=env, cwd=proj)
    out = proc.stdout + proc.stderr

    def trunc(s):
        s = s.replace("\n", " | ")
        return s[-300:] if len(s) > 300 else s

    ok = (
        proc.returncode == 2
        and "CEILING: --max-tokens 5000 exceeds max_output_tokens 100" in out
        and "100000" not in out
    )
    detail = "rc=" + str(proc.returncode) + " out=" + trunc(out)
    return ok, detail


def main():
    tmp_root = tempfile.mkdtemp(prefix="c8-", dir="/tmp")
    LAN_HOST = ".".join(["192", "168", "1", "50"])
    results = []
    try:
        results.append(("1 apply_choice keeps a remote endpoint out of local-reader", case1_apply_choice()))
        results.append(("2 validate refuses local+private on https://api.openai.com/v1", case_validate(
            "https://api.openai.com/v1", None,
            [
                "models[0].location local but the endpoint host is not local; add the host to private_hosts to accept it",
                "models[0].trust private but the endpoint host is not local",
            ],
        )))
        results.append(("3 validate accepts local+private on http://127.0.0.1:1234/v1", case_validate(
            "http://127.0.0.1:1234/v1", None, [])))
        results.append(("4 validate accepts local+private on http://foo.localhost:9100/v1", case_validate(
            "http://foo.localhost:9100/v1", None, [])))
        results.append(("5 validate accepts local+private on http://" + LAN_HOST + ":9100/v1 with private_hosts", case_validate(
            "http://" + LAN_HOST + ":9100/v1", [LAN_HOST], [])))
        results.append(("6 delegate ceilings come from FRUGALFLOW_HOME, not from the --models folder", case6_delegate_ceiling(tmp_root)))
    finally:
        shutil.rmtree(tmp_root, ignore_errors=True)

    failed = 0
    for name, (ok, detail) in results:
        if ok:
            print("PASS " + name + " | " + detail)
        else:
            print("FAIL " + name + " | " + detail)
            failed += 1

    total = len(results)
    print("SUMMARY " + str(total - failed) + "/" + str(total))
    sys.exit(1 if failed else 0)


if __name__ == "__main__":
    main()
