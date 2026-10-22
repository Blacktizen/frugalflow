import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anon_core

TRUSTS = ["private", "trusted_third_party", "untrusted_third_party"]

def outbound(text, trust, anonymizable, irreducible, table=None):
    if trust not in TRUSTS:
        return (None, {}, {}, "unknown trust: " + str(trust))
    if trust == "private":
        return (text, {} if table is None else table, {}, None)
    findings = anon_core.find(text, anonymizable, irreducible)
    irreducible_labels = sorted(set(label for _, kind, label, _ in findings if kind == "irreducible"))
    if irreducible_labels:
        return (None, {}, {}, "irreducible data found: " + ", ".join(irreducible_labels))
    clean, counts, table = anon_core.anonymize(text, anonymizable, irreducible, {} if table is None else table)
    return (clean, table, counts, None)

def inbound(text, table):
    if not table:
        return text
    return anon_core.restore(text, table)

def announce(counts):
    if not counts:
        return ""
    items = sorted(counts.items())
    parts = [f"{label} x{count}" for label, count in items]
    return "anonymized before sending: " + ", ".join(parts)

E1 = "ann" + "@example.org"
E2 = "bob" + "@example.org"
A = [("[a-z]+@[a-z]+\\.org", "email address", "EMAIL"), ("\\bPlimsoq\\b", "person", "PERSON")]
I = [("KEY=[A-Z0-9]{8,}", "key")]
T1 = "Hello Plimsoq, write to " + E1 + " or " + E2 + "."
C1 = "Hello __PERSON_1__, write to __EMAIL_1__ or __EMAIL_2__."
TAB1 = {"__PERSON_1__": "Plimsoq", "__EMAIL_1__": E1, "__EMAIL_2__": E2}
T2 = "Plimsoq uses KEY=ABCD1234 today"

NOTICE = """NAME      send_rules.py - decides what may leave for a model: everything to a private one, labels instead of personal data to a third party, nothing when a secret is found.
READS     nothing: pure module; it applies the pattern lists it is given.
WRITES    nothing: outbound() returns the text to send, its table and counts, or a refusal naming only labels.
EXAMPLE   python3 send_rules.py --notice
PITFALLS  2026-08-07 the gate refused instead of cleaning, so nothing ever left; personal data is now labelled, secrets still refuse.
          2026-08-08 a retry sent the verify report in clear; the same table must be passed again."""

def run_autotest():
    results = []

    # Test 1
    try:
        r1a = outbound(T1, "private", A, I)
        r1b = outbound(T2, "private", A, I)
        r1 = r1a == (T1, {}, {}, None) and r1b == (T2, {}, {}, None)
        expected1 = "outbound(T1, 'private') == (T1, {}, {}, None) and outbound(T2, 'private') == (T2, {}, {}, None)"
        actual1 = f"outbound(T1, 'private')={r1a}, outbound(T2, 'private')={r1b}"
    except Exception as e:
        r1 = False
        expected1 = "no exception"
        actual1 = f"Exception: {e}"
    results.append((1, r1, expected1, actual1))

    # Test 2
    try:
        r2a = outbound(T1, "untrusted_third_party", A, I)
        r2b = inbound(C1, TAB1)
        r2c = inbound("x", {})
        r2 = r2a == (C1, TAB1, {"person": 1, "email address": 2}, None) and r2b == T1 and r2c == "x"
        expected2 = "(C1, TAB1, counts, None) and inbound(C1, TAB1) == T1 and inbound('x', {}) == 'x'"
        actual2 = f"outbound(...)={r2a}, inbound(C1, TAB1)={r2b}, inbound('x', {{}})={r2c}"
    except Exception as e:
        r2 = False
        expected2 = "no exception"
        actual2 = f"Exception: {e}"
    results.append((2, r2, expected2, actual2))

    # Test 3
    try:
        r3a = outbound(T2, "trusted_third_party", A, I)
        r3b = outbound(T1, "public", A, I)
        r3 = r3a == (None, {}, {}, "irreducible data found: key") and r3b == (None, {}, {}, "unknown trust: public")
        expected3 = "(None, {}, {}, 'irreducible data found: key') and (None, {}, {}, 'unknown trust: public')"
        actual3 = f"outbound(T2, 'trusted_third_party')={r3a}, outbound(T1, 'public')={r3b}"
    except Exception as e:
        r3 = False
        expected3 = "no exception"
        actual3 = f"Exception: {e}"
    results.append((3, r3, expected3, actual3))

    # Test 4
    try:
        t = dict(TAB1)
        r4a = outbound("Mail " + E2 + " again", "untrusted_third_party", A, I, t)
        ann1 = announce({"person": 1, "email address": 2})
        ann2 = announce({})
        r4 = r4a == ("Mail __EMAIL_2__ again", TAB1, {"email address": 1}, None) and ann1 == "anonymized before sending: email address x2, person x1" and ann2 == ""
        expected4 = "outbound(...) == ('Mail __EMAIL_2__ again', TAB1, {'email address': 1}, None) and announce(...) == 'anonymized before sending: email address x2, person x1' and announce({}) == ''"
        actual4 = f"res4={r4a}, ann1={ann1}, ann2={ann2}"
    except Exception as e:
        r4 = False
        expected4 = "no exception"
        actual4 = f"Exception: {e}"
    results.append((4, r4, expected4, actual4))

    # Test 5
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        r5 = proc.returncode == 0 and proc.stdout.startswith("NAME      send_rules.py")
        expected5 = "returncode 0 and stdout startswith 'NAME      send_rules.py'"
        actual5 = f"returncode={proc.returncode}, stdout={proc.stdout!r}"
    except Exception as e:
        r5 = False
        expected5 = "no exception"
        actual5 = f"Exception: {e}"
    results.append((5, r5, expected5, actual5))

    all_pass = True
    for num, success, expected, actual in results:
        status = "PASS" if success else "FAIL"
        print(f"{status} test {num}: expected {expected}, got {actual}")
        if not success:
            all_pass = False
    sys.exit(0 if all_pass else 1)

def main():
    if len(sys.argv) == 1:
        print("usage: send_rules.py --notice | --autotest")
        sys.exit(2)
    arg = sys.argv[1]
    if arg == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif arg == "--autotest":
        run_autotest()
    else:
        print("usage: send_rules.py --notice | --autotest")
        sys.exit(2)

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "send_rules", sys.argv[1:])
