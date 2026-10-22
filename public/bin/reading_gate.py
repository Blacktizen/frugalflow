#!/usr/bin/env python3
import os
import sys
import re
import json
import datetime
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import page_rules

ATTEST = ".reading.json"

USAGE = "usage: reading_gate.py --vault DIR (--show | --attest FILE | --status) | --notice | --autotest"

NOTICE = (
    "NAME      reading_gate.py - the vault's reading gate: shows the bearing lines of the required pages, attests a reading only when a restatement repeats every one of them.\n"
    "READS     --vault: the REQUIRED-READING block of SCHEMA.md at the vault root and the pages it names, found by name anywhere in the vault except raw/; --attest: the restatement file.\n"
    "WRITES    <vault>/.reading.json on a full restatement only. Exit 0 ok, 2 usage, 3 page missing or ambiguous, 4 lines missing, 5 unread or stale.\n"
    "EXAMPLE   python3 reading_gate.py --vault ~/projects/demo/vault --attest restatement.txt\n"
    "PITFALLS  2026-09-22 moving a page into a subfolder made the old gate refuse every write, its own repair included.\n"
    "          Pages are resolved by name; a moved page keeps the same fingerprint, so the attestation stays valid.\n"
)


def vault_files(vault):
    """Walk vault, skip dot-directories, return sorted relative paths with / separator."""
    result = []
    for dirpath, dirs, filenames in os.walk(vault):
        dirs[:] = [d for d in dirs if not d.startswith(".")]
        for f in filenames:
            full = os.path.join(dirpath, f)
            rel = os.path.relpath(full, vault)
            result.append(rel.replace(os.sep, "/"))
    return sorted(result)


def load(vault):
    """Load required pages from vault. Returns (pages, errors)."""
    files = vault_files(vault)
    schema_text = None
    if "SCHEMA.md" in files:
        with open(os.path.join(vault, "SCHEMA.md"), "r", encoding="utf-8") as fh:
            schema_text = fh.read()
    paths, errors = page_rules.required_pages(schema_text, files)
    pages = []
    for p in paths:
        with open(os.path.join(vault, p), "r", encoding="utf-8") as fh:
            pages.append((p, fh.read()))
    return pages, errors


def normalize(line):
    """Strip and collapse internal whitespace to single spaces."""
    return re.sub(r"[ \t]+", " ", line.strip())


def missing_lines(pages, restitution):
    """Return bearing lines absent from the restatement, in page order."""
    given = set(normalize(l) for l in restitution.split("\n"))
    result = []
    for _p, text in pages:
        for line in page_rules.bearing_lines(text):
            if normalize(line) not in given:
                result.append(line)
    return result


