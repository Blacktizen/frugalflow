import sys
import os
import json
import subprocess
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
BIN = os.path.join(HERE, "..", "bin")
CHECK = os.path.join(BIN, "anon_check.py")

PLANTS = [
    ("email address", "anonymizable", "ann" + "@example.org"),
    ("user path", "anonymizable", "/Us" + "ers/alice/notes"),
    ("IP address", "anonymizable", "10.20" + ".30.40"),
    ("MAC address", "anonymizable", "00:1B:44" + ":11:3A:B7"),
    ("internal host name", "anonymizable", "box.tail1234.ts" + ".net"),
    ("person", "anonymizable", "Zorb" + "lax"),
    ("JWT", "irreducible", "ey" + "JhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0"),  # lang-ok: base64, not a word
    ("API key", "irreducible", "sk" + "-proj-AbCdEfGhIjKlMnOpQrSt0123"),
    ("private key block", "irreducible", "-----BEGIN RSA PRIV" + "ATE KEY-----"),
    ("third-party file", "irreducible", "Quar" + "nix"),
]
RULES = {"anonymizable": [{"pattern": "\\bZorb" + "lax\\b", "label": "person", "tag": "PERSON"}],
         "irreducible": [{"pattern": "(?i)\\bquar" + "nix\\b", "label": "third-party file"}]}
NEUTRAL = "def add(a, b):\n    return a + b\nhost = '127.0.0.1'\nversion = '3.11.2'\nhome = Path.home()\n"
SELF = ["anon_rules.py", "anon_core.py", "anon_check.py"]


def run_check(args):
    return subprocess.run([sys.executable, CHECK] + args, capture_output=True, text=True)


def lines_rstrip(stdout):
    return [ln.rstrip() for ln in stdout.splitlines()]


