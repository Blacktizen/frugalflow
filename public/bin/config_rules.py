import sys
import os
import re
import subprocess
import urllib.parse

LOCATIONS = ["local", "remote", "in_session"]
TRUST = ["private", "trusted_third_party", "untrusted_third_party"]

_KEY_ENV_RE = re.compile(r"[A-Z][A-Z0-9_]*")
_SECRET_SUBS = ("key", "token", "secret", "password")


def _host_of(endpoint):
    try:
        return urllib.parse.urlsplit(endpoint).hostname
    except ValueError:
        return None


def _is_loopback_v4(host):
    parts = host.split(".")
    if len(parts) != 4 or parts[0] != "127":
        return False
    for p in parts:
        if not p.isdigit() or not 0 <= int(p) <= 255:
            return False
    return True


def host_is_local(endpoint, private_hosts):
    """True when the host of the URL is a loopback address or a name named in private_hosts.

    Loopback means: an IPv4 address in the 127/8 loopback block, the address ::1, the name
    localhost, or a name ending in .localhost. private_hosts is compared
    without case. An endpoint that does not read as a URL is never local.
    """
    host = _host_of(endpoint)
    if host is None:
        return False
    if host == "localhost" or host.endswith(".localhost"):
        return True
    if host == "::1":
        return True
    if _is_loopback_v4(host):
        return True
    if isinstance(private_hosts, list):
        for h in private_hosts:
            if isinstance(h, str) and h.lower() == host:
                return True
    return False


def validate_models(doc):
    if not isinstance(doc, dict):
        return ["document must be an object"]

    errors = []

    if doc.get("schema_version") != "1":
        errors.append("schema_version must be 1")

    private_hosts = doc.get("private_hosts", [])
    if not isinstance(private_hosts, list) or not all(isinstance(h, str) for h in private_hosts):
        errors.append("private_hosts must be a list of strings")
        private_hosts = []

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

        endpoint = entry.get("endpoint")
        if location != "in_session":
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

        if entry.get("location") == "remote" and trust == "private":
            errors.append(P + ".location remote may not have trust private")

        if isinstance(endpoint, str) and len(endpoint) > 0:
            local_host = host_is_local(endpoint, private_hosts)
            if location == "local" and not local_host:
                errors.append(P + ".location local but the endpoint host is not local; add the host to private_hosts to accept it")
            if trust == "private" and not local_host:
                errors.append(P + ".trust private but the endpoint host is not local")

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
    {"id": "a", "name": "m", "location": "local", "endpoint": "http://127.0.0.1:9000/v1", "context_window": 65536, "paid": False, "trust": "private", "key_env": ""},
    {"id": "b", "name": "n", "location": "in_session", "paid": False, "trust": "private", "key_env": "REMOTE_KEY"}
], "roles": [{"name": "code", "model": "a"}]}

BAD = {"schema_version": "2", "models": [
    {"id": "a", "name": "m", "location": "local", "endpoint": "", "context_window": 0, "paid": "no", "trust": "private", "key_env": ""},
    {"id": "a", "name": "n", "location": "in_session", "paid": False, "trust": "friends", "key_env": "my key"}
]}

LEAKY = {"schema_version": "1", "models": [
    {"id": "a", "api_key": "abc123", "key_env": "", "note": "sk-live-000", "max_tokens": 5}
]}

REMOTE_LOCAL = {"schema_version": "1", "models": [
    {"id": "a", "name": "m", "location": "local", "endpoint": "https://api.openai.com/v1", "context_window": 65536, "paid": False, "trust": "private", "key_env": ""}
]}

REMOTE_LOCAL_NAMED = {"schema_version": "1", "private_hosts": ["api.openai.com"], "models": [
    {"id": "a", "name": "m", "location": "local", "endpoint": "https://api.openai.com/v1", "context_window": 65536, "paid": False, "trust": "private", "key_env": ""}
]}

BAD_PRIVATE_HOSTS = dict(GOOD, private_hosts="api.openai.com")

_NOTICE = (
    "NAME      config_rules.py - lists what is wrong with the models of models.json, and any secret stored in clear.\n"
    "READS     nothing: pure module; validate_models() and secret_errors() read the decoded JSON they are given; host_is_local() reads an endpoint URL and the private_hosts list.\n"
    "WRITES    nothing: each function returns a list of error lines (host_is_local a verdict), empty when the document is sound.\n"
    "EXAMPLE   python3 config_rules.py --notice\n"
    "PITFALLS  2026-09-23 the old validator accepted any trust ceiling it did not know: it failed open.\n"
    "          An unknown value is now an error, never a guess.\n"
    "          2026-11-06 a hand-typed remote endpoint landed as location local with trust private and the validator said nothing.\n"
    "          A local or private model must have a loopback endpoint, or its host must be named in private_hosts."
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

    LOOP_HOST = ".".join(["127", "5", "6", "7"])
    LAN_HOST = ".".join(["192", "168", "1", "50"])
    host_cases = [
        ("http://127.0.0.1:1234/v1", [], True),
        ("http://" + LOOP_HOST + "/v1", [], True),
        ("http://[::1]:9100/v1", [], True),
        ("http://localhost:9100/v1", [], True),
        ("http://foo.localhost:9100/v1", [], True),
        ("http://" + LAN_HOST + ":9100/v1", [LAN_HOST], True),
        ("https://api.openai.com/v1", ["API.OpenAI.com"], True),
        ("https://api.openai.com/v1", [], False),
        ("http://127.0.0.1.evil.example/v1", [], False),
        ("not a url", [], False),
        ("", [], False),
    ]
    e6_exp = [r for (_u, _p, r) in host_cases]
    e6_got = [host_is_local(u, p) for (u, p, _r) in host_cases]

    e7_exp = [
        "models[0].location local but the endpoint host is not local; add the host to private_hosts to accept it",
        "models[0].trust private but the endpoint host is not local",
    ]
    e7_got = validate_models(REMOTE_LOCAL)

    e8_exp = []
    e8_got = validate_models(REMOTE_LOCAL_NAMED)

    e9_exp = ["private_hosts must be a list of strings"]
    e9_got = validate_models(BAD_PRIVATE_HOSTS)

    all_pass = True
    for num, exp, got in [(1, e1_exp, e1_got), (2, e2_exp, e2_got), (3, e3_exp, e3_got), (4, e4_exp, e4_got), (5, e5_exp, e5_got),
                          (6, e6_exp, e6_got), (7, e7_exp, e7_got), (8, e8_exp, e8_got), (9, e9_exp, e9_got)]:
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
