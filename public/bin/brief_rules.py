import json
import os
import re
import subprocess
import sys
import unicodedata

TYPES = {
    "code_block_min_lines": ["lines"],
    "regex_all": ["patterns"],
    "regex_none": ["patterns"],
    "each_line": ["if", "then"],
    "declared_at_most": ["key", "limit"],
    "lines_at_most": ["limit"],
}

FENCE = "`" * 3


def normalize(text):
    text = text.lower()
    text = unicodedata.normalize("NFD", text)
    text = "".join(c for c in text if unicodedata.category(c) != "Mn")
    return text


def check_doc(doc):
    defects = []
    if not isinstance(doc, dict):
        return ["not an object"]

    limits = doc.get("limits")
    if (not isinstance(limits, dict)
            or any(isinstance(v, bool) or not isinstance(v, int) for v in limits.values())):
        defects.append("limits must map names to integers")
        limits = {}

    rules = doc.get("rules")
    if not isinstance(rules, list):
        defects.append("rules must be a list")
        return defects

    for i, r in enumerate(rules):
        if not isinstance(r, dict):
            defects.append("rule %d: not an object" % i)
            continue

        X = r.get("id")
        if not isinstance(X, str) or not X:
            X = str(i)

        for field_name in ("id", "title", "fix"):
            val = r.get(field_name)
            if not isinstance(val, str) or not val:
                defects.append("rule %s: missing %s" % (X, field_name))

        b = r.get("born_from")
        if (not isinstance(b, dict)
                or not (isinstance(b.get("date"), str) and b.get("date"))
                or not (isinstance(b.get("incident"), str) and b.get("incident"))):
            defects.append("rule %s: missing born_from" % X)

        t = r.get("trigger")
        if (not isinstance(t, dict)
                or any(k not in ("trust", "any", "regex") for k in t)
                or ("any" in t and (not isinstance(t["any"], list)
                                    or any(not isinstance(x, str) for x in t["any"])))):
            defects.append("rule %s: bad trigger" % X)

        q = r.get("requirement")
        if not isinstance(q, dict):
            defects.append("rule %s: bad requirement" % X)
            continue
        rtype = q.get("type")
        if rtype not in TYPES:
            defects.append("rule %s: bad requirement" % X)
            continue
        if any(key not in q for key in TYPES[rtype]):
            defects.append("rule %s: bad requirement" % X)
            continue

        patterns_to_check = []
        if isinstance(t, dict) and "regex" in t:
            patterns_to_check.append(t["regex"])
        if "patterns" in q:
            for p in q["patterns"]:
                patterns_to_check.append(p)
        if "if" in q:
            patterns_to_check.append(q["if"])
        if "then" in q:
            patterns_to_check.append(q["then"])
        if "key" in q:
            patterns_to_check.append(q["key"])

        for pattern_item in patterns_to_check:
            if not isinstance(pattern_item, str):
                defects.append("rule %s: bad regex %s" % (X, pattern_item))
                break
            try:
                re.compile(pattern_item)
            except re.error:
                defects.append("rule %s: bad regex %s" % (X, pattern_item))
                break

        if rtype == "code_block_min_lines":
            if not isinstance(q["lines"], int) or isinstance(q["lines"], bool):
                defects.append("rule %s: bad requirement" % X)
        if rtype in ("declared_at_most", "lines_at_most"):
            if q["limit"] not in limits:
                defects.append("rule %s: unknown limit %s" % (X, q["limit"]))

    return defects


def fires(rule, norm, trust):
    t = rule["trigger"]
    if "trust" in t and t["trust"] != trust:
        return False
    if "any" in t:
        if not any(w in norm for w in t["any"]):
            return False
    if "regex" in t:
        if re.search(t["regex"], norm) is None:
            return False
    return True


