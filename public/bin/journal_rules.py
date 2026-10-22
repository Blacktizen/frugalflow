import sys
import os
import json
import subprocess

FIELDS = ["time", "role", "model_asked", "model_answered", "target", "sha256", "tokens_in", "tokens_out", "status", "reason", "subject", "seconds", "chars", "waiver"]
STATUSES = ["success", "failure", "refused"]

S0 = {"role": "code", "model_asked": "alpha-7b", "model_answered": None, "target": "out.py", "tokens_in": None, "tokens_out": None, "status": "failure", "reason": "exit without conclusion", "subject": "NATURE: creation"}
LINE0 = '{"time": "2026-09-23T10:00:00", "role": "code", "model_asked": "alpha-7b", "model_answered": null, "target": "out.py", "sha256": null, "tokens_in": null, "tokens_out": null, "status": "failure", "reason": "exit without conclusion", "subject": "NATURE: creation", "seconds": null, "chars": null, "waiver": null}'
LOG = '{"status": "success"}\n\nnot json\n[1, 2]\n{"status": "weird"}\n'

USAGE = "usage: journal_rules.py --notice | --autotest"

NOTICE = """NAME      journal_rules.py - builds one delegation log line (role, model asked, model that answered, tokens, status) and reads a log back.
READS     nothing: pure module; it works on the values and texts it is given.
WRITES    nothing: to_line() returns the JSON line, parse_lines() and summarize() what a log holds.
EXAMPLE   python3 journal_rules.py --notice
PITFALLS  2026-08-23 the log named the backend, not the model that answered; both are now recorded.
          A success answered by another model is logged as a failure.
"""

def new_state(role, model_asked, target, subject):
    return {"role": role, "model_asked": model_asked, "model_answered": None, "target": target, "tokens_in": None, "tokens_out": None, "status": "failure", "reason": "exit without conclusion", "subject": subject}

def conclude(state, status, reason=None, tokens_in=None, tokens_out=None, model_answered=None):
    result = dict(state)
    result["status"] = status
    result["reason"] = reason
    result["tokens_in"] = tokens_in
    result["tokens_out"] = tokens_out
    result["model_answered"] = model_answered
    if status not in STATUSES:
        result["status"] = "failure"
        result["reason"] = "unknown status: " + str(status)
    if result["status"] == "success" and model_answered is not None and model_answered != state["model_asked"]:
        result["status"] = "failure"
        result["reason"] = "answered by " + str(model_answered) + " instead of " + str(state["model_asked"])
    return result

def to_line(state, now, sha256):
    d = {}
    for field in FIELDS:
        if field == "time":
            d[field] = now
        elif field == "sha256":
            d[field] = sha256
        else:
            d[field] = state.get(field)
    subj = d.get("subject")
    if isinstance(subj, str):
        subj = subj.replace("\n", " ").replace("\r", " ")
        subj = subj[:80]
        d["subject"] = subj
    return json.dumps(d, ensure_ascii=False)

def parse_lines(text):
    records = []
    unreadable = 0
    for raw in text.split("\n"):
        line = raw.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except ValueError:
            unreadable += 1
        else:
            if isinstance(obj, dict):
                records.append(obj)
            else:
                unreadable += 1
    return records, unreadable

def summarize(records):
    counts = {"records": len(records), "success": 0, "failure": 0, "refused": 0, "other": 0}
    for rec in records:
        status = rec.get("status")
        if status in STATUSES:
            counts[status] += 1
        else:
            counts["other"] += 1
    return counts

def autotest():
    results = []
    # test 1
    try:
        s = new_state("code", "alpha-7b", "out.py", "NATURE: creation")
        line = to_line(S0, "2026-09-23T10:00:00", None)
        ok = (s == S0 and line == LINE0)
        expected_str = "new_state(...) == S0 and to_line(...) == LINE0"
        obtained_str = str(ok)
    except Exception as e:
        ok = False
        obtained_str = repr(e)
    if ok:
        print(f"PASS test 1: want {expected_str}, got {obtained_str}")
        results.append(True)
    else:
        print(f"FAIL test 1: want {expected_str}, got {obtained_str}")
        results.append(False)

    # test 2
    try:
        c = conclude(S0, "success", None, 10, 20, "alpha-7b")
        expected = dict(S0, status="success", reason=None, tokens_in=10, tokens_out=20, model_answered="alpha-7b")
        ok = (c == expected and S0["status"] == "failure")
        expected_str = "conclude(...) == expected and S0 unchanged"
        obtained_str = str(ok)
    except Exception as e:
        ok = False
        obtained_str = repr(e)
    if ok:
        print(f"PASS test 2: want {expected_str}, got {obtained_str}")
        results.append(True)
    else:
        print(f"FAIL test 2: want {expected_str}, got {obtained_str}")
        results.append(False)

    # test 3
    try:
        r1 = conclude(S0, "success", None, 10, 20, "beta-3b")
        r2 = conclude(S0, "done")
        ok = (r1["status"] == "failure" and r1["reason"] == "answered by beta-3b instead of alpha-7b" and r2["reason"] == "unknown status: done")
        expected_str = "status failure, reason answered by..., reason unknown status"
        obtained_str = str(ok)
    except Exception as e:
        ok = False
        obtained_str = repr(e)
    if ok:
        print(f"PASS test 3: want {expected_str}, got {obtained_str}")
        results.append(True)
    else:
        print(f"FAIL test 3: want {expected_str}, got {obtained_str}")
        results.append(False)

    # test 4
    try:
        parsed, unread = parse_lines(LOG)
        sum1 = summarize(parsed)
        line_subject = json.loads(to_line(dict(S0, subject="a\nb" + "x" * 100), "t", "h"))["subject"]
        ok = (parsed == [{"status": "success"}, {"status": "weird"}] and unread == 2 and sum1 == {"records": 2, "success": 1, "failure": 0, "refused": 0, "other": 1} and line_subject == "a b" + "x" * 77)
        expected_str = "parse(s) == ..., summarize == ..., subject == ..."
        obtained_str = str(ok)
    except Exception as e:
        ok = False
        obtained_str = repr(e)
    if ok:
        print(f"PASS test 4: want {expected_str}, got {obtained_str}")
        results.append(True)
    else:
        print(f"FAIL test 4: want {expected_str}, got {obtained_str}")
        results.append(False)

    # test 5
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        ok = (proc.returncode == 0 and proc.stdout.startswith("NAME      journal_rules.py"))
        expected_str = "returncode=0 and stdout starts with NAME..."
        obtained_str = f"returncode={proc.returncode}, stdout_prefix={proc.stdout[:30]!r}"
    except Exception as e:
        ok = False
        obtained_str = repr(e)
    if ok:
        print(f"PASS test 5: want {expected_str}, got {obtained_str}")
        results.append(True)
    else:
        print(f"FAIL test 5: want {expected_str}, got {obtained_str}")
        results.append(False)

    return all(results)

def main():
    if len(sys.argv) == 1:
        print(USAGE)
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        ok = autotest()
        sys.exit(0 if ok else 1)
    else:
        print(USAGE)
        sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "journal_rules", sys.argv[1:])
