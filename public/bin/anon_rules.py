import sys
import os
import re
import json
import base64
import subprocess
import warnings

# Some Betterleaks patterns trip a Python FutureWarning; it says nothing about a leak.
warnings.filterwarnings("ignore", "Possible nested set", FutureWarning)

GENERIC_ANONYMIZABLE = [
    # the French placeholder domain (exemple.fr...) and the 0123456789 fixture are not personal data; example.org stays caught, our fixtures prove detection with it.
    (r"[A-Za-z0-9._%+-]+@(?!exemple\.(?:fr|com|org|net)(?![A-Za-z0-9.-]))[A-Za-z0-9.-]+\.[A-Za-z]{2,}", "email address", "EMAIL"),
    (r"/[U]sers/[A-Za-z0-9._-]+", "user path", "PATH"),
    (r"/home/[A-Za-z0-9._-]+", "user path", "PATH"),
    (r"C:[\\/]Users[\\/][A-Za-z0-9._-]+", "user path", "PATH"),
    (r"\b(?!127\.0\.0\.1\b)(?!0\.0\.0\.0\b)(?:\d{1,3}\.){3}\d{1,3}\b", "IP address", "IP"),
    (r"\b(?:[0-9A-Fa-f]{2}[:-]){5}[0-9A-Fa-f]{2}\b", "MAC address", "MAC"),
    (r"(?i)\b(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+(?:lan|internal|intra|corp|ts\.net)\b", "internal host name", "HOST"),
    (r"\b(?:DESKTOP|LAPTOP)-[A-Z0-9]{6,}\b", "machine name", "HOST"),
    (r"(?:@author|__author__)[ \t]*[:=]?[ \t]*\W?[A-Z][a-z]+", "author metadata", "AUTHOR"),
    (r"(?<!\d)(?!01[\s.-]?23[\s.-]?45[\s.-]?67[\s.-]?89(?!\d))(?:\+33\s?|0033\s?|0)[1-9](?:[\s.-]?\d{2}){4}(?!\d)", "phone number", "PHONE"),
]

GENERIC_IRREDUCIBLE = [
    (r"(?im)\b(?:password|passwd|secret|api[_-]?key)\b\s*[:=]\s*(?:\"[^\"]{4,}\"|'[^']{4,}'|[A-Za-z0-9_/+-]{8,}\s*$)", "credential in clear"),
    (r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}", "JWT"),
    (r"(?i)\b(?:sk|pk)-(?:[A-Za-z0-9]{1,12}-){0,3}[A-Za-z0-9]{16,}", "API key"),
    (r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----", "private key block"),
    (r"(?i)\b(?:AWS_SECRET_ACCESS_KEY|DATABASE_URL|REDIS_URL|MONGO_URL|VAULT_TOKEN)\s*[=:]\s*\S{8,}", "connection string with its value"),
]


def load(doc):
    if not isinstance(doc, dict):
        return ([], [], ["rules file must be an object"])

    errors = []

    for k in sorted(doc):
        if k not in ("anonymizable", "irreducible"):
            errors.append("unknown key " + k)

    anonymizable = []
    irreducible = []

    for key in ("anonymizable", "irreducible"):
        value = doc.get(key, [])
        if not isinstance(value, list):
            errors.append(key + " must be a list")
            continue
        for i, entry in enumerate(value):
            P = key + "[" + str(i) + "]"
            if not isinstance(entry, dict):
                errors.append(P + " must be an object")
                continue
            entry_errors = []
            pattern = entry.get("pattern")
            if not isinstance(pattern, str) or not pattern:
                entry_errors.append(P + ".pattern must be a non-empty string")
            else:
                try:
                    re.compile(pattern)
                except re.error:
                    entry_errors.append(P + ".pattern is not a valid regular expression")
                else:
                    if re.search(pattern, "") is not None:
                        entry_errors.append(P + ".pattern matches the empty string")
            label = entry.get("label")
            if not isinstance(label, str) or not label:
                entry_errors.append(P + ".label must be a non-empty string")
            if key == "anonymizable":
                tag = entry.get("tag")
                if not isinstance(tag, str) or re.fullmatch(r"[A-Z]{2,12}", tag) is None:
                    entry_errors.append(P + ".tag must be 2 to 12 capital letters")
            errors.extend(entry_errors)
            if not entry_errors:
                if key == "anonymizable":
                    anonymizable.append((pattern, label, tag))
                else:
                    irreducible.append((pattern, label))

    if errors:
        return ([], [], errors)
    return (GENERIC_ANONYMIZABLE + anonymizable, GENERIC_IRREDUCIBLE + BETTERLEAKS + irreducible, [])


def go_to_py(pattern):
    # Go/RE2 writes end-of-text as \z; Python 3.11 and 3.12 refuse it and spell it \Z.
    # An escaped backslash followed by z (two backslashes then z) is a literal \z and stays as is.
    out = []
    i = 0
    n = len(pattern)
    while i < n:
        c = pattern[i]
        if c == "\\":
            nxt = pattern[i + 1] if i + 1 < n else ""
            if nxt == "z":
                out.append("\\Z")
                i += 2
            elif nxt:
                out.append(c)
                out.append(nxt)
                i += 2
            else:
                out.append(c)
                i += 1
        else:
            out.append(c)
            i += 1
    return "".join(out)


# Secret rules by Zachary Rice, Betterleaks (MIT), refreshed with import_betterleaks.py.
# A missing file raises at import: the commit gate stops instead of passing secrets.
_BL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "betterleaks_rules.json")
with open(_BL, encoding="utf-8") as _f:
    BETTERLEAKS = [(go_to_py(r["regex"]), "secret (Betterleaks " + r["id"] + ")")
                   for r in json.loads(base64.b64decode(json.load(_f)["rules_b64"]))]


