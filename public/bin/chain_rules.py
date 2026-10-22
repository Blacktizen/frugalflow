#!/usr/bin/env python3
"""Pure module: seals and verifies an append-only vault log chain."""

import hashlib
import os
import re
import subprocess
import sys

GENESIS = "0" * 64
SEAL = re.compile(r"^<!-- chain prev=([0-9a-f]{64}) hash=([0-9a-f]{64}) -->$")


def entry_hash(prev, body):
    """Return the sha256 hex digest of prev + newline + body."""
    return hashlib.sha256((prev + "\n" + body).encode("utf-8")).hexdigest()


def render(prev, when, title, fields):
    """Build a sealed markdown entry and return it as a string."""
    body = "## [" + when + "] " + title + "\n"
    for key, value in fields:
        body += key + ": " + value + "\n"
    return body + "<!-- chain prev=" + prev + " hash=" + entry_hash(prev, body) + " -->\n"


def entries(text):
    """Parse sealed entries from a journal text; return a list of dicts."""
    lines = text.split("\n")
    result = []
    current_lines = None

    for line in lines:
        if line.startswith("## ["):
            if current_lines is not None:
                body = "".join(l + "\n" for l in current_lines)
                result.append({"body": body, "prev": None, "hash": None})
            current_lines = [line]
        elif current_lines is not None:
            m = SEAL.fullmatch(line)
            if m:
                body = "".join(l + "\n" for l in current_lines)
                result.append({"body": body, "prev": m.group(1), "hash": m.group(2)})
                current_lines = None
            else:
                current_lines.append(line)

    if current_lines is not None:
        body = "".join(l + "\n" for l in current_lines)
        result.append({"body": body, "prev": None, "hash": None})

    return result


def verify(text):
    """Verify the seal chain; return (ok, n, bad, reason)."""
    ents = entries(text)
    n = len(ents)
    expected = GENESIS
    for i, e in enumerate(ents):
        if e["hash"] is None:
            return (False, n, i, "entry " + str(i) + " has no seal")
        if e["prev"] != expected:
            return (False, n, i, "entry " + str(i) + " does not follow the previous one")
        if e["hash"] != entry_hash(e["prev"], e["body"]):
            return (False, n, i, "entry " + str(i) + " was rewritten")
        expected = e["hash"]
    return (True, n, None, "")


def last_hash(text):
    """Return the hash of the last entry, GENESIS if none, None if unsealed."""
    ents = entries(text)
    if not ents:
        return GENESIS
    return ents[-1]["hash"]


NOTICE = (
    "NAME      chain_rules.py - seals each entry of a vault's append-only log with the sha256 of the previous one, and verifies the chain.\n"
    "READS     nothing: pure module; the caller passes the log text.\n"
    "WRITES    nothing: render() returns the sealed entry to append; verify() returns (ok, entries, first bad index, reason).\n"
    "EXAMPLE   python3 chain_rules.py --notice\n"
    "PITFALLS  2026-09-06 a log that nothing checked was rewritten in bulk at the end of a session.\n"
    "          A rewritten, removed or inserted entry now breaks the chain, and the closing check says which one.\n"
)

USAGE = "usage: chain_rules.py --notice | --autotest\n"


def _autotest():
    """Run the five proofs; print one PASS/FAIL line per proof; return True if all pass."""
    PRE = "---\ntitle: Log\n---\n# Log\n\n"
    E1 = render(GENESIS, "2026-09-26 10:00", "setup", [("Decision", "vault created")])
    E2 = render(entry_hash(GENESIS, E1.split("<!--")[0]), "2026-09-26 11:00", "second", [("Decision", "b")])
    LOG = PRE + E1 + "\n" + E2
    H2 = entries(LOG)[1]["hash"] if len(entries(LOG)) == 2 else ""
    E3 = render(H2, "2026-09-26 12:00", "third", [("Why", "c")])

    all_pass = True

    # Proof 1
    r1 = (
        E1.startswith("## [2026-09-26 10:00] setup\nDecision: vault created\n<!-- chain prev=" + GENESIS + " hash=")
        and E1.endswith(" -->\n")
        and verify(LOG) == (True, 2, None, "")
        and verify(PRE) == (True, 0, None, "")
        and last_hash(PRE) == GENESIS
    )
    a1 = (
        E1.startswith("## [2026-09-26 10:00] setup\nDecision: vault created\n<!-- chain prev=" + GENESIS + " hash="),
        E1.endswith(" -->\n"),
        verify(LOG),
        verify(PRE),
        last_hash(PRE),
    )
    if r1:
        print("PASS 1 expected=True actual=True")
    else:
        all_pass = False
        print("FAIL 1 expected=True actual=" + repr(a1))

    # Proof 2
    r2 = (
        verify(LOG + "\n" + E3) == (True, 3, None, "")
        and last_hash(LOG + "\n" + E3) == entries(LOG + "\n" + E3)[2]["hash"]
    )
    a2 = (verify(LOG + "\n" + E3), last_hash(LOG + "\n" + E3), entries(LOG + "\n" + E3)[2]["hash"])
    if r2:
        print("PASS 2 expected=True actual=True")
    else:
        all_pass = False
        print("FAIL 2 expected=True actual=" + repr(a2))

    # Proof 3
    r3 = (
        verify(LOG.replace("Decision: b", "Decision: B")) == (False, 2, 1, "entry 1 was rewritten")
        and verify(PRE + E2) == (False, 1, 0, "entry 0 does not follow the previous one")
    )
    a3 = (verify(LOG.replace("Decision: b", "Decision: B")), verify(PRE + E2))
    if r3:
        print("PASS 3 expected=True actual=True")
    else:
        all_pass = False
        print("FAIL 3 expected=True actual=" + repr(a3))

    # Proof 4
    r4 = (
        verify(LOG + "\n## [2026-09-26 13:00] unsealed\nDecision: x\n") == (False, 3, 2, "entry 2 has no seal")
        and last_hash(LOG + "\n## [2026-09-26 13:00] unsealed\n") is None
        and verify(PRE + E1 + "\n" + E3) == (False, 2, 1, "entry 1 does not follow the previous one")
    )
    a4 = (
        verify(LOG + "\n## [2026-09-26 13:00] unsealed\nDecision: x\n"),
        last_hash(LOG + "\n## [2026-09-26 13:00] unsealed\n"),
        verify(PRE + E1 + "\n" + E3),
    )
    if r4:
        print("PASS 4 expected=True actual=True")
    else:
        all_pass = False
        print("FAIL 4 expected=True actual=" + repr(a4))

    # Proof 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True,
    )
    proc2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True,
        text=True,
    )
    r5 = (
        proc.returncode == 0
        and proc.stdout.startswith("NAME      chain_rules.py")
        and proc2.returncode == 2
        and proc2.stdout == USAGE
    )
    a5 = (proc.returncode, proc.stdout[:40], proc2.returncode, proc2.stdout)
    if r5:
        print("PASS 5 expected=True actual=True")
    else:
        all_pass = False
        print("FAIL 5 expected=True actual=" + repr(a5))

    return all_pass


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(0 if _autotest() else 1)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "chain_rules", sys.argv[1:])
