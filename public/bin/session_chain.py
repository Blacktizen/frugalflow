#!/usr/bin/env python3
import json
import hashlib
import sys
import subprocess

GENESIS = "0" * 64


def canonical(record):
    """Return the canonical JSON serialization of a record."""
    return json.dumps(record, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def seal(last, entry):
    """Seal a new entry that follows the last sealed line.

    Returns the new line dict including seq, prev, and hash keys.
    """
    line = dict(entry)
    line["seq"] = 0 if last is None else last["seq"] + 1
    line["prev"] = GENESIS if last is None else last["hash"]
    line["hash"] = hashlib.sha256((line["prev"] + canonical(line)).encode("utf-8")).hexdigest()
    return line


def verify(lines):
    """Verify the hash chain of log lines.

    Returns a 4-tuple (ok, n, bad, reason).
    """
    filtered = [entry for entry in lines if entry.strip()]
    n = len(filtered)
    expected = GENESIS
    for idx, raw in enumerate(filtered):
        try:
            record = json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            return (False, n, idx, "line " + str(idx) + " is not a JSON object")
        if not isinstance(record, dict):
            return (False, n, idx, "line " + str(idx) + " is not a JSON object")
        if record.get("seq") != idx:
            return (False, n, idx, "line " + str(idx) + " has seq " + str(record.get("seq")))
        if record.get("prev") != expected:
            return (False, n, idx, "line " + str(idx) + " does not follow the previous one")
        body = dict(record)
        body.pop("hash", None)
        computed = hashlib.sha256((record["prev"] + canonical(body)).encode("utf-8")).hexdigest()
        if computed != record.get("hash"):
            return (False, n, idx, "line " + str(idx) + " was rewritten")
        expected = record["hash"]
    return (True, n, None, "")


def head(lines):
    """Return the head (seq and hash) of the last non-empty line, or None if empty."""
    filtered = [entry for entry in lines if entry.strip()]
    if not filtered:
        return None
    record = json.loads(filtered[-1])
    return {"seq": record["seq"], "hash": record["hash"]}


def anchor_verdict(anchor, lines):
    """Compare the log to its anchor and return a one-word verdict."""
    records = []
    for entry in lines:
        if entry.strip():
            try:
                records.append(json.loads(entry))
            except (json.JSONDecodeError, ValueError):
                return "REWRITTEN"
    if anchor is None:
        return "NEW"
    if len(records) <= anchor["seq"]:
        return "TRUNCATED"
    if records[anchor["seq"]].get("hash") != anchor["hash"]:
        return "REWRITTEN"
    body = dict(records[anchor["seq"]])
    body.pop("hash", None)
    computed = hashlib.sha256((records[anchor["seq"]]["prev"] + canonical(body)).encode("utf-8")).hexdigest()
    if computed != records[anchor["seq"]].get("hash"):
        return "REWRITTEN"
    if len(records) == anchor["seq"] + 1:
        return "INTACT"
    return "AHEAD"


NOTICE_TEXT = (
    "NAME      session_chain.py - seals each line of a session log with the sha256 of the previous one, verifies the chain, and compares the log to its anchor.\n"
    "READS     nothing: pure module; the caller passes the log lines and the anchor.\n"
    "WRITES    nothing: seal() returns the line to append; verify() returns (ok, lines, first bad index, reason); anchor_verdict() one word.\n"
    "EXAMPLE   python3 session_chain.py --notice\n"
    "PITFALLS  2026-09-19 a chain cannot see a truncation: the last lines removed leave a valid chain.\n"
    "          The anchor, kept outside the log, is what sees it: TRUNCATED."
)


def _autotest():
    r0 = seal(None, {"event": "start", "ts": "2026-09-26T10:00:00+02:00"})
    r1 = seal(r0, {"event": "prompt", "text": "fix the parser"})
    r2 = seal(r1, {"event": "stop", "texts": ["done"]})
    lines = [canonical(r0), canonical(r1), "", canonical(r2)]
    edited = dict(r1)
    edited["text"] = "fix nothing"
    tampered = [canonical(r0), canonical(edited), canonical(r2)]

    all_pass = True

    # Test 1
    t1_got = (
        r0["seq"] == 0
        and r0["prev"] == GENESIS
        and r2["seq"] == 2
        and r2["prev"] == r1["hash"]
        and verify(lines) == (True, 3, None, "")
        and verify([]) == (True, 0, None, "")
        and head([]) is None
        and head(lines) == {"seq": 2, "hash": r2["hash"]}
    )
    if t1_got:
        print("PASS test 1: expected True, got True")
    else:
        all_pass = False
        print("FAIL test 1: expected True, got " + repr(t1_got))

    # Test 2
    t2a = verify(tampered)
    t2b = verify([canonical(r0), canonical(r2)])
    t2c = verify(["not json"])
    t2_got = (
        t2a == (False, 3, 1, "line 1 was rewritten")
        and t2b == (False, 2, 1, "line 1 has seq 2")
        and t2c == (False, 1, 0, "line 0 is not a JSON object")
    )
    if t2_got:
        print("PASS test 2: expected True, got True")
    else:
        all_pass = False
        detail = []
        if t2a != (False, 3, 1, "line 1 was rewritten"):
            detail.append("tampered=" + repr(t2a))
        if t2b != (False, 2, 1, "line 1 has seq 2"):
            detail.append("seq=" + repr(t2b))
        if t2c != (False, 1, 0, "line 0 is not a JSON object"):
            detail.append("json=" + repr(t2c))
        print("FAIL test 2: expected True, got False (" + " ".join(detail) + ")")

    # Test 3
    t3a = anchor_verdict(None, lines)
    t3b = anchor_verdict({"seq": 2, "hash": r2["hash"]}, lines)
    t3c = anchor_verdict({"seq": 1, "hash": r1["hash"]}, lines)
    t3_got = t3a == "NEW" and t3b == "INTACT" and t3c == "AHEAD"
    if t3_got:
        print("PASS test 3: expected True, got True")
    else:
        all_pass = False
        print("FAIL test 3: expected (NEW, INTACT, AHEAD), got (" + t3a + ", " + t3b + ", " + t3c + ")")

    # Test 4
    t4a = anchor_verdict({"seq": 2, "hash": r2["hash"]}, lines[:2])
    t4b = anchor_verdict({"seq": 0, "hash": r0["hash"]}, [])
    t4c = anchor_verdict({"seq": 1, "hash": r1["hash"]}, tampered)
    t4_got = t4a == "TRUNCATED" and t4b == "TRUNCATED" and t4c == "REWRITTEN"
    if t4_got:
        print("PASS test 4: expected True, got True")
    else:
        all_pass = False
        print("FAIL test 4: expected (TRUNCATED, TRUNCATED, REWRITTEN), got (" + t4a + ", " + t4b + ", " + t4c + ")")

    # Test 5
    proc_notice = subprocess.run(
        [sys.executable, __file__, "--notice"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    proc_bogus = subprocess.run(
        [sys.executable, __file__, "--bogus"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    notice_out = proc_notice.stdout.decode("utf-8")
    bogus_out = proc_bogus.stdout.decode("utf-8")
    t5_got = (
        proc_notice.returncode == 0
        and notice_out.startswith("NAME      session_chain.py")
        and proc_bogus.returncode == 2
        and "usage: session_chain.py" in bogus_out
    )
    if t5_got:
        print("PASS test 5: expected True, got True")
    else:
        all_pass = False
        detail = []
        if proc_notice.returncode != 0:
            detail.append("notice rc=" + str(proc_notice.returncode))
        if not notice_out.startswith("NAME      session_chain.py"):
            detail.append("notice out=" + repr(notice_out[:40]))
        if proc_bogus.returncode != 2:
            detail.append("bogus rc=" + str(proc_bogus.returncode))
        if "usage: session_chain.py" not in bogus_out:
            detail.append("bogus out=" + repr(bogus_out[:40]))
        print("FAIL test 5: expected True, got False (" + " ".join(detail) + ")")

    if not all_pass:
        sys.exit(1)
    sys.exit(0)


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE_TEXT)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        _autotest()
    print("usage: session_chain.py --notice | --autotest")
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "session_chain", sys.argv[1:])