GOOD = {"anonymizable": [{"pattern": "\\bPlimsoq\\b", "label": "person", "tag": "PERSON"}],
        "irreducible": [{"pattern": "(?i)\\bvendrak\\b", "label": "third-party file"}]}

BAD = {"anonymisable": [],
       "anonymizable": [{"pattern": "", "label": "x", "tag": "AB"},
                        {"pattern": "(", "label": "x", "tag": "AB"},
                        {"pattern": "a*", "label": "x", "tag": "AB"},
                        {"pattern": "ok", "label": "", "tag": "ab"},
                        "text"],
       "irreducible": {"pattern": "x"}}

PROBES = [("ann" + "@example.org", 0), ("/Us" + "ers/alice", 1), ("10.20" + ".30.40", 4), ("00:1B:44" + ":11:3A:B7", 5), ("box.tail1234.ts" + ".net", 6), ("DESKTOP" + "-A1B2C3", 7)]

NEGATIVES = ["127.0.0.1", "Path.home()", "threading.local()", "version 3.11.2", "def reset_password(user):"]


def _autotest():
    all_pass = True

    # Test 1
    got = load({})
    exp = (GENERIC_ANONYMIZABLE, GENERIC_IRREDUCIBLE + BETTERLEAKS, [])
    ok = got == exp and len(got[0]) == 10 and len(got[1]) == 5 + 439
    if ok:
        print("PASS 1: expected (10 anonymizable, 5 + 439 irreducible, 0 errors) got (10, 444, 0)")
    else:
        print("FAIL 1: expected (10, 444, 0) got " + str((len(got[0]), len(got[1]), len(got[2]))))
    all_pass = all_pass and ok

    # Test 2
    got = load(GOOD)
    exp_last_anon = ("\\bPlimsoq\\b", "person", "PERSON")
    exp_last_irr = ("(?i)\\bvendrak\\b", "third-party file")
    ok = (len(got[0]) == 11 and len(got[1]) == 6 + 439 and got[2] == []
          and got[0][-1] == exp_last_anon and got[1][-1] == exp_last_irr)
    if ok:
        print("PASS 2: expected (11, 445, 0) got (11, 445, 0)")
    else:
        print("FAIL 2: expected (11, 445, 0) got " + str((len(got[0]), len(got[1]), len(got[2]))))
    all_pass = all_pass and ok

    # Test 3
    got = load(BAD)
    exp = ([], [], [
        "unknown key anonymisable",
        "anonymizable[0].pattern must be a non-empty string",
        "anonymizable[1].pattern is not a valid regular expression",
        "anonymizable[2].pattern matches the empty string",
        "anonymizable[3].label must be a non-empty string",
        "anonymizable[3].tag must be 2 to 12 capital letters",
        "anonymizable[4] must be an object",
        "irreducible must be a list",
    ])
    ok = got == exp
    if ok:
        print("PASS 3: expected 8 errors got 8")
    else:
        print("FAIL 3: expected " + str(exp[2]) + " got " + str(got[2]))
    all_pass = all_pass and ok

    # Test 4
    ok = True
    fail_detail = ""
    for value, index in PROBES:
        if re.search(GENERIC_ANONYMIZABLE[index][0], value) is None:
            ok = False
            fail_detail = "PROBE " + value + " not matched by index " + str(index)
            break
    if ok:
        for neg in NEGATIVES:
            all_pats = [p[0] for p in GENERIC_ANONYMIZABLE] + [p[0] for p in GENERIC_IRREDUCIBLE]
            for pat in all_pats:
                if re.search(pat, neg, re.M) is not None:
                    ok = False
                    fail_detail = "NEGATIVE " + neg + " matched by " + pat
                    break
            if not ok:
                break
    if ok:
        print("PASS 4: expected all PROBES matched and no NEGATIVES matched, got 6/6 PROBES, 0/5 NEGATIVES")
    else:
        print("FAIL 4: " + fail_detail)
    all_pass = all_pass and ok

    # Test 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    ok = proc.returncode == 0 and proc.stdout.startswith("NAME      anon_rules.py")
    if ok:
        print("PASS 5: expected rc=0 and stdout startswith 'NAME      anon_rules.py' got rc=0, ok")
    else:
        print("FAIL 5: expected rc=0 got rc=" + str(proc.returncode))
    all_pass = all_pass and ok

    # Test 6
    got6a = go_to_py("a\\z")
    got6b = go_to_py("a\\\\z")
    bad6 = []
    for pat, _label in BETTERLEAKS:
        try:
            re.compile(pat)
        except re.error:
            bad6.append(pat)
    ok = got6a == "a\\Z" and got6b == "a\\\\z" and not bad6
    if ok:
        print("PASS 6: expected go_to_py('a\\z')=='a\\Z', 'a\\\\z' unchanged, 0 BETTERLEAKS compile errors; got " + repr(got6a) + ", " + repr(got6b) + ", 0")
    else:
        print("FAIL 6: expected go_to_py('a\\z')=='a\\Z', 'a\\\\z' unchanged, 0 BETTERLEAKS compile errors; got " + repr(got6a) + ", " + repr(got6b) + ", " + str(len(bad6)))
    all_pass = all_pass and ok

    sys.exit(0 if all_pass else 1)


def _main():
    if len(sys.argv) == 1:
        print("usage: anon_rules.py --notice | --autotest")
        sys.exit(2)
    if sys.argv[1] == "--notice":
        sys.stdout.write(
            "NAME      anon_rules.py - holds the generic leak patterns and validates the operator's own pattern file.\n"
            "READS     nothing: pure module; load() reads the decoded anonymization.json it is given.\n"
            "WRITES    nothing: load() returns the pattern lists and the error lines.\n"
            "EXAMPLE   python3 anon_rules.py --notice\n"
            "PITFALLS  2026-08-27 the old anonymiser carried private names in its own code: a leak dressed as protection.\n"
            "          2026-09-23 a misspelt key would have disarmed a rule silently; an unknown key is now an error.\n"
        )
        sys.exit(0)
    if sys.argv[1] == "--autotest":
        _autotest()
    else:
        print("usage: anon_rules.py --notice | --autotest")
        sys.exit(2)


def _cli():
    _main()


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "anon_rules", sys.argv[1:])