def holds(req, text, norm, limits):
    lines = text.splitlines()
    nlines = norm.splitlines()
    rtype = req["type"]

    if rtype == "code_block_min_lines":
        i = 0
        while i < len(lines):
            if lines[i].strip().startswith(FENCE):
                j = None
                for k in range(i + 1, len(lines)):
                    if lines[k].strip() == FENCE:
                        j = k
                        break
                if j is not None:
                    if j - i - 1 >= req["lines"]:
                        return True
                    i = j + 1
                else:
                    i += 1
            else:
                i += 1
        return False

    if rtype == "regex_all":
        return all(re.search(p, norm) is not None for p in req["patterns"])

    if rtype == "regex_none":
        return all(re.search(p, norm) is None for p in req["patterns"])

    if rtype == "each_line":
        for l in nlines:
            if re.search(req["if"], l) and not re.search(req["then"], l):
                return False
        return True

    if rtype == "declared_at_most":
        for l in nlines:
            m = re.search(req["key"], l)
            if m:
                n = re.search(r"\d+", l[m.end():])
                if n is None:
                    return False
                return int(n.group()) <= limits[req["limit"]]
        return False

    if rtype == "lines_at_most":
        return len(lines) <= limits[req["limit"]]

    return False


def evaluate(text, doc, trust="private"):
    defects = check_doc(doc)
    if defects:
        raise ValueError("; ".join(defects))
    norm = normalize(text)
    return [r for r in doc["rules"]
            if fires(r, norm, trust) and not holds(r["requirement"], text, norm, doc["limits"])]


def explain(rule):
    return ("REFUSED %s - %s\n  born %s: %s\n  To fix: %s"
            % (rule["id"], rule["title"],
               rule["born_from"]["date"], rule["born_from"]["incident"],
               rule["fix"]))


_NOTICE = (
    "NAME      brief_rules.py - checks a delegation brief against given rules and returns the refused rules, each with how to fix the brief.\n"
    "READS     nothing: pure module; the caller passes the brief text, the decoded rules document and the trust level of the target.\n"
    "WRITES    nothing: evaluate() returns the refused rules in document order; explain() turns one into three lines ending with the fix; check_doc() lists what is wrong in a rules document.\n"
    "EXAMPLE   python3 brief_rules.py --notice\n"
    "PITFALLS  2026-09-26 a naive guard fired on bare words: a quoted option, a function name, a verb. Triggers are now written for the case, and every refusal says how to fix the brief.\n"
)


