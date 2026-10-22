import sys
import os
import re
import subprocess

MARKER = re.compile(r"__[A-Z]+_\d+__")


# Values that documentation reserves for examples (RFC 5737 address blocks, example.com and example.net
# mailboxes, the access key printed in the vendor guides): they identify no one, so they are not hits.
DOC_VALUES = re.compile(
    r"@example\.(?:com|net)\b|\b(?:192\.0\.2|198\.51\.100|203\.0\.113)\.\d{1,3}\b|AKIAIOSFODNN7" + "EXAMPLE"
)


def find(text, anonymizable, irreducible):
    hits = []
    for i, (pattern, label, tag) in enumerate(anonymizable):
        for m in re.finditer(pattern, text, re.M):
            if m.end() == m.start() or DOC_VALUES.search(m.group()):
                continue
            line = text.count("\n", 0, m.start()) + 1
            excerpt = m.group()[:80]
            hits.append((m.start(), 0, i, (line, "anonymizable", label, excerpt)))
    for i, (pattern, label) in enumerate(irreducible):
        for m in re.finditer(pattern, text, re.M):
            if m.end() == m.start() or DOC_VALUES.search(m.group()):
                continue
            line = text.count("\n", 0, m.start()) + 1
            excerpt = m.group()[:80]
            hits.append((m.start(), 1, i, (line, "irreducible", label, excerpt)))
    hits.sort(key=lambda x: (x[0], x[1], x[2]))
    return [h[3] for h in hits]


def anonymize(text, anonymizable, irreducible, table=None):
    if table is None:
        table = {}

    forbidden = []
    for pattern, label in irreducible:
        for m in re.finditer(pattern, text, re.M):
            if m.end() > m.start():
                forbidden.append((m.start(), m.end()))

    counters = {}
    for label in table:
        if MARKER.fullmatch(label):
            inner = label[2:-2]
            last_us = inner.rfind("_")
            tag_part = inner[:last_us]
            n_str = inner[last_us + 1:]
            if n_str.isdigit():
                n = int(n_str)
                if tag_part not in counters or n > counters[tag_part]:
                    counters[tag_part] = n

    occurrences = []
    for i, (pattern, label, tag) in enumerate(anonymizable):
        for m in re.finditer(pattern, text, re.M):
            if m.end() == m.start():
                continue
            value = m.group()
            occurrences.append((m.start(), m.end(), label, tag, value))
    occurrences.sort(key=lambda x: (x[0], -(x[1] - x[0])))

    kept = []
    counts = {}
    for (start, end, label, tag, value) in occurrences:
        skip = False
        for (fs, fe) in forbidden:
            if start < fe and end > fs:
                skip = True
                break
        if skip:
            continue
        for (ks, ke, _, _) in kept:
            if start < ke and end > ks:
                skip = True
                break
        if skip:
            continue
        existing = None
        for lbl, val in table.items():
            if val == value:
                existing = lbl
                break
        if existing is not None:
            mark_label = existing
        else:
            if tag not in counters:
                counters[tag] = 0
            counters[tag] += 1
            mark_label = "__" + tag + "_" + str(counters[tag]) + "__"
            table[mark_label] = value
        kept.append((start, end, mark_label, label))
        counts[label] = counts.get(label, 0) + 1

    kept.sort(key=lambda x: x[0])
    parts = []
    pos = 0
    for (start, end, mark_label, label) in kept:
        parts.append(text[pos:start])
        parts.append(mark_label)
        pos = end
    parts.append(text[pos:])
    clean = "".join(parts)

    return (clean, counts, table)


def restore(text, table):
    for label in sorted(table.keys(), key=len, reverse=True):
        text = text.replace(label, table[label])
    return text


NOTICE = (
    "NAME      anon_core.py - finds leaks in a text, swaps the anonymizable ones for stable labels, and puts them back.\n"
    "READS     nothing: pure module; it works on the text and the pattern lists it is given.\n"
    "WRITES    nothing: find() returns the hits, anonymize() the clean text and its table, restore() the original.\n"
    "EXAMPLE   python3 anon_core.py --notice\n"
    "PITFALLS  2026-08-07 a label that looked like an e-mail was caught again after cleaning; labels now match no pattern.\n"
    "          2026-08-08 masking a secret hides the signal that it must not leave; irreducible spans are never touched."
)


