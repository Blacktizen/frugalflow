import sys
import os
import subprocess

DOC = {"models": [
    {"id": "reader", "name": "alpha-7b", "location": "local", "paid": False},
    {"id": "coder", "name": "beta-pro", "location": "remote", "paid": True},
    {"id": "me", "name": "session", "location": "in_session", "paid": True, "price_in": 3, "price_out": 15}]}

REC = [
    {"model_asked": "alpha-7b", "model_answered": "alpha-7b", "status": "success", "tokens_in": 20000, "tokens_out": 10000},
    {"model_asked": "alpha-7b", "model_answered": None, "status": "failure", "tokens_in": 5, "tokens_out": 5},
    {"model_asked": "beta-pro", "model_answered": "beta-pro", "status": "success", "tokens_in": 1, "tokens_out": 1},
    {"model_asked": "gamma", "model_answered": "gamma", "status": "success", "tokens_in": True, "tokens_out": 3}]

def model_index(models_doc):
    if not isinstance(models_doc, dict):
        return {}
    models = models_doc.get("models")
    if not isinstance(models, list):
        return {}
    result = {}
    for entry in models:
        if isinstance(entry, dict) and isinstance(entry.get("name"), str):
            result[entry["name"]] = entry
    return result

def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)

def session_prices(models_doc):
    if not isinstance(models_doc, dict):
        return (None, None)
    models = models_doc.get("models")
    if not isinstance(models, list):
        return (None, None)
    for entry in models:
        if isinstance(entry, dict) and entry.get("location") == "in_session":
            price_in = entry.get("price_in")
            price_out = entry.get("price_out")
            if _is_number(price_in) and _is_number(price_out):
                return (price_in, price_out)
            else:
                return (None, None)
    return (None, None)

def summarize(records, index):
    n = 0
    success = 0
    free = 0
    paid = 0
    unknown = 0
    free_in = 0
    free_out = 0
    for record in records:
        if not isinstance(record, dict):
            continue
        name = None
        model_answered = record.get("model_answered")
        if isinstance(model_answered, str) and model_answered:
            name = model_answered
        else:
            name = record.get("model_asked")
        input = index.get(name)
        if input is None:
            unknown += 1
            is_free = False
        elif input.get("paid") is True:
            paid += 1
            is_free = False
        else:
            free += 1
            is_free = True
        n += 1
        if record.get("status") == "success":
            success += 1
            if is_free:
                tokens_in = record.get("tokens_in")
                tokens_out = record.get("tokens_out")
                if _is_number(tokens_in) and isinstance(tokens_in, int):
                    free_in += tokens_in
                if _is_number(tokens_out) and isinstance(tokens_out, int):
                    free_out += tokens_out
    escalation_rate = round(100 * paid / n, 1) if n > 0 else 0.0
    return {
        "delegations": n,
        "success": success,
        "free": free,
        "paid": paid,
        "unknown": unknown,
        "escalation_rate": escalation_rate,
        "free_in": free_in,
        "free_out": free_out,
    }

def counterfactual(summary, price_in, price_out):
    if price_in is None or price_out is None:
        return None
    return round((summary["free_in"] * price_in + summary["free_out"] * price_out) / 1000000, 2)

def report(summary, cost):
    lines = []
    lines.append("DELEGATIONS " + str(summary["delegations"]) + " | success " + str(summary["success"]) + " | free " + str(summary["free"]) + " | paid " + str(summary["paid"]) + " | unknown " + str(summary["unknown"]) + " | escalation rate " + str(summary["escalation_rate"]) + " %")
    lines.append("FREE WORK tokens in " + str(summary["free_in"]) + ", out " + str(summary["free_out"]))
    if cost is None:
        lines.append("COUNTERFACTUAL unknown: no price_in and price_out on the in_session model")
    else:
        lines.append("COUNTERFACTUAL on the session model: " + format(cost, ".2f"))
    return lines

