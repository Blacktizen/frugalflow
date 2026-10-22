#!/usr/bin/env python3
"""commit_claims.py - lists the hex hashes a markdown text presents as commits."""

import os
import re
import sys
import subprocess

QUALIFIERS = ["gist", "sha256", "sha-256", "fingerprint", "empreinte", "checksum", "digest", "hash"]
WINDOW = 60


def strip_code_blocks(text):
    """Remove lines between pairs of triple-backtick delimiters, inclusive."""
    lines = text.split("\n")
    result = []
    in_block = False
    for line in lines:
        if line.lstrip().startswith("```"):
            in_block = not in_block
            continue
        if not in_block:
            result.append(line)
    return "\n".join(result)


def is_candidate(token):
    """True if token is a 7-40 char lowercase hex string with at least one digit and one letter."""
    if not (7 <= len(token) <= 40):
        return False
    if not re.fullmatch(r"[0-9a-f]+", token):
        return False
    return any(c.isdigit() for c in token) and any(c.isalpha() for c in token)


def claims(text, qualifiers=None, declared=()):
    """Return {'commits': [...], 'excluded': [(token, motive), ...]} from a markdown text."""
    if qualifiers is None:
        qualifiers = QUALIFIERS
    if not isinstance(text, str):
        return {"commits": [], "excluded": []}

    cleaned = strip_code_blocks(text)
    declared_lower = {d.lower() for d in declared}
    commits_set = set()
    excluded_set = set()

    for line in cleaned.split("\n"):
        for m in re.finditer(r"`([^`\n]+)`", line):
            token = m.group(1).strip()
            if not is_candidate(token):
                continue
            if token.lower() in declared_lower:
                excluded_set.add((token, "declared"))
            else:
                before = line[max(0, m.start() - WINDOW):m.start()].lower()
                q = None
                for qual in qualifiers:
                    if re.search(r"(?<![a-z0-9_])" + re.escape(qual) + r"(?![a-z0-9_])", before):
                        q = qual
                        break
                if q is not None and "commit" not in before:
                    excluded_set.add((token, "qualifier " + q))
                else:
                    commits_set.add(token)

    return {"commits": sorted(commits_set), "excluded": sorted(excluded_set)}


# --- Fixtures ---
T1 = "Done in `3fb9ccf` and `f2911be`.\nWord `deadbeef0cafe` too.\n"
T2 = "Karpathy gist, revision `a1b2c3d4e5f6a7b8c9d0` unchanged.\nFile sha256 `0a1b2c3d4e5f6a7b` here.\n"
T3 = "The hash of commit `9f8743b` is kept.\n"
T4 = "Cron id `5e641f9aa` and `ecf74eb`.\n"
T6 = "Built `digest_rules.py` `9f8743b` with hashlib `ecf74eb`.\n"
T5 = "```\nsee `c287246`\n```\nout `319f3ff` and `abcdefa` and `1234567` and `3FB9CCF`.\n"


NOTICE = (
    "NAME      commit_claims.py - lists the hex hashes a markdown text presents as commits, and sets apart, with their motive, those that name something else.\n"
    "READS     nothing: pure module; the caller passes the text, and optionally the qualifier words and the declared non-commit ids.\n"
    "WRITES    nothing: claims() returns {\"commits\": [...], \"excluded\": [(token, motive), ...]}; the caller must announce the excluded count.\n"
    "EXAMPLE   python3 commit_claims.py --notice\n"
    "PITFALLS  2026-09-22 a gist revision cited as proof was checked as a local commit and made the closing check fail.\n"
    "          A hash preceded by a qualifier word (gist, sha256, fingerprint...) is set apart, unless \"commit\" stands next to it;\n"
    "          2026-09-26 \"digest_rules.py\" set a real commit apart: a qualifier counts only as a whole word.\n"
)


def _autotest():
    """Run the five test cases; print one line per test; return exit code."""
    failures = 0

    # Test 1
    expected = {"commits": ["3fb9ccf", "deadbeef0cafe", "f2911be"], "excluded": []}
    got = claims(T1)
    if not isinstance(got, dict):
        got = None
    ok = got == expected
    print(("PASS" if ok else "FAIL") + " Test 1: expected " + repr(expected) + ", got " + repr(got))
    if not ok:
        failures += 1

    # Test 2
    expected = {"commits": [], "excluded": [("0a1b2c3d4e5f6a7b", "qualifier sha256"), ("a1b2c3d4e5f6a7b8c9d0", "qualifier gist")]}
    got = claims(T2)
    if not isinstance(got, dict):
        got = None
    ok = got == expected
    print(("PASS" if ok else "FAIL") + " Test 2: expected " + repr(expected) + ", got " + repr(got))
    if not ok:
        failures += 1

    # Test 3
    exp_a = {"commits": ["9f8743b"], "excluded": []}
    got_a = claims(T3)
    if not isinstance(got_a, dict):
        got_a = None
    exp_b = {"commits": ["ecf74eb"], "excluded": [("5e641f9aa", "declared")]}
    got_b = claims(T4, declared=["5E641F9AA"])
    if not isinstance(got_b, dict):
        got_b = None
    exp_c = {"commits": ["0a1b2c3d4e5f6a7b", "a1b2c3d4e5f6a7b8c9d0"], "excluded": []}
    got_c = claims(T2, qualifiers=[])
    if not isinstance(got_c, dict):
        got_c = None
    ok = (got_a == exp_a) and (got_b == exp_b) and (got_c == exp_c)
    print(("PASS" if ok else "FAIL") + " Test 3: expected " + repr((exp_a, exp_b, exp_c)) + ", got " + repr((got_a, got_b, got_c)))
    if not ok:
        failures += 1

    # Test 4
    exp_a = {"commits": ["319f3ff"], "excluded": []}
    got_a = claims(T5)
    if not isinstance(got_a, dict):
        got_a = None
    exp_b = {"commits": ["9f8743b", "ecf74eb"], "excluded": []}
    got_b = claims(T6)
    if not isinstance(got_b, dict):
        got_b = None
    exp_c = {"commits": [], "excluded": []}
    got_c = claims(None)
    if not isinstance(got_c, dict):
        got_c = None
    got_d = claims("")
    if not isinstance(got_d, dict):
        got_d = None
    ok = (got_a == exp_a) and (got_b == exp_b) and (got_c == exp_c) and (got_d == exp_c)
    print(("PASS" if ok else "FAIL") + " Test 4: expected " + repr((exp_a, exp_b, exp_c, exp_c)) + ", got " + repr((got_a, got_b, got_c, got_d)))
    if not ok:
        failures += 1

    # Test 5
    proc1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    proc2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True
    )
    ok1 = proc1.returncode == 0 and proc1.stdout.startswith("NAME      commit_claims.py")
    ok2 = proc2.returncode == 2 and proc2.stdout == "usage: commit_claims.py --notice | --autotest\n"
    ok = ok1 and ok2
    print(("PASS" if ok else "FAIL") + " Test 5: expected rc=0/notice and rc=2/usage, got rc=" + str(proc1.returncode) + " and rc=" + str(proc2.returncode))
    if not ok:
        failures += 1

    return 1 if failures else 0


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write("usage: commit_claims.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "commit_claims", sys.argv[1:])
