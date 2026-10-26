#!/usr/bin/env python3
"""Computes the effective limits of one delegation (tries, output tokens, trust)
from preferences.json, .frugalflow.json and the command line.
An option may only tighten a ceiling, never widen it."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ceilings
import example_defaults


def resolve(prefs, project, cli):
    """Resolve effective limits from decoded documents and CLI options.

    Returns a (limits, error) tuple. limits is a dict with keys
    "tries", "max_tokens", "trust" or None on error.
    error is None or a string starting with "CEILING: ".
    """
    # Step 1: validate CLI trust level
    if cli["trust"] is not None and cli["trust"] not in ceilings.TRUST:
        return (None, "CEILING: unknown trust level " + cli["trust"])

    # Step 2: validate CLI numeric bounds
    if cli["tries"] is not None and cli["tries"] < 1:
        return (None, "CEILING: --tries must be at least 1")
    if cli["max_tokens"] is not None and cli["max_tokens"] < 1:
        return (None, "CEILING: --max-tokens must be at least 1")

    # Step 3: no preferences file
    if prefs is None:
        if project is not None:
            return (None, "CEILING: .frugalflow.json found but no preferences.json to tighten")
        return (
            {
                "tries": cli["tries"] if cli["tries"] is not None else example_defaults.get("preferences", "ceilings.max_tries"),
                "max_tokens": cli["max_tokens"],
                "trust": cli["trust"] if cli["trust"] is not None else "private",
            },
            None,
        )

    # Step 4: validate preferences document
    errs = ceilings.validate_preferences(prefs)
    if errs:
        return (None, "CEILING: preferences.json invalid: " + errs[0])

    # Step 5: validate project document
    if project is not None:
        errs = ceilings.validate_project(project)
        if errs:
            return (None, "CEILING: .frugalflow.json invalid: " + errs[0])

    # Step 6: tighten
    effective, violations = ceilings.tighten(prefs, project)
    if violations:
        return (None, "CEILING: " + violations[0])

    # Step 7: extract top ceilings
    eff = {path: value for path, value, source in effective}
    top_tries = eff["ceilings.max_tries"]
    top_tokens = eff["ceilings.max_output_tokens"]
    top_trust = eff["ceilings.max_trust"]

    # Step 8: resolve tries
    if cli["tries"] is None:
        tries = top_tries
    elif cli["tries"] > top_tries:
        return (None, "CEILING: --tries " + str(cli["tries"]) + " exceeds max_tries " + str(top_tries))
    else:
        tries = cli["tries"]

    # Step 9: resolve max_tokens
    if cli["max_tokens"] is None:
        max_tokens = top_tokens
    elif cli["max_tokens"] > top_tokens:
        return (None, "CEILING: --max-tokens " + str(cli["max_tokens"]) + " exceeds max_output_tokens " + str(top_tokens))
    else:
        max_tokens = cli["max_tokens"]

    # Step 10: resolve trust
    if cli["trust"] is None:
        trust = "private"
    elif ceilings.TRUST.index(cli["trust"]) > ceilings.TRUST.index(top_trust):
        return (None, "CEILING: --trust " + cli["trust"] + " exceeds max_trust " + top_trust)
    else:
        trust = cli["trust"]

    # Step 11: return
    return ({"tries": tries, "max_tokens": max_tokens, "trust": trust}, None)


NOTICE = (
    "NAME      run_limits.py - computes the effective limits of one delegation "
    "(tries, output tokens, trust) from preferences.json, .frugalflow.json "
    "and the command line; an option may only tighten.\n"
    "READS     nothing: pure module; it works on the decoded documents and the "
    "options it is given, with ceilings.py beside it.\n"
    "WRITES    nothing: resolve() returns the limits, or an error starting "
    "with CEILING.\n"
    "EXAMPLE   python3 run_limits.py --autotest\n"
    "PITFALLS  2026-10-02 the preferences existed and were validated, but no "
    "delegation read them: --tries 5 ran 5 attempts under a ceiling of 2.\n"
)

USAGE = "usage: run_limits.py --notice | --autotest"


def _autotest():
    """Run the five built-in test cases. Returns 0 on success, 1 on failure."""
    PREFS = {
        "schema_version": "1",
        "verbosity": {"final_answer_words": 120, "step_message_words": 30},
        "ceilings": {"max_trust": "trusted_third_party", "max_tries": 2, "max_output_tokens": 100},
        "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
        "grouping": {"independent_calls_same_turn": True},
    }
    NONE = {"tries": None, "max_tokens": None, "trust": None}

    tests = [
        (PREFS, None, NONE,
         ({"tries": 2, "max_tokens": 100, "trust": "private"}, None)),
        (PREFS, None, {"tries": 5, "max_tokens": None, "trust": None},
         (None, "CEILING: --tries 5 exceeds max_tries 2")),
        (PREFS, {"schema_version": "1", "ceilings": {"max_tries": 1}},
         {"tries": None, "max_tokens": 50, "trust": "trusted_third_party"},
         ({"tries": 1, "max_tokens": 50, "trust": "trusted_third_party"}, None)),
        (PREFS, None, {"tries": None, "max_tokens": None, "trust": "untrusted_third_party"},
         (None, "CEILING: --trust untrusted_third_party exceeds max_trust trusted_third_party")),
        (None, None, NONE,
         ({"tries": 3, "max_tokens": None, "trust": "private"}, None)),
    ]

    all_passed = True
    for i, (p, proj, c, expected) in enumerate(tests, 1):
        got = resolve(p, proj, c)
        ok = isinstance(got, tuple) and len(got) == 2 and got == expected
        status = "PASS" if ok else "FAIL"
        print("{} test {} expected={} got={}".format(status, i, expected, got))
        if not ok:
            all_passed = False

    proc = subprocess.run(
        [sys.executable, __file__, "--notice"],
        capture_output=True,
        text=True,
    )
    ok = proc.returncode == 0 and proc.stdout.startswith("NAME      run_limits.py")
    status = "PASS" if ok else "FAIL"
    print("{} test 5 subprocess --notice rc={} startswith_ok={}".format(status, proc.returncode, proc.stdout.startswith("NAME      run_limits.py")))
    if not ok:
        all_passed = False

    return 0 if all_passed else 1


def main():
    """Entry point: dispatch on command-line arguments."""
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    sys.stdout.write(USAGE + "\n")
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "run_limits", sys.argv[1:])
