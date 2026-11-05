import os
import sys

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
sys.path.insert(0, BIN)

import config_rules  # noqa: E402
import layers  # noqa: E402


def doc_with(remote_trust):
    return {
        "schema_version": "1",
        "models": [
            {"id": "local", "name": "m", "location": "local", "endpoint": "http://127.0.0.1:9000/v1",
             "context_window": 65536, "paid": False, "trust": "private", "key_env": ""},
            {"id": "far", "name": "n", "location": "remote", "endpoint": "https://api.example.com/v1",
             "context_window": 131072, "paid": True, "trust": remote_trust, "key_env": "REMOTE_KEY"},
        ],
        "layers": [{"name": "reading", "delegable": True}, {"name": "kept", "delegable": False}],
        "roles": [
            {"name": "code", "layer": "reading", "model": "local"},
            {"name": "remote", "layer": "reading", "model": "far"},
            {"name": "judgment", "layer": "kept", "model": ""},
        ],
    }


def main():
    failures = 0

    bad = doc_with("private")
    errs = config_rules.validate_models(bad)
    ok1 = any(e.startswith("models[1].location remote") and "private" in e for e in errs)
    print(("PASS" if ok1 else "FAIL") + " 1 validate_models refuses remote+private: got " + repr(errs))
    failures += 0 if ok1 else 1

    got = layers.route(bad, "remote", "private")
    ok2 = got[0] is None and "remote" in got[1]
    print(("PASS" if ok2 else "FAIL") + " 2 route(remote+private, ceiling private) refused: got " + repr(got))
    failures += 0 if ok2 else 1

    got = layers.route(bad, "remote", "untrusted_third_party")
    ok3 = got[0] is None and "remote" in got[1]
    print(("PASS" if ok3 else "FAIL") + " 3 route(remote+private, ceiling untrusted) refused: got " + repr(got))
    failures += 0 if ok3 else 1

    good = doc_with("untrusted_third_party")
    got = layers.route(good, "remote", "untrusted_third_party")
    ok4 = got[0] is not None and got[0].get("id") == "far" and got[1] == ""
    print(("PASS" if ok4 else "FAIL") + " 4 route(remote untrusted, ceiling untrusted) still routed: got " + repr(got[1]))
    failures += 0 if ok4 else 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())