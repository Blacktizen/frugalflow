#!/usr/bin/env python3
"""journal_add.py - appends one sealed entry to a vault's append-only log, after checking the existing chain."""

import os
import sys
import datetime
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_rules
import page_rules

USAGE = 'usage: journal_add.py --vault DIR --title TITLE --field KEY=VALUE [--field KEY=VALUE ...] [--when "YYYY-MM-DD HH:MM"] | --notice | --autotest'

NOTICE = (
    "NAME      journal_add.py - appends one sealed entry to a vault's append-only log, after checking the existing chain.\n"
    "READS     --vault; the vault's log.md, found by name anywhere in the vault.\n"
    "WRITES    one entry at the end of log.md; a broken chain is refused, nothing written. Exit 0 appended, 2 usage, 3 no log.md, 4 chain broken.\n"
    "EXAMPLE   python3 journal_add.py --vault ~/projects/demo/vault --title \"Parser fixed\" --field \"Decision=resolve pages by name\" --field \"Why=a moved page bricked the gate\"\n"
    "PITFALLS  2026-09-06 55 minutes and 5 commits went by without one log entry, then 8 entries were dumped in 3 minutes.\n"
    "          An entry is one command, written right after the gesture; the chain shows when an older one was touched."
)


def vault_files(vault):
    """Return sorted list of relative file paths (using / separator) in vault, ignoring dot-directories."""
    files = []
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for name in filenames:
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, vault)
            files.append(rel.replace(os.sep, "/"))
    return sorted(files)


def append(vault, when, title, fields):
    """Append a sealed entry to the vault log after verifying the chain. Returns (code, message)."""
    rel, err = page_rules.resolve("log.md", vault_files(vault))
    if rel is None:
        return (3, err)
    path = os.path.join(vault, rel)
    with open(path, "r", encoding="utf-8") as f:
        text = f.read()
    ok, n, bad, reason = chain_rules.verify(text)
    if not ok:
        return (4, "REFUSED log chain broken: " + reason + ": nothing written")
    entry = chain_rules.render(chain_rules.last_hash(text), when, title, fields)
    sep = "\n" if text.endswith("\n") else "\n\n"
    with open(path, "a", encoding="utf-8") as f:
        f.write(sep + entry)
    with open(path, "r", encoding="utf-8") as f:
        new_text = f.read()
    ok2, _, _, reason2 = chain_rules.verify(new_text)
    if not ok2:
        return (4, "REFUSED log chain broken after append: " + reason2)
    return (0, "APPENDED entry " + str(n) + " to " + rel)


def _parse_args(args):
    """Parse CLI args. Returns (mode, dict) or (None, None) on usage error."""
    if args == ["--notice"]:
        return ("notice", None)
    if args == ["--autotest"]:
        return ("autotest", None)
    vault = None
    title = None
    fields = []
    when = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--vault":
            if i + 1 >= len(args):
                return (None, None)
            vault = args[i + 1]
            i += 2
        elif a == "--title":
            if i + 1 >= len(args):
                return (None, None)
            title = args[i + 1]
            i += 2
        elif a == "--field":
            if i + 1 >= len(args):
                return (None, None)
            val = args[i + 1]
            if "=" not in val:
                return (None, None)
            k, v = val.split("=", 1)
            fields.append((k, v))
            i += 2
        elif a == "--when":
            if i + 1 >= len(args):
                return (None, None)
            when = args[i + 1]
            i += 2
        else:
            return (None, None)
    if vault is None or title is None or len(fields) == 0:
        return (None, None)
    if when is None:
        when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return ("append", {"vault": vault, "title": title, "fields": fields, "when": when})


def _autotest():
    """Run 5 proofs in a tempdir. Print one PASS/FAIL line per proof. Return exit code."""
    tmp = tempfile.mkdtemp()
    results = []
    try:
        START = "# Log\n\n" + chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])

        def make(vault, rel="log.md", text=START):
            p = os.path.join(vault, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as f:
                f.write(text)
            return p

        # --- Proof 1 ---
        V1 = os.path.join(tmp, "v1")
        os.makedirs(V1, exist_ok=True)
        make(V1)
        r1a = append(V1, "2026-09-26 10:00", "fix", [("Decision", "a")])
        with open(os.path.join(V1, "log.md"), "r", encoding="utf-8") as f:
            c1 = f.read()
        v1 = chain_rules.verify(c1)
        r1b = append(V1, "2026-09-26 10:00", "fix2", [("Decision", "a")])
        exp1 = (r1a == (0, "APPENDED entry 1 to log.md") and v1 == (True, 2, None, "") and r1b == (0, "APPENDED entry 2 to log.md"))
        results.append((1, exp1, (r1a, v1, r1b)))

        # --- Proof 2 ---
        V2 = os.path.join(tmp, "v2")
        os.makedirs(V2, exist_ok=True)
        make(V2, rel="05-reference/log.md")
        r2a = append(V2, "2026-09-26 10:00", "fix", [("Decision", "a")])
        V2b = os.path.join(tmp, "v2b")
        os.makedirs(V2b, exist_ok=True)
        r2b = append(V2b, "x", "t", [("a", "b")])
        exp2 = (r2a == (0, "APPENDED entry 1 to 05-reference/log.md") and r2b == (3, "missing page: log.md"))
        results.append((2, exp2, (r2a, r2b)))

        # --- Proof 3 ---
        V3 = os.path.join(tmp, "v3")
        os.makedirs(V3, exist_ok=True)
        broken = START.replace("created", "CREATED")
        make(V3, text=broken)
        r3 = append(V3, "2026-09-26 10:00", "fix", [("Decision", "a")])
        with open(os.path.join(V3, "log.md"), "r", encoding="utf-8") as f:
            c3 = f.read()
        exp3 = (r3 == (4, "REFUSED log chain broken: entry 0 was rewritten: nothing written") and c3 == broken)
        results.append((3, exp3, (r3, c3 == broken)))

        # --- Proof 4 ---
        V4 = os.path.join(tmp, "v4")
        os.makedirs(V4, exist_ok=True)
        make(V4)
        p4 = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vault", V4, "--title", "t", "--field", "Decision=b=c", "--when", "2026-09-26 11:00"],
            capture_output=True, text=True
        )
        with open(os.path.join(V4, "log.md"), "r", encoding="utf-8") as f:
            c4 = f.read()
        exp4a = (p4.returncode == 0 and p4.stdout == "APPENDED entry 1 to log.md\n" and "Decision: b=c" in c4)
        V4b = os.path.join(tmp, "v4b")
        os.makedirs(V4b, exist_ok=True)
        make(V4b, text=START.replace("created", "CREATED"))
        p4b = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vault", V4b, "--title", "t", "--field", "Decision=b=c", "--when", "2026-09-26 11:00"],
            capture_output=True, text=True
        )
        exp4 = exp4a and p4b.returncode == 4
        results.append((4, exp4, (p4.returncode, p4.stdout.strip(), p4b.returncode)))

        # --- Proof 5 ---
        p5a = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--notice"],
            capture_output=True, text=True
        )
        p5b = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True
        )
        V5 = os.path.join(tmp, "v5")
        os.makedirs(V5, exist_ok=True)
        p5c = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vault", V5, "--title", "t"],
            capture_output=True, text=True
        )
        p5d = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vault", V5, "--title", "t", "--field", "nokey"],
            capture_output=True, text=True
        )
        V5b = os.path.join(tmp, "v5b")
        os.makedirs(V5b, exist_ok=True)
        p5e = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--vault", V5b, "--title", "t", "--field", "Decision=a"],
            capture_output=True, text=True
        )
        exp5 = (
            p5a.returncode == 0 and p5a.stdout.startswith("NAME      journal_add.py")
            and p5b.returncode == 2 and p5b.stdout == USAGE + "\n"
            and p5c.returncode == 2
            and p5d.returncode == 2
            and p5e.returncode == 3
        )
        results.append((5, exp5, (p5a.returncode, p5b.returncode, p5c.returncode, p5d.returncode, p5e.returncode)))
    finally:
        shutil.rmtree(tmp)

    all_pass = True
    for num, passed, got in results:
        if passed:
            print("PASS {} got={}".format(num, got))
        else:
            print("FAIL {} expected=all-matches got={}".format(num, got))
            all_pass = False
    return 0 if all_pass else 1


def main():
    mode, kw = _parse_args(sys.argv[1:])
    if mode is None:
        print(USAGE)
        sys.exit(2)
    if mode == "notice":
        print(NOTICE)
        sys.exit(0)
    if mode == "autotest":
        sys.exit(_autotest())
    code, msg = append(kw["vault"], kw["when"], kw["title"], kw["fields"])
    print(msg)
    sys.exit(code)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "journal_add", sys.argv[1:])
