#!/usr/bin/env python3
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timedelta, timezone


def parse_lines(text):
    result = []
    for line in text.splitlines():
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            continue
        if isinstance(obj, dict):
            result.append(obj)
    return result


def to_time(value, tz):
    if not isinstance(value, str):
        return None
    s = value
    if s.endswith("Z"):
        s = s[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(s)
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=tz)
    return dt


def same_target(a, b):
    if not isinstance(a, str) or not a:
        return False
    if not isinstance(b, str) or not b:
        return False
    if a == b:
        return True
    if os.path.abspath(os.path.expanduser(a)) == os.path.abspath(os.path.expanduser(b)):
        return True
    if "/" not in b and os.path.basename(a) == b:
        return True
    return False


def is_receipt(r):
    if not isinstance(r, dict):
        return False
    if r.get("status") != "success":
        return False
    ma = r.get("model_answered")
    if not isinstance(ma, str) or not ma:
        return False
    tg = r.get("target")
    if not isinstance(tg, str) or not tg:
        return False
    return True


def find_receipt(records, target, now, validity_minutes=60):
    best = None
    best_t = None
    for r in records:
        if not is_receipt(r):
            continue
        if not isinstance(target, str) or not target or os.path.abspath(os.path.expanduser(r["target"])) != os.path.abspath(os.path.expanduser(target)):
            continue
        t = to_time(r.get("time"), now.tzinfo)
        if t is None:
            continue
        if t > now + timedelta(minutes=2):
            continue
        if now - t > timedelta(minutes=validity_minutes):
            continue
        if best_t is None or t >= best_t:
            best_t = t
            best = r
    return best


def fingerprint(text):
    if isinstance(text, bytes):
        data = text
    else:
        data = str(text).encode("utf-8")
    return hashlib.sha256(data).hexdigest()


def content_verdict(records, target, content, now, validity_minutes=60, fragment=False):
    r = find_receipt(records, target, now, validity_minutes)
    if r is None:
        return "no_receipt"
    if not r.get("sha256"):
        return "no_fingerprint"
    if not fragment and fingerprint(content) == r["sha256"]:
        return "match"
    for e in records:
        if not isinstance(e, dict):
            continue
        if e.get("kind") != "edit":
            continue
        if not same_target(e.get("target"), target):
            continue
        reason = e.get("reason")
        if not isinstance(reason, str) or not reason:
            continue
        t = to_time(e.get("time"), now.tzinfo)
        if t is None:
            continue
        delta = (now - t).total_seconds()
        if 0 <= delta <= 900:
            return "declared_edit"
    return "divergent"


# --- fixtures ---

UTC = timezone.utc
NOW = datetime(2026, 9, 25, 12, 0, tzinfo=UTC)


def AT(minutes):
    return (NOW + timedelta(minutes=minutes)).isoformat()


def REC(minutes, **kw):
    r = {"time": AT(minutes), "status": "success", "model_answered": "m", "target": "/w/a.py", "sha256": fingerprint("x\n")}
    r.update(kw)
    return r


LINES = '{"a": 1}\n\nnot json\n[1]\n{"b": 2}\n'
EDIT = {"kind": "edit", "target": "/w/a.py", "time": AT(-5), "reason": "r"}


# --- notice ---

NOTICE = (
    "NAME      receipt_rules.py - says whether a code file comes from a recent, successful delegation, "
    "and whether the content about to be written is the one the delegation returned.\n"
    "READS     nothing: pure module; the caller passes the decoded delegation log lines and the current time.\n"
    "WRITES    nothing: find_receipt() returns the newest valid receipt or None; "
    "content_verdict() returns no_receipt, no_fingerprint, match, declared_edit or divergent.\n"
    "EXAMPLE   python3 receipt_rules.py --notice\n"
    "PITFALLS  2026-09-25 a naive guard accepted any log line naming a model, a failed delegation included, "
    "and accepted everything when the log was unreadable: it failed open.\n"
    "          A receipt now needs status success and a model that answered; "
    "an unreadable log is the caller's refusal, never an acceptance.\n"
    "          2026-09-27 a receipt also matched a bare name by basename; it now covers only the exact file delegated (operator decision)."
)


# --- autotest ---

