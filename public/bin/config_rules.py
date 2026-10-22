import sys
import os
import re
import subprocess

LOCATIONS = ["local", "remote", "in_session"]
TRUST = ["private", "trusted_third_party", "untrusted_third_party"]

_KEY_ENV_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_SECRET_SUBS = ("key", "token", "secret", "password")


def validate_models(doc):
    if not isinstance(doc, dict):
        return ["document must be an object"]

    errors = []

    if doc.get("schema_version") != "1":
        errors.append("schema_version must be 1")

    models = doc.get("models")
    if not isinstance(models, list) or len(models) == 0:
        errors.append("models must be a non-empty list")
        return errors

    seen_ids = set()
    for i, entry in enumerate(models):
        P = "models[" + str(i) + "]"

        if not isinstance(entry, dict):
            errors.append(P + " must be an object")
            continue

        mid = entry.get("id")
        if not isinstance(mid, str) or len(mid) == 0:
            errors.append(P + ".id must be a non-empty string")
        elif mid in seen_ids:
            errors.append(P + ".id duplicates " + mid)
        else:
            seen_ids.add(mid)

        name = entry.get("name")
        if not isinstance(name, str) or len(name) == 0:
            errors.append(P + ".name must be a non-empty string")

        location = entry.get("location")
        if location not in LOCATIONS:
            errors.append(P + ".location must be one of local, remote, in_session")

        if location != "in_session":
            endpoint = entry.get("endpoint")
            if not isinstance(endpoint, str) or len(endpoint) == 0:
                errors.append(P + ".endpoint must be a non-empty string")
            cw = entry.get("context_window")
            if not isinstance(cw, int) or isinstance(cw, bool) or cw <= 0:
                errors.append(P + ".context_window must be an integer above 0")

        paid = entry.get("paid")
        if not isinstance(paid, bool):
            errors.append(P + ".paid must be true or false")

        trust = entry.get("trust")
        if trust not in TRUST:
            errors.append(P + ".trust must be one of private, trusted_third_party, untrusted_third_party")

        key_env = entry.get("key_env")
        if not isinstance(key_env, str):
            errors.append(P + ".key_env must name an environment variable or be empty")
        elif len(key_env) > 0 and not _KEY_ENV_RE.fullmatch(key_env):
            errors.append(P + ".key_env must name an environment variable or be empty")

    return errors


def secret_errors(doc):
    results = []
    _walk_secret(doc, "", results)
    return results


def _walk_secret(obj, path, results):
    if isinstance(obj, dict):
        for k, v in obj.items():
            cp = path + "." + k if path else k
            if isinstance(v, str) and len(v) > 0:
                _check_secret(k, v, cp, results)
            elif isinstance(v, (dict, list)):
                _walk_secret(v, cp, results)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            cp = path + "[" + str(i) + "]"
            if isinstance(v, str) and len(v) > 0:
                if v.startswith("sk-"):
                    results.append("secret value at " + cp + ": name an environment variable in key_env instead")
            elif isinstance(v, (dict, list)):
                _walk_secret(v, cp, results)


def _check_secret(key, value, path, results):
    flagged = False
    lk = key.lower()
    if any(s in lk for s in _SECRET_SUBS) and key != "key_env":
        flagged = True
    if value.startswith("sk-"):
        flagged = True
    if flagged:
        results.append("secret value at " + path + ": name an environment variable in key_env instead")


GOOD = {"schema_version": "1", "models": [
    {"id": "a", "name": "m", "location": "local", "endpoint": "http://127.0.0.1:8000/v1", "context_window": 65536, "paid": False, "trust": "private", "key_env": ""},
    {"id": "b", "name": "n", "location": "in_session", "paid": False, "trust": "private", "key_env": "REMOTE_KEY"}
], "roles": [{"name": "code", "model": "a"}]}

BAD = {"schema_version": "2", "models": [
    {"id": "a", "name": "m", "location": "local", "endpoint": "", "context_window": 0, "paid": "no", "trust": "private", "key_env": ""},
    {"id": "a", "name": "n", "location": "in_session", "paid": False, "trust": "friends", "key_env": "my key"}
]}

LEAKY = {"schema_version": "1", "models": [
    {"id": "a", "api_key": "abc123", "key_env": "", "note": "sk-live-000", "max_tokens": 5}
]}

_NOTICE = (
    "NAME      config_rules.py - lists what is wrong with the models of models.json, and any secret stored in clear.\n"
    "READS     nothing: pure module; validate_models() and secret_errors() read the decoded JSON they are given.\n"
    "WRITES    nothing: each function returns a list of error lines, empty when the document is sound.\n"
    "EXAMPLE   python3 config_rules.py --notice\n"
    "PITFALLS  2026-09-23 the old validator accepted any trust ceiling it did not know: it failed open.\n"
    "          An unknown value is now an error, never a guess."
)


def _autotest():
    e1_exp = []
    e1_got = validate_models(GOOD)

    e2_exp = [
        "schema_version must be 1",
        "models[0].endpoint must be a non-empty string",
        "models[0].context_window must be an integer above 0",
        "models[0].paid must be true or false",
        "models[1].id duplicates a",
        "models[1].trust must be one of private, trusted_third_party, untrusted_third_party",
        "models[1].key_env must name an environment variable or be empty",
    ]
    e2_got = validate_models(BAD)

    e3_exp = []
    e3_got = secret_errors(GOOD)

    e4_exp = [
        "secret value at models[0].api_key: name an environment variable in key_env instead",
        "secret value at models[0].note: name an environment variable in key_env instead",
    ]
    e4_got = secret_errors(LEAKY)

    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    e5_exp = (0, True)
    e5_got = (proc.returncode, proc.stdout.startswith("NAME      config_rules.py"))

    all_pass = True
    for num, exp, got in [(1, e1_exp, e1_got), (2, e2_exp, e2_got), (3, e3_exp, e3_got), (4, e4_exp, e4_got), (5, e5_exp, e5_got)]:
        if exp == got:
            print("PASS test " + str(num) + " expected=" + repr(exp) + " got=" + repr(got))
        else:
            print("FAIL test " + str(num) + " expected=" + repr(exp) + " got=" + repr(got))
            all_pass = False
    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(_NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: config_rules.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "config_rules", sys.argv[1:])