def status(vault, pages):
    """Check attestation state. Returns (exit_code, message)."""
    a = os.path.join(vault, ATTEST)
    if not os.path.exists(a):
        return (5, "UNREAD no attestation for this vault")
    try:
        with open(a, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return (5, "UNREAD attestation unreadable")
    if data.get("fingerprint") == page_rules.fingerprint(pages):
        return (0, "READ attestation matches the pages")
    return (5, "STALE pages changed since the attestation")


def _run_autotest():
    """Execute five proofs as subprocess invocations and report PASS/FAIL."""
    script = os.path.abspath(__file__)
    all_pass = True

    SCHEMA = "# S\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n"
    OVERVIEW = "# O\n\u26d4\u26d4 never push to main\nplain\n"
    TODO = "# T\n- [ ] \u2b50\u2b50 fix the parser\n"
    FULL = "\u26d4\u26d4 never push to main\n- [ ] \u2b50\u2b50 fix the parser\n"
    HALF = "\u26d4\u26d4 never push to main\n"

    def make(v, overview_rel="overview.md"):
        for rel, text in (("SCHEMA.md", SCHEMA), (overview_rel, OVERVIEW), ("todo.md", TODO)):
            p = os.path.join(v, rel)
            os.makedirs(os.path.dirname(p), exist_ok=True)
            with open(p, "w", encoding="utf-8") as fh:
                fh.write(text)

    def run(*args):
        r = subprocess.run([sys.executable, script] + list(args), capture_output=True, text=True)
        return r.returncode, r.stdout

    # Proof 1: --show
    V = tempfile.mkdtemp()
    try:
        make(V)
        code, out = run("--vault", V, "--show")
        lines = out.split("\n")
        ok = code == 0 and len(lines) >= 5
        if ok:
            if not lines[0].startswith("PAGE overview.md"):
                ok = False
            if not lines[1].startswith("\u26d4\u26d4 never push to main"):
                ok = False
            if not lines[2].startswith("PAGE todo.md"):
                ok = False
            if not lines[3].startswith("- [ ] \u2b50\u2b50 fix the parser"):
                ok = False
            if not lines[4].startswith("FINGERPRINT "):
                ok = False
            else:
                hex_part = lines[4][len("FINGERPRINT "):]
                if len(hex_part) != 64:
                    ok = False
        if ok:
            print("PASS proof 1: --show exit 0, correct PAGE lines and 64-char FINGERPRINT")
        else:
            print("FAIL proof 1: expected code 0 with PAGE/FINGERPRINT lines, got code {} out {!r}".format(code, out))
            all_pass = False
    finally:
        shutil.rmtree(V, ignore_errors=True)

    # Proof 2: --attest with HALF (incomplete restatement)
    V = tempfile.mkdtemp()
    F = os.path.join(V, "rest.txt")
    try:
        make(V)
        with open(F, "w", encoding="utf-8") as fh:
            fh.write(HALF)
        code, out = run("--vault", V, "--attest", F)
        expected_out = "MISSING - [ ] \u2b50\u2b50 fix the parser\nNOT ATTESTED 1 of 2 bearing lines missing\n"
        attest_path = os.path.join(V, ATTEST)
        ok = code == 4 and out == expected_out and not os.path.exists(attest_path)
        if ok:
            code2, out2 = run("--vault", V, "--status")
            ok = code2 == 5 and out2 == "UNREAD no attestation for this vault\n"
        if ok:
            print("PASS proof 2: --attest HALF exit 4, no .reading.json, --status UNREAD")
        else:
            print("FAIL proof 2: expected (4, {!r}), got ({}, {!r})".format(expected_out, code, out))
            all_pass = False
    finally:
        shutil.rmtree(V, ignore_errors=True)

    # Proof 3: --attest with FULL then modify page to trigger STALE
    V = tempfile.mkdtemp()
    F = os.path.join(V, "rest.txt")
    try:
        make(V)
        with open(F, "w", encoding="utf-8") as fh:
            fh.write(FULL)
        code, out = run("--vault", V, "--attest", F)
        ok = code == 0 and out == "ATTESTED 2 bearing lines\n"
        if ok:
            ok = os.path.exists(os.path.join(V, ATTEST))
        if ok:
            code2, out2 = run("--vault", V, "--status")
            ok = code2 == 0 and out2 == "READ attestation matches the pages\n"
        if ok:
            with open(os.path.join(V, "todo.md"), "a", encoding="utf-8") as fh:
                fh.write("\u26d4 new rule\n")
            code3, out3 = run("--vault", V, "--status")
            ok = code3 == 5 and out3 == "STALE pages changed since the attestation\n"
        if ok:
            print("PASS proof 3: --attest FULL exit 0, .reading.json written, status READ then STALE")
        else:
            print("FAIL proof 3: expected full-attestation flow, got unexpected result")
            all_pass = False
    finally:
        shutil.rmtree(V, ignore_errors=True)

    # Proof 4: move page to subfolder keeps attestation valid; duplicate causes ambiguity
    V = tempfile.mkdtemp()
    F = os.path.join(V, "rest.txt")
    try:
        make(V)
        with open(F, "w", encoding="utf-8") as fh:
            fh.write(FULL)
        run("--vault", V, "--attest", F)
        os.makedirs(os.path.join(V, "01-context"), exist_ok=True)
        os.rename(os.path.join(V, "overview.md"), os.path.join(V, "01-context", "overview.md"))
        code, out = run("--vault", V, "--status")
        ok = code == 0 and out == "READ attestation matches the pages\n"
        if ok:
            code2, out2 = run("--vault", V, "--show")
            ok = code2 == 0 and "PAGE 01-context/overview.md" in out2
        if ok:
            with open(os.path.join(V, "overview.md"), "w", encoding="utf-8") as fh:
                fh.write(OVERVIEW)
            code3, out3 = run("--vault", V, "--status")
            ok = code3 == 3 and out3.startswith("ERROR ambiguous page: overview.md")
        if ok:
            print("PASS proof 4: moved page keeps valid attestation; duplicate triggers ambiguous error")
        else:
            print("FAIL proof 4: expected valid-after-move and ambiguous-after-duplicate, got unexpected")
            all_pass = False
    finally:
        shutil.rmtree(V, ignore_errors=True)

    # Proof 5: --notice, no args, bad vault, empty vault
    V = tempfile.mkdtemp()
    try:
        code, out = run("--notice")
        ok = code == 0 and out.startswith("NAME      reading_gate.py")
        if ok:
            code2, out2 = run()
            ok = code2 == 2 and out2 == USAGE + "\n"
        if ok:
            code3, out3 = run("--vault", "/nonexistent-dir-xyz", "--show")
            ok = code3 == 2
        if ok:
            code4, out4 = run("--vault", V, "--status")
            ok = code4 == 3 and out4 == "ERROR missing page: overview.md\nERROR missing page: todo.md\n"
        if ok:
            print("PASS proof 5: --notice, no-args usage, bad vault, empty vault all correct")
        else:
            print("FAIL proof 5: expected notice/usage/bad-vault/empty-vault, got unexpected")
            all_pass = False
    finally:
        shutil.rmtree(V, ignore_errors=True)

    sys.exit(0 if all_pass else 1)


def main():
    args = sys.argv[1:]

    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        sys.exit(0)

    if args == ["--autotest"]:
        _run_autotest()
        return

    vault = None
    mode = None
    attest_file = None
    i = 0
    while i < len(args):
        if args[i] == "--vault":
            i += 1
            if i >= len(args):
                sys.stdout.write(USAGE + "\n")
                sys.exit(2)
            vault = args[i]
        elif args[i] == "--show":
            mode = "show"
        elif args[i] == "--attest":
            i += 1
            if i >= len(args):
                sys.stdout.write(USAGE + "\n")
                sys.exit(2)
            attest_file = args[i]
            mode = "attest"
        elif args[i] == "--status":
            mode = "status"
        else:
            sys.stdout.write(USAGE + "\n")
            sys.exit(2)
        i += 1

    if vault is None or mode is None:
        sys.stdout.write(USAGE + "\n")
        sys.exit(2)

    if not os.path.isdir(vault):
        sys.stdout.write(USAGE + "\n")
        sys.exit(2)

    if mode == "attest" and not os.path.isfile(attest_file):
        sys.stdout.write(USAGE + "\n")
        sys.exit(2)

    pages, errors = load(vault)
    if errors:
        for e in errors:
            sys.stdout.write("ERROR " + e + "\n")
        sys.exit(3)

    if mode == "show":
        for p, text in pages:
            sys.stdout.write("PAGE " + p + "\n")
            for line in page_rules.bearing_lines(text):
                sys.stdout.write(line + "\n")
        sys.stdout.write("FINGERPRINT " + page_rules.fingerprint(pages) + "\n")
        sys.exit(0)

    if mode == "attest":
        with open(attest_file, "r", encoding="utf-8") as fh:
            restitution = fh.read()
        total = sum(len(page_rules.bearing_lines(t)) for _p, t in pages)
        missing = missing_lines(pages, restitution)
        if missing:
            for l in missing:
                sys.stdout.write("MISSING " + l + "\n")
            sys.stdout.write("NOT ATTESTED " + str(len(missing)) + " of " + str(total) + " bearing lines missing\n")
            sys.exit(4)
        fp = page_rules.fingerprint(pages)
        payload = {
            "fingerprint": fp,
            "time": datetime.datetime.now().isoformat(timespec="seconds"),
            "lines": total,
        }
        with open(os.path.join(vault, ATTEST), "w", encoding="utf-8") as fh:
            fh.write(json.dumps(payload))
        sys.stdout.write("ATTESTED " + str(total) + " bearing lines\n")
        sys.exit(0)

    if mode == "status":
        code, message = status(vault, pages)
        sys.stdout.write(message + "\n")
        sys.exit(code)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "reading_gate", sys.argv[1:])