def main():
    passed = 0
    total = 5

    with tempfile.TemporaryDirectory() as tmp:
        rules_path = os.path.join(tmp, "rules.json")
        with open(rules_path, "w") as f:
            f.write(json.dumps(RULES))

        empty_path = os.path.join(tmp, "empty.json")
        with open(empty_path, "w") as f:
            f.write("{}")

        badre_path = os.path.join(tmp, "badre.json")
        with open(badre_path, "w") as f:
            f.write(json.dumps({"anonymizable": [{"pattern": "(", "label": "x", "tag": "AB"}]}))

        for k in range(1, 11):
            fname = "f%02d.txt" % k
            with open(os.path.join(tmp, fname), "w") as f:
                f.write("line one\nvalue " + PLANTS[k - 1][2] + "\n")

        all_path = os.path.join(tmp, "all.txt")
        with open(all_path, "w") as f:
            for k in range(10):
                f.write(PLANTS[k][2] + "\n")

        neutral_path = os.path.join(tmp, "neutral.txt")
        with open(neutral_path, "w") as f:
            f.write(NEUTRAL)

        # --- TEST 1: TEN LEAKS PLANTED ---
        try:
            ok = True
            details = []
            for k in range(1, 11):
                fpath = os.path.join(tmp, "f%02d.txt" % k)
                r = run_check(["--rules", rules_path, "--scan", fpath])
                if r.returncode != 12:
                    ok = False
                    details.append("f%02d code=%d expected=12" % (k, r.returncode))
                    break
                ls = lines_rstrip(r.stdout)
                if not ls:
                    ok = False
                    details.append("f%02d stdout empty, code=12 expected" % k)
                    break
                kind = PLANTS[k - 1][1]
                label = PLANTS[k - 1][0]
                expected = fpath + ":2: " + kind + " " + label
                if ls[0] != expected:
                    ok = False
                    details.append("f%02d line expected=%r got=%r" % (k, expected, ls[0]))
                    break
                if ls[-1] != "FOUND 1 in 1 of 1 files":
                    ok = False
                    details.append("f%02d last expected=%r got=%r" % (k, "FOUND 1 in 1 of 1 files", ls[-1]))
                    break
            if ok:
                r = run_check(["--rules", rules_path, "--scan", all_path])
                if r.returncode != 12:
                    ok = False
                    details.append("all.txt code=%d expected=12" % r.returncode)
                else:
                    ls = lines_rstrip(r.stdout)
                    if not ls:
                        ok = False
                        details.append("all.txt stdout empty, code=12 expected")
                    else:
                        n_leak = sum(1 for ln in ls if ln.startswith(all_path + ":"))
                        if n_leak != 10:
                            ok = False
                            details.append("all.txt %d lines leak, expected 10" % n_leak)
                        if ls[-1] != "FOUND 10 in 1 of 1 files":
                            ok = False
                            details.append("all.txt last expected=%r got=%r" % ("FOUND 10 in 1 of 1 files", ls[-1]))
            if ok:
                r = run_check(["--rules", rules_path, "--scan", neutral_path])
                if r.returncode != 0:
                    ok = False
                    details.append("neutral code=%d expected=0" % r.returncode)
                else:
                    ls = lines_rstrip(r.stdout)
                    if not ls:
                        ok = False
                        details.append("neutral stdout empty, code=0 expected")
                    elif ls[-1] != "CLEAN 1 files":
                        ok = False
                        details.append("neutral last expected=%r got=%r" % ("CLEAN 1 files", ls[-1]))
            if ok:
                passed += 1
                print("PASS 1: 10 leaks planted, 10 in all.txt, 0 in neutral")
            else:
                print("FAIL 1: " + "; ".join(details))
        except Exception as e:
            print("FAIL 1: exception %r" % e)

        # --- TEST 2: DISARM ---
        try:
            ok = True
            details = []
            for fk in (6, 10):
                fpath = os.path.join(tmp, "f%02d.txt" % fk)
                r = run_check(["--rules", empty_path, "--scan", fpath])
                if r.returncode != 0:
                    ok = False
                    details.append("f%02d code=%d expected=0" % (fk, r.returncode))
                    break
                ls = lines_rstrip(r.stdout)
                if not ls:
                    ok = False
                    details.append("f%02d stdout empty, code=0 expected" % fk)
                    break
                if ls[-1] != "CLEAN 1 files":
                    ok = False
                    details.append("f%02d last expected=%r got=%r" % (fk, "CLEAN 1 files", ls[-1]))
                    break
            if ok:
                r = run_check(["--rules", empty_path, "--scan", all_path])
                if r.returncode != 12:
                    ok = False
                    details.append("all.txt code=%d expected=12" % r.returncode)
                else:
                    ls = lines_rstrip(r.stdout)
                    if not ls:
                        ok = False
                        details.append("all.txt stdout empty, code=12 expected")
                    elif ls[-1] != "FOUND 8 in 1 of 1 files":
                        ok = False
                        details.append("all.txt last expected=%r got=%r" % ("FOUND 8 in 1 of 1 files", ls[-1]))
            if ok:
                passed += 1
                print("PASS 2: disarm, 0 on f06/f10, 8 on all.txt")
            else:
                print("FAIL 2: " + "; ".join(details))
        except Exception as e:
            print("FAIL 2: exception %r" % e)

        # --- TEST 3: THE ANONYMIZER ITSELF CARRIES NOTHING ---
        try:
            ok = True
            details = []
            scan_files = [os.path.join(BIN, s) for s in SELF]
            scan_files.append(os.path.abspath(__file__))
            scan_files.append(os.path.join(HERE, "..", "config", "anonymization.example.json"))
            r = run_check(["--rules", rules_path, "--scan"] + scan_files)
            if r.returncode != 0:
                ok = False
                details.append("code=%d expected=0" % r.returncode)
            else:
                ls = lines_rstrip(r.stdout)
                if not ls:
                    ok = False
                    details.append("stdout empty, code=0 expected")
                elif ls[-1] != "CLEAN 5 files":
                    ok = False
                    details.append("last expected=%r got=%r" % ("CLEAN 5 files", ls[-1]))
            if ok:
                passed += 1
                print("PASS 3: anonymizer clean, 5 files CLEAN")
            else:
                print("FAIL 3: " + "; ".join(details))
        except Exception as e:
            print("FAIL 3: exception %r" % e)

        # --- TEST 4: CLOSED ON THE UNKNOWN ---
        try:
            ok = True
            details = []
            missing_rules = os.path.join(tmp, "no_such_rules.json")
            r = run_check(["--rules", missing_rules, "--scan", neutral_path])
            if r.returncode != 13:
                ok = False
                details.append("rule missing code=%d expected=13" % r.returncode)
            if ok:
                r = run_check(["--rules", badre_path, "--scan", neutral_path])
                if r.returncode != 13:
                    ok = False
                    details.append("badre code=%d expected=13" % r.returncode)
            if ok:
                missing_scan = os.path.join(tmp, "no_such_scan.txt")
                r = run_check(["--rules", empty_path, "--scan", missing_scan])
                if r.returncode != 2:
                    ok = False
                    details.append("file absent code=%d expected=2" % r.returncode)
            if ok:
                r = run_check([])
                if r.returncode != 2:
                    ok = False
                    details.append("without argument code=%d expected=2" % r.returncode)
            if ok:
                passed += 1
                print("PASS 4: closed on the unknown, codes 13/13/2/2")
            else:
                print("FAIL 4: " + "; ".join(details))
        except Exception as e:
            print("FAIL 4: exception %r" % e)

        # --- TEST 5: ROUND-TRIP ---
        try:
            sys.path.insert(0, BIN)
            import anon_rules
            import anon_core

            A, I, errors = anon_rules.load(RULES)
            if errors != []:
                raise AssertionError("errors=%r" % errors)

            TEXT = "\n".join(PLANTS[k][2] for k in range(6))
            clean, counts, table = anon_core.anonymize(TEXT, A, I)

            found = anon_core.find(clean, A, I)
            if found != []:
                raise AssertionError("find(clean)=%r, expected []" % found)

            if sum(counts.values()) != 6:
                raise AssertionError("sum(counts)=%d, expected 6" % sum(counts.values()))

            restored = anon_core.restore(clean, table)
            if restored != TEXT:
                raise AssertionError("restore != TEXT")

            SECRET = PLANTS[6][2]
            result = anon_core.anonymize(SECRET, A, I)[0]
            if result != SECRET:
                raise AssertionError("secret modified")

            passed += 1
            print("PASS 5: round-trip, 6 anonymized, secret intact")
        except Exception as e:
            print("FAIL 5: exception %r" % e)

    if passed == total:
        print("E2E ANONYMIZER OK 5/5")
        return 0
    else:
        print("E2E ANONYMIZER FAILED %d/5" % passed)
        return 1


if __name__ == "__main__":
    sys.exit(main())