def _autotest():
    BASE = {"id": "A1", "title": "t", "born_from": {"date": "2026-01-01", "incident": "i"},
            "fix": "write nature:", "trigger": {},
            "requirement": {"type": "regex_all", "patterns": ["nature:"]}}

    def RULE(rid, trigger, requirement):
        return dict(BASE, id=rid, trigger=trigger, requirement=requirement)

    def D(*rules):
        return {"limits": {"max_tests": 2, "max_lines": 3}, "rules": list(rules)}

    def IDS(text, doc, trust="private"):
        return [r["id"] for r in evaluate(text, doc, trust)]

    T = RULE("T", {"trust": "untrusted_third_party"}, {"type": "regex_none", "patterns": ["/srv/"]})
    W = RULE("W", {"any": ["epreuve"], "regex": "epreuve \\d"}, {"type": "regex_all", "patterns": ["grandeur"]})  # lang-ok: French brief words the rules read
    V = RULE("V", {}, {"type": "each_line", "if": "--check\\s+'", "then": "\\$[a-z_]+"})
    N = RULE("N", {}, {"type": "declared_at_most", "key": "tests:", "limit": "max_tests"})
    M = RULE("M", {}, {"type": "lines_at_most", "limit": "max_lines"})
    K = RULE("K", {}, {"type": "code_block_min_lines", "lines": 2})
    Z = RULE("Z", {}, {"type": "regex_none", "patterns": ["\\t"]})
    FENCE = "`" * 3

    all_pass = True

    # Test 1
    t1_pairs = [
        (normalize("EpreUVE \u00e0"), "epreuve a"),  # lang-ok
        (check_doc(D(BASE)), []),
        (check_doc([]), ["not an object"]),
        (check_doc({"limits": {}, "rules": 5}), ["rules must be a list"]),
        (check_doc(D(RULE("B", {}, {"type": "nope"}))), ["rule B: bad requirement"]),
        (check_doc(D(RULE("C", {"regex": "("}, {"type": "regex_all", "patterns": ["x"]}))), ["rule C: bad regex ("]),
        (check_doc(D(RULE("L", {}, {"type": "lines_at_most", "limit": "zzz"}))), ["rule L: unknown limit zzz"]),
        (check_doc(D(dict(BASE, fix=""))), ["rule A1: missing fix"]),
    ]
    if all(a == b for a, b in t1_pairs):
        print("PASS test1: expected %r, got %r" % ([], []))
    else:
        for a, b in t1_pairs:
            if a != b:
                print("FAIL test1: expected %r, got %r" % (b, a))
                break
        all_pass = False

    # Test 2
    t2_pairs = [
        (IDS("hello", D(BASE)), ["A1"]),
        (IDS("NATURE: creation", D(BASE)), []),
        (IDS("/SRV/me", D(T)), []),
        (IDS("/SRV/me", D(T), "untrusted_third_party"), ["T"]),
        (IDS("\u00c9preuve 3", D(W)), ["W"]),  # lang-ok
        (IDS("epreuve x", D(W)), []),  # lang-ok
        (IDS("Epreuve 3 GRANDEUR", D(W)), []),  # lang-ok
    ]
    if all(a == b for a, b in t2_pairs):
        print("PASS test2: expected %r, got %r" % ([], []))
    else:
        for a, b in t2_pairs:
            if a != b:
                print("FAIL test2: expected %r, got %r" % (b, a))
                break
        all_pass = False

    # Test 3
    t3_pairs = [
        (IDS("run --check 'x.py'", D(V)), ["V"]),
        (IDS("run --check 'python3 \"$OUT\"'", D(V)), []),
        (IDS("TESTS: 2", D(N)), []),
        (IDS("TESTS: 3", D(N)), ["N"]),
        (IDS("no count", D(N)), ["N"]),
        (IDS("a\nb\nc", D(M)), []),
        (IDS("a\nb\nc\nd", D(M)), ["M"]),
    ]
    if all(a == b for a, b in t3_pairs):
        print("PASS test3: expected %r, got %r" % ([], []))
    else:
        for a, b in t3_pairs:
            if a != b:
                print("FAIL test3: expected %r, got %r" % (b, a))
                break
        all_pass = False

    # Test 4
    t4_ok = True
    t4_pairs = [
        (IDS(FENCE + "\na\nb\n" + FENCE, D(K)), []),
        (IDS(FENCE + "\na\n" + FENCE, D(K)), ["K"]),
        (IDS(FENCE + "\na\nb\n", D(K)), ["K"]),
        (IDS("a\tb", D(Z)), ["Z"]),
        (IDS("x", D(Z, BASE, K)), ["A1", "K"]),
        (explain(BASE), "REFUSED A1 - t\n  born 2026-01-01: i\n  To fix: write nature:"),
    ]
    for a, b in t4_pairs:
        if a != b:
            t4_ok = False
            break
    if t4_ok:
        try:
            evaluate("x", {"rules": 5})
            t4_ok = False
        except ValueError:
            pass
    if t4_ok:
        print("PASS test4: expected %r, got %r" % ([], []))
    else:
        for a, b in t4_pairs:
            if a != b:
                print("FAIL test4: expected %r, got %r" % (b, a))
                break
        else:
            print("FAIL test4: expected ValueError, got no exception")
        all_pass = False

    # Test 5
    t5_ok = True
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    if proc.returncode != 0:
        t5_ok = False
    elif not proc.stdout.startswith("NAME      brief_rules.py"):
        t5_ok = False

    proc2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True
    )
    if proc2.returncode != 2:
        t5_ok = False
    elif proc2.stdout != "usage: brief_rules.py --notice | --autotest\n":
        t5_ok = False

    if t5_ok:
        print("PASS test5: expected %r, got %r" % (0, proc.returncode))
    else:
        if proc.returncode != 0:
            print("FAIL test5: expected exit 0, got %d" % proc.returncode)
        elif not proc.stdout.startswith("NAME      brief_rules.py"):
            print("FAIL test5: expected stdout starting with 'NAME      brief_rules.py', got %r" % proc.stdout[:40])
        elif proc2.returncode != 2:
            print("FAIL test5: expected exit 2, got %d" % proc2.returncode)
        else:
            print("FAIL test5: expected %r, got %r" % ("usage: brief_rules.py --notice | --autotest\n", proc2.stdout))
        all_pass = False

    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(_NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write("usage: brief_rules.py --notice | --autotest\n")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "brief_rules", sys.argv[1:])