def run_autotest():
    E1 = "ann" + "@example.org"
    E2 = "bob" + "@example.org"
    E0 = "zed" + "@example.org"
    A = [("[a-z]+@[a-z]+\\.org", "email address", "EMAIL"), ("\\bPlimsoq\\b", "person", "PERSON")]
    I = [("KEY=[A-Z0-9]{8,}", "key")]
    I2 = [("SECRET\\([^)]*\\)", "secret")]
    T1 = "Hello Plimsoq, write to " + E1 + "\nor " + E2 + ", " + E1 + " again. KEY=ABCD1234"
    T4 = "SECRET(" + E1 + ") and " + E2
    CLEAN1 = "Hello __PERSON_1__, write to __EMAIL_1__\nor __EMAIL_2__, __EMAIL_1__ again. KEY=ABCD1234"
    TABLE1 = {"__PERSON_1__": "Plimsoq", "__EMAIL_1__": E1, "__EMAIL_2__": E2}

    all_pass = True

    # Test 1
    expected1 = [(1, "anonymizable", "person", "Plimsoq"), (1, "anonymizable", "email address", E1), (2, "anonymizable", "email address", E2), (2, "anonymizable", "email address", E1), (2, "irreducible", "key", "KEY=ABCD1234")]
    got1 = find(T1, A, I)
    if not isinstance(got1, list):
        print("FAIL 1: expected list, got " + type(got1).__name__)
        all_pass = False
    elif got1 == expected1:
        print("PASS 1: " + repr(got1))
    else:
        print("FAIL 1: expected " + repr(expected1) + " got " + repr(got1))
        all_pass = False

    # Test 2
    expected2 = (CLEAN1, {"person": 1, "email address": 3}, TABLE1)
    got2 = anonymize(T1, A, I)
    if not (isinstance(got2, tuple) and len(got2) == 3):
        print("FAIL 2: expected tuple of 3, got " + type(got2).__name__)
        all_pass = False
    elif got2 == expected2:
        print("PASS 2: " + repr(got2))
    else:
        print("FAIL 2: expected " + repr(expected2) + " got " + repr(got2))
        all_pass = False

    # Test 3
    expected3a = T1
    got3a = restore(CLEAN1, TABLE1)
    expected3b = "Ask " + E2 + " about Plimsoq and __EMAIL_9__"
    got3b = restore("Ask __EMAIL_2__ about __PERSON_1__ and __EMAIL_9__", TABLE1)
    if not isinstance(got3a, str) or not isinstance(got3b, str):
        print("FAIL 3: expected str, got " + type(got3a).__name__ + " / " + type(got3b).__name__)
        all_pass = False
    elif got3a == expected3a and got3b == expected3b:
        print("PASS 3: " + repr(got3a) + " / " + repr(got3b))
    else:
        print("FAIL 3: expected " + repr(expected3a) + " / " + repr(expected3b) + " got " + repr(got3a) + " / " + repr(got3b))
        all_pass = False

    # Test 4
    expected4a = ("SECRET(" + E1 + ") and __EMAIL_2__", {"email address": 1}, {"__EMAIL_1__": E0, "__EMAIL_2__": E2})
    got4a = anonymize(T4, A, I2, {"__EMAIL_1__": E0})
    expected4b = [(2, "irreducible", "key", "KEY=ABCD1234")]
    got4b = find(CLEAN1, A, I)
    if not (isinstance(got4a, tuple) and len(got4a) == 3) or not isinstance(got4b, list):
        print("FAIL 4: expected tuple of 3 and list, got " + type(got4a).__name__ + " / " + type(got4b).__name__)
        all_pass = False
    elif got4a == expected4a and got4b == expected4b:
        print("PASS 4: " + repr(got4a) + " / " + repr(got4b))
    else:
        print("FAIL 4: expected " + repr(expected4a) + " / " + repr(expected4b) + " got " + repr(got4a) + " / " + repr(got4b))
        all_pass = False

    # Test 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True
    )
    if proc.returncode == 0 and proc.stdout.startswith("NAME      anon_core.py"):
        print("PASS 5: rc=" + str(proc.returncode) + " stdout starts with NAME")
    else:
        print("FAIL 5: expected rc=0 and stdout starts with 'NAME      anon_core.py', got rc=" + str(proc.returncode) + " stdout=" + repr(proc.stdout[:60]))
        all_pass = False

    if not all_pass:
        sys.exit(1)


def _cli():
    if len(sys.argv) < 2:
        print("usage: anon_core.py --notice | --autotest")
        sys.exit(2)
    elif sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        run_autotest()
        sys.exit(0)
    else:
        print("usage: anon_core.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "anon_core", sys.argv[1:])