NOTICE = """NAME      ledger_rules.py - sums a delegation log: free or paid, the escalation rate always shown, and what the free work would have cost on the session model.
READS     nothing: pure module; it works on the log records and the models document it is given.
WRITES    nothing: summarize() returns the counts, report() three lines.
EXAMPLE   python3 ledger_rules.py --notice
PITFALLS  2026-09-23 a saving was claimed without a price; with no price on the session model the counterfactual says unknown."""

USAGE = "usage: ledger_rules.py --notice | --autotest"

def run_autotests():
    checks = []

    # Test 1
    idx_keys = sorted(model_index(DOC))
    idx_empty = model_index([])
    prices_full = session_prices(DOC)
    prices_missing = session_prices({"models": [{"location": "in_session", "price_in": 3}]})
    cond1 = (idx_keys == ["alpha-7b", "beta-pro", "session"] and idx_empty == {} and prices_full == (3, 15) and prices_missing == (None, None))
    print(("PASS" if cond1 else "FAIL") + " test 1 expected=['alpha-7b', 'beta-pro', 'session'], {}, (3, 15), (None, None) obtained=" + repr((idx_keys, idx_empty, prices_full, prices_missing)))
    checks.append(cond1)

    # Test 2
    idx2 = model_index(DOC)
    s2 = summarize(REC, idx2)
    expected2 = {"delegations": 4, "success": 3, "free": 2, "paid": 1, "unknown": 1, "escalation_rate": 25.0, "free_in": 20000, "free_out": 10000}
    cond2 = (s2 == expected2)
    print(("PASS" if cond2 else "FAIL") + " test 2 expected=" + repr(expected2) + " obtained=" + repr(s2))
    checks.append(cond2)

    # Test 3
    s3_empty = summarize([], {})
    expected3_empty = {"delegations": 0, "success": 0, "free": 0, "paid": 0, "unknown": 0, "escalation_rate": 0.0, "free_in": 0, "free_out": 0}
    s3_rec = summarize(REC, model_index(DOC))
    cf1 = counterfactual(s3_rec, 3, 15)
    cf2 = counterfactual(s3_rec, None, 15)
    cond3 = (s3_empty == expected3_empty and cf1 == 0.21 and cf2 is None)
    print(("PASS" if cond3 else "FAIL") + " test 3 expected=" + repr((expected3_empty, 0.21, None)) + " obtained=" + repr((s3_empty, cf1, cf2)))
    checks.append(cond3)

    # Test 4
    s4 = summarize(REC, model_index(DOC))
    r4 = report(s4, 0.21)
    r4_none = report(s4, None)
    expected4 = ["DELEGATIONS 4 | success 3 | free 2 | paid 1 | unknown 1 | escalation rate 25.0 %", "FREE WORK tokens in 20000, out 10000", "COUNTERFACTUAL on the session model: 0.21"]
    cond4 = (r4 == expected4 and r4_none[2] == "COUNTERFACTUAL unknown: no price_in and price_out on the in_session model")
    print(("PASS" if cond4 else "FAIL") + " test 4 expected=" + repr((expected4, "COUNTERFACTUAL unknown: no price_in and price_out on the in_session model")) + " obtained=" + repr((r4, r4_none[2])))
    checks.append(cond4)

    # Test 5
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    cond5 = (proc.returncode == 0 and proc.stdout.startswith("NAME      ledger_rules.py"))
    print(("PASS" if cond5 else "FAIL") + " test 5 expected=(returncode=0, stdout starts with 'NAME      ledger_rules.py') obtained=(returncode=" + str(proc.returncode) + ", stdout_prefix=" + repr(proc.stdout[:50]) + ")")
    checks.append(cond5)

    return all(checks)

def main():
    if len(sys.argv) == 1:
        print(USAGE)
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        ok = run_autotests()
        sys.exit(0 if ok else 1)
    else:
        print(USAGE)
        sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "ledger_rules", sys.argv[1:])