def _autotest():
    all_pass = True

    # Test 1
    try:
        got = (
            parse_lines(LINES) == [{"a": 1}, {"b": 2}]
            and to_time("2026-09-25T11:00:00Z", UTC) == datetime(2026, 9, 25, 11, 0, tzinfo=UTC)
            and to_time("2026-09-25T11:00:00", UTC) == datetime(2026, 9, 25, 11, 0, tzinfo=UTC)
            and to_time("x", UTC) is None
            and to_time(5, UTC) is None
        )
        if got:
            print("PASS 1: expected all assertions true, got True")
        else:
            print("FAIL 1: expected all assertions true, got False")
            all_pass = False
    except Exception as exc:
        print(f"FAIL 1: expected all assertions true, got {type(exc).__name__}: {exc}")
        all_pass = False

    # Test 2
    try:
        got = (
            find_receipt([REC(-3)], "/w/a.py", NOW) == REC(-3)
            and find_receipt([REC(-180)], "/w/a.py", NOW) is None
            and find_receipt([REC(10)], "/w/a.py", NOW) is None
            and find_receipt([REC(1)], "/w/a.py", NOW) == REC(1)
            and find_receipt([REC(-3, status="failure")], "/w/a.py", NOW) is None
            and find_receipt([REC(-3, model_answered="")], "/w/a.py", NOW) is None
            and find_receipt([REC(-3, target="/w/b.py")], "/w/a.py", NOW) is None
            and find_receipt([REC(-3, target="/w/a.py")], "a.py", NOW) is None
            and find_receipt([REC(-2, sha256="new"), REC(-9, sha256="old")], "/w/a.py", NOW)["sha256"] == "new"
        )
        if got:
            print("PASS 2: expected all assertions true, got True")
        else:
            print("FAIL 2: expected all assertions true, got False")
            all_pass = False
    except Exception as exc:
        print(f"FAIL 2: expected all assertions true, got {type(exc).__name__}: {exc}")
        all_pass = False

    # Test 3
    try:
        got = (
            same_target("/w/a.py", "a.py") is True
            and same_target("/w/a.py", "b/a.py") is False
            and same_target("~/x.py", os.path.expanduser("~/x.py")) is True
            and same_target(None, "a") is False
            and same_target("/w/a.py", "") is False
        )
        if got:
            print("PASS 3: expected all assertions true, got True")
        else:
            print("FAIL 3: expected all assertions true, got False")
            all_pass = False
    except Exception as exc:
        print(f"FAIL 3: expected all assertions true, got {type(exc).__name__}: {exc}")
        all_pass = False

    # Test 4
    try:
        got = (
            content_verdict([REC(-3)], "/w/a.py", "x\n", NOW) == "match"
            and content_verdict([REC(-3)], "/w/a.py", "y\n", NOW) == "divergent"
            and content_verdict([REC(-3)], "/w/a.py", "x\n", NOW, fragment=True) == "divergent"
            and content_verdict([REC(-3), EDIT], "/w/a.py", "y\n", NOW) == "declared_edit"
            and content_verdict([REC(-3), dict(EDIT, time=AT(-20))], "/w/a.py", "y\n", NOW) == "divergent"
            and content_verdict([REC(-3, sha256=None)], "/w/a.py", "x\n", NOW) == "no_fingerprint"
            and content_verdict([], "/w/a.py", "x\n", NOW) == "no_receipt"
            and fingerprint(b"x\n") == fingerprint("x\n")
        )
        if got:
            print("PASS 4: expected all assertions true, got True")
        else:
            print("FAIL 4: expected all assertions true, got False")
            all_pass = False
    except Exception as exc:
        print(f"FAIL 4: expected all assertions true, got {type(exc).__name__}: {exc}")
        all_pass = False

    # Test 5
    try:
        r1 = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--notice"],
            capture_output=True, text=True
        )
        r2 = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True
        )
        ok1 = r1.returncode == 0 and r1.stdout.startswith("NAME      receipt_rules.py")
        ok2 = r2.returncode == 2 and r2.stdout == "usage: receipt_rules.py --notice | --autotest\n"
        got = ok1 and ok2
        if got:
            print("PASS 5: expected notice rc=0 and noarg rc=2, got True")
        else:
            print(f"FAIL 5: expected notice rc=0/noarg rc=2, got notice_rc={r1.returncode} ok1={ok1} noarg_rc={r2.returncode} ok2={ok2}")
            all_pass = False
    except Exception as exc:
        print(f"FAIL 5: expected notice rc=0/noarg rc=2, got {type(exc).__name__}: {exc}")
        all_pass = False

    return 0 if all_pass else 1


# --- entry point ---

def _cli():
        if len(sys.argv) == 2 and sys.argv[1] == "--notice":
            print(NOTICE)
            sys.exit(0)
        elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
            sys.exit(_autotest())
        else:
            print("usage: receipt_rules.py --notice | --autotest")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "receipt_rules", sys.argv[1:])
