import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anon_rules
import anon_core
import scan_files

PUBLIC_FILE = ".frugalflow-public"
_MIN_PUBLIC_LEN = 8

NOTICE = (
    "NAME      scan_cmd.py - the frugalflow scan subcommand: looks for secrets and private data in a folder or a git repo, with no model.\n"
    "READS     the folder or file given; the rules file given by --rules, else FRUGALFLOW_HOME/anonymization.json, else ~/.frugalflow/anonymization.json, else the built-in rules; " + PUBLIC_FILE + " at the scanned folder root (the git root with --staged); with --staged, the git index.\n"
    "WRITES    nothing: one line per leak with file, line, type and label, never the text found. Exit 0 clean, 12 leak found, 2 bad usage or path, 13 bad rules.\n"
    "EXAMPLE   python3 scan_cmd.py ./my-project\n"
    "PITFALLS  2026-10-25 printing the text found would copy the leak into CI logs; only its place, type and label are printed.\n"
    "          2026-10-25 a scan that finds no file used to print CLEAN; a path with nothing to read still says 0 files, so an empty scan is visible.\n"
    "          2026-11-13 the repository URL contains the owner handle, which users list as private; a literal public value now sets aside only its own occurrences."
)

USAGE = "usage: scan_cmd.py [PATH] [--staged] [--quiet] [--rules FILE] | --notice | --autotest"

KEY_LINE = "api" + "_key = " + chr(34) + "abcd1234efgh5678ijkl" + chr(34) + "\n"
CLEAN_LINE = "def add(a, b):\n    return a + b\n"
PRIVATE_RULES = {"anonymizable": [{"pattern": "\\bPlimsoq\\b", "label": "person", "tag": "PERSON"}]}
PRIVATE_LINE = "hello Plimsoq\n"


def _load_rules_file(path):
    if not os.path.isfile(path):
        print("NO RULES FILE " + path)
        return None, 13
    try:
        with open(path, encoding="utf-8") as fh:
            doc = json.load(fh)
    except (json.JSONDecodeError, UnicodeDecodeError):
        print("NO RULES " + path + ": not valid JSON")
        return None, 13
    return doc, 0


def _git_root(path):
    env = {k: v for k, v in os.environ.items() if not k.startswith("GIT_")}
    try:
        proc = subprocess.run(
            ["git", "-C", path, "rev-parse", "--show-toplevel"],
            capture_output=True,
            env=env,
            timeout=60,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    if proc.returncode != 0:
        return None
    root = proc.stdout.strip().decode("utf-8", errors="surrogateescape")
    return root or None


def _load_public_values(root):
    # One literal value per line; blank lines and lines starting with # are comments.
    # Returns (values, path): the path is set even when every value was too short.
    if not root:
        return [], None
    p = os.path.join(root, PUBLIC_FILE)
    if not os.path.isfile(p):
        return [], None
    try:
        with open(p, encoding="utf-8", errors="replace") as fh:
            text = fh.read()
    except OSError:
        return [], None
    values = []
    for raw in text.splitlines():
        v = raw.strip()
        if not v or v.startswith("#"):
            continue
        if len(v) < _MIN_PUBLIC_LEN:
            print("public value too short, ignored: " + v, file=sys.stderr)
            continue
        values.append(v)
    return values, os.path.abspath(p)


def _match_spans(text, anonymizable, irreducible):
    # Same iteration and order as anon_core.find, but keeping each match's span,
    # so the two lists can be paired one to one.
    spans = []
    for i, (pattern, _label, _tag) in enumerate(anonymizable):
        for m in re.finditer(pattern, text, re.M):
            if m.end() == m.start() or anon_core.DOC_VALUES.search(m.group()):
                continue
            spans.append((m.start(), 0, i, m.start(), m.end()))
    for i, (pattern, _label) in enumerate(irreducible):
        for m in re.finditer(pattern, text, re.M):
            if m.end() == m.start() or anon_core.DOC_VALUES.search(m.group()):
                continue
            spans.append((m.start(), 1, i, m.start(), m.end()))
    spans.sort(key=lambda x: (x[0], x[1], x[2]))
    return [(s, e) for (_k, _i, _j, s, e) in spans]


def _line_starts(text):
    starts = [0]
    idx = text.find("\n")
    while idx != -1:
        starts.append(idx + 1)
        idx = text.find("\n", idx + 1)
    return starts


def _public_occurrences(line, public_values):
    occ = []
    for v in public_values:
        start = 0
        while True:
            i = line.find(v, start)
            if i < 0:
                break
            occ.append((i, i + len(v)))
            start = i + 1
    return occ


def _set_aside_public(text, hits, anonymizable, irreducible, public_values):
    # A hit is set aside only when its whole span sits inside one occurrence of a
    # public value on the same line; the same word elsewhere on the line stays a leak.
    spans = _match_spans(text, anonymizable, irreducible)
    if len(spans) != len(hits):
        return hits, 0
    starts = _line_starts(text)
    occ_cache = {}
    kept = []
    aside = 0
    for hit, (ms, me) in zip(hits, spans):
        line_no = hit[0]
        line_start = starts[line_no - 1]
        if line_no not in occ_cache:
            line_end = starts[line_no] if line_no < len(starts) else len(text)
            occ_cache[line_no] = _public_occurrences(text[line_start:line_end], public_values)
        if any(os_ <= ms - line_start and me - line_start <= oe for os_, oe in occ_cache[line_no]):
            aside += 1
        else:
            kept.append(hit)
    return kept, aside


def main(argv):
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()

    path = None
    staged = False
    quiet = False
    rules_file = None
    positional = []
    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--staged":
            staged = True
            i += 1
        elif arg == "--quiet":
            quiet = True
            i += 1
        elif arg == "--rules":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            rules_file = argv[i + 1]
            i += 2
        elif arg.startswith("--"):
            print(USAGE)
            return 2
        else:
            positional.append(arg)
            i += 1

    if len(positional) > 1:
        print(USAGE)
        return 2
    path = positional[0] if positional else "."

    # 1. Rules
    if rules_file is not None:
        doc, code = _load_rules_file(rules_file)
        if code != 0:
            return code
    else:
        home = os.environ.get("FRUGALFLOW_HOME", "")
        if not home:
            home = os.path.expanduser("~/.frugalflow")
        candidate = os.path.join(home, "anonymization.json")
        if os.path.isfile(candidate):
            doc, code = _load_rules_file(candidate)
            if code != 0:
                return code
        else:
            doc = {}

    anonymizable, irreducible, errors = anon_rules.load(doc)
    if errors:
        for err in errors:
            print("NO RULES " + err)
        return 13

    # 2. Files
    try:
        files = scan_files.list_files(path, staged=staged)
    except ValueError as exc:
        print("NO PATH " + str(exc))
        return 2

    # 2b. Declared public values: .frugalflow-public at the scanned folder root,
    # the git root with --staged. The declaration file itself is not scanned.
    if staged:
        public_root = _git_root(os.path.abspath(path))
    elif os.path.isdir(path):
        public_root = os.path.abspath(path)
    else:
        public_root = os.path.dirname(os.path.abspath(path))
    public_values, public_file = _load_public_values(public_root)
    if public_file is not None:
        files = [f for f in files if os.path.abspath(f) != public_file]

    # 3. Analysis
    is_dir = os.path.isdir(path)
    n_files = len(files)
    all_findings = []
    file_with_leak = 0
    aside = 0
    for fpath in files:
        try:
            with open(fpath, encoding="utf-8", errors="replace") as fh:
                text = fh.read()
        except OSError:
            continue
        hits = anon_core.find(text, anonymizable, irreducible)
        if hits and public_values:
            hits, n_aside = _set_aside_public(text, hits, anonymizable, irreducible, public_values)
            aside += n_aside
        if hits:
            file_with_leak += 1
        for line, kind, label, _excerpt in hits:
            all_findings.append((fpath, line, kind, label))

    # 4. Report
    h = len(all_findings)
    aside_note = ""
    if aside > 0:
        aside_note = " (" + str(aside) + " public value match(es) set aside by " + PUBLIC_FILE + ")"
    if not quiet:
        for fpath, line, kind, label in all_findings:
            if is_dir:
                rel = os.path.relpath(os.path.realpath(fpath), os.path.realpath(path))
            else:
                rel = path
            typ = "secret" if kind == "irreducible" else "private data"
            shown = label if label.lower().startswith(typ) else typ + " " + label
            print(rel + ":" + str(line) + ": " + shown)

    # 5. Summary and code
    if h == 0:
        print("CLEAN: " + str(n_files) + " file(s) scanned, no leak found" + aside_note)
        return 0
    print("FOUND " + str(h) + " leak(s) in " + str(file_with_leak) + " file(s)" + aside_note)
    if not quiet:
        print("Fix: remove the value and load it from an environment variable, then scan again.")
        print("False positive? Keep that file out of the scanned folder, list it in .gitignore, or declare the exact public value in " + PUBLIC_FILE + ".")
    return 12


def _autotest():
    tmp = tempfile.mkdtemp()
    try:
        leaky = os.path.join(tmp, "leaky")
        os.mkdir(leaky)
        with open(os.path.join(leaky, "leak.py"), "w", encoding="utf-8") as f:
            f.write(KEY_LINE)

        clean = os.path.join(tmp, "clean")
        os.mkdir(clean)
        with open(os.path.join(clean, "ok.py"), "w", encoding="utf-8") as f:
            f.write(CLEAN_LINE)

        priv = os.path.join(tmp, "priv")
        os.mkdir(priv)
        with open(os.path.join(priv, "p.txt"), "w", encoding="utf-8") as f:
            f.write(PRIVATE_LINE)

        rules_path = os.path.join(tmp, "rules.json")
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write("[]")

        private_rules_path = os.path.join(tmp, "private_rules.json")
        with open(private_rules_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(PRIVATE_RULES))

        env = os.environ.copy()
        env["HOME"] = tmp
        env["USERPROFILE"] = tmp
        env.pop("FRUGALFLOW_HOME", None)
        for key in list(env.keys()):
            if key.startswith("GIT_"):
                del env[key]

        def run(args):
            proc = subprocess.run(
                [sys.executable, os.path.abspath(__file__)] + args,
                capture_output=True,
                text=True,
                timeout=300,
                env=env,
            )
            return proc.returncode, proc.stdout + proc.stderr

        passed = 0
        self_path = os.path.abspath(__file__)

        # Test 1: leaky dir
        rc, out = run([leaky])
        ok = (rc == 12
              and "leak.py:1:" in out
              and "secret credential in clear" in out
              and "FOUND 1 leak(s) in 1 file(s)" in out
              and "abcd1234efgh5678ijkl" not in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 1: exit 12 + leak.py:1: + FOUND 1",
              "got rc=" + str(rc))

        # Test 2: clean dir
        rc, out = run([clean])
        ok = (rc == 0
              and "CLEAN: 1 file(s) scanned, no leak found" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 2: exit 0 + CLEAN: 1 file(s)",
              "got rc=" + str(rc))

        # Test 3: missing path
        rc, out = run([os.path.join(tmp, "nonexistent")])
        ok = (rc == 2 and "NO PATH " in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 3: exit 2 + NO PATH",
              "got rc=" + str(rc))

        # Test 4: bad rules file + unknown option
        rc1, out1 = run(["--rules", rules_path, clean])
        rc2, out2 = run(["--bogus"])
        ok = (rc1 == 13 and rc2 == 2 and "usage: scan_cmd.py" in out2)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 4: exit 13 + exit 2 + usage",
              "got rc1=" + str(rc1) + " rc2=" + str(rc2))

        # Test 5: private rules
        rc, out = run(["--rules", private_rules_path, priv])
        ok = (rc == 12
              and "p.txt:1: private data person" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 5: exit 12 + private data person",
              "got rc=" + str(rc))

        # Tests 6-8: declared public values (.frugalflow-public)
        pub_url = "github.com/Plimsoq/tool"

        pub1 = os.path.join(tmp, "pub1")
        os.mkdir(pub1)
        with open(os.path.join(pub1, "notes.md"), "w", encoding="utf-8") as f:
            f.write("Install from " + pub_url + "\n")
        with open(os.path.join(pub1, PUBLIC_FILE), "w", encoding="utf-8") as f:
            f.write("# comment line\n\n" + pub_url + "\n")

        pub2 = os.path.join(tmp, "pub2")
        os.mkdir(pub2)
        with open(os.path.join(pub2, "notes.md"), "w", encoding="utf-8") as f:
            f.write("Install from " + pub_url + "\nAsk Plimsoq for help\n")
        with open(os.path.join(pub2, PUBLIC_FILE), "w", encoding="utf-8") as f:
            f.write(pub_url + "\n")

        pub3 = os.path.join(tmp, "pub3")
        os.mkdir(pub3)
        with open(os.path.join(pub3, "notes.md"), "w", encoding="utf-8") as f:
            f.write("Install from " + pub_url + "\n")
        with open(os.path.join(pub3, PUBLIC_FILE), "w", encoding="utf-8") as f:
            f.write("Plimsoq\n")

        # Test 6: the URL line is set aside, the scan is clean
        rc, out = run(["--rules", private_rules_path, pub1])
        ok = (rc == 0
              and "notes.md:" not in out
              and "1 public value match" in out
              and "CLEAN: 1 file(s) scanned, no leak found" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 6: public value sets aside its occurrence + exit 0",
              "got rc=" + str(rc))

        # Test 7: the same handle elsewhere stays a leak
        rc, out = run(["--rules", private_rules_path, pub2])
        leak_lines = [l for l in out.splitlines() if "notes.md:" in l]
        ok = (rc == 12
              and len(leak_lines) == 1
              and leak_lines[0].startswith("notes.md:2:")
              and "1 public value match" in out
              and "FOUND 1 leak(s) in 1 file(s)" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 7: handle outside the public value stays a leak",
              "got rc=" + str(rc))

        # Test 8: a value shorter than 8 characters is ignored, with a warning
        rc, out = run(["--rules", private_rules_path, pub3])
        ok = (rc == 12
              and "notes.md:1:" in out
              and "public value too short, ignored: Plimsoq" in out)
        if ok:
            passed += 1
        print("PASS" if ok else "FAIL",
              "test 8: short public value ignored + warning",
              "got rc=" + str(rc))

        print("AUTOTEST " + str(passed) + "/8")
        return 0 if passed == 8 else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
