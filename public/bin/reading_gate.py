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
import journal_guard

ATTEST = ".reading.json"

USAGE = "usage: reading_gate.py --vault DIR (--show | --attest FILE | --status) | --notice | --autotest"

NOTICE = (
    "NAME      reading_gate.py - the vault's reading gate: shows the bearing lines of the required pages, attests a reading only when a restatement repeats every one of them, and, run as a check of the guard hook, refuses the first write into a vault that asks for a reading.\n"
    "READS     --vault: the REQUIRED-READING block of SCHEMA.md at the vault root and the pages it names, found by name anywhere in the vault except raw/; --attest: the restatement file.\n"
    "WRITES    <vault>/.reading.json: on a full restatement, or by the guard hook's check at the moment it refuses the first write. Never by hand. Exit 0 ok, 2 usage, 3 page missing or ambiguous, 4 lines missing, 5 unread or stale.\n"
    "EXAMPLE   python3 reading_gate.py --vault ~/projects/demo/vault --attest restatement.txt\n"
    "PITFALLS  2026-09-22 moving a page into a subfolder made the old gate refuse every write, its own repair included.\n"
    "          Pages are resolved by name; a moved page keeps the same fingerprint, so the attestation stays valid.\n"
    "          2026-11-05 the gate only spoke when it was asked, so a write into a gated vault passed untouched.\n"
    "          check() now runs inside the guard hook: it refuses once, shows the bearing lines, and attests that refusal itself, so the identical write right after passes without a new restitution.\n"
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


# --- the gate as a check of the guard hook (guard_checks.build runs check()) ---

HAND_WRITE = (
    "Reading gate refused: " + ATTEST + " is the gate's own file. "
    "To fix: never write this file by hand; the gate writes it itself, at the moment it refuses the first write into the vault."
)


def absolute(path, cwd):
    """Expand a written path, make it absolute, resolve it - the same way journal_guard does."""
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(cwd, p)
    return os.path.realpath(p)


def gated_dir(directory):
    """The vault a folder belongs to: itself, or the nearest ancestor whose SCHEMA.md names required pages."""
    d = os.path.realpath(directory)
    while True:
        schema = os.path.join(d, "SCHEMA.md")
        if os.path.isfile(schema):
            try:
                with open(schema, "r", encoding="utf-8") as fh:
                    text = fh.read()
            except OSError:
                return None
            # a block that names no page is not a gate: page_rules would fall back to its default pages.
            if page_rules.schema_pages(text) is not None:
                return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def gated_vault(path, cwd):
    """The vault a written path falls into, or None when no SCHEMA.md there asks for a reading."""
    return gated_dir(os.path.dirname(absolute(path, cwd)))


def attest_refusal(vault, pages):
    """Write the attestation of this refusal: the same fingerprint --status reads."""
    total = sum(len(page_rules.bearing_lines(t)) for _p, t in pages)
    payload = {
        "fingerprint": page_rules.fingerprint(pages),
        "time": datetime.datetime.now().isoformat(timespec="seconds"),
        "lines": total,
        "attestation": "hook",
    }
    with open(os.path.join(vault, ATTEST), "w", encoding="utf-8") as fh:
        fh.write(json.dumps(payload))
    return total


def refusal_text(vault, pages):
    """What the gate answers a first write: the lines to read, then the gesture to repeat."""
    out = ["Reading gate: " + vault + " asks for a reading before any write."]
    for p, text in pages:
        out.append("PAGE " + p)
        for line in page_rules.bearing_lines(text):
            out.append(line)
    out.append(
        "Read them, then make the write again. To fix: repeat this exact write; "
        "the gate attested this refusal itself, so the next one is accepted without a new restitution."
    )
    return "\n".join(out)


def write_path(tool_name, tool_input):
    """The file a write tool names, or None for any other tool."""
    if tool_name in ("Write", "Edit", "MultiEdit"):
        p = tool_input.get("file_path")
    elif tool_name == "NotebookEdit":
        p = tool_input.get("notebook_path")
    else:
        return None
    return p if isinstance(p, str) and p else None


def named_dirs(command, cwd):
    """Folders a shell command names beside the attestation file, so a vault reached by an absolute path is found too."""
    result = []
    for word in re.split(r"[\s'\"`;|&()<>]+", command):
        word = re.sub(r"^[0-9]*[<>]+", "", word)  # > path, 2> path
        if ATTEST not in word:
            continue
        d = os.path.dirname(absolute(word, cwd))
        if d not in result:
            result.append(d)
    return result


def bash_attestations(tool_input, cwd):
    """Attestation files a shell command writes inside a vault that asks for a reading."""
    command = tool_input.get("command")
    if not isinstance(command, str) or ATTEST not in command:
        return []
    vaults = []
    for d in [cwd] + named_dirs(command, cwd):
        vault = gated_dir(d)
        if vault is not None and vault not in vaults:
            vaults.append(vault)
    result = []
    for vault in vaults:
        attest = os.path.join(vault, ATTEST)
        # journal_guard answers for the whole command: redirections, tee, sed -i, inline code, cd tracking.
        for touched in journal_guard.touched("Bash", tool_input, [attest], cwd):
            if journal_guard.same_path(absolute(touched, cwd), absolute(attest, cwd)):
                result.append(attest)
                break
    return result


def _attest_rendered(vault, pages, ctx):
    """Attest a refusal only when the guard really renders it (mode active).

    In observe mode the refusal becomes an allow: no restitution reaches the
    assistant, so attesting it would let the next write pass without a reading."""
    if isinstance(ctx, dict) and ctx.get("mode") == "active":
        attest_refusal(vault, pages)


def check(tool_name, tool_input, config, ctx):
    """Refuse the first write into a gated vault and attest it; refuse any hand-write of the attestation."""
    cwd = ctx.get("cwd") if isinstance(ctx, dict) else None
    if not (isinstance(cwd, str) and cwd):
        cwd = os.getcwd()

    path = write_path(tool_name, tool_input)
    if path is not None:
        vault = gated_vault(path, cwd)
        if vault is None:
            return (False, "", [])
        attest = os.path.join(vault, ATTEST)
        if journal_guard.same_path(absolute(path, cwd), absolute(attest, cwd)):
            return (True, HAND_WRITE, [attest])
        pages, errors = load(vault)
        if errors:
            return (
                True,
                "Reading gate refused: " + vault + " cannot read its required pages (" + "; ".join(errors) + "). "
                "To fix: repair SCHEMA.md and the pages it names; nothing is written into this vault while they are broken.",
                [path],
            )
        code, _message = status(vault, pages)
        if code == 0:
            return (False, "", [])
        _attest_rendered(vault, pages, ctx)
        return (True, refusal_text(vault, pages), [path])

    if tool_name == "Bash":
        touched = bash_attestations(tool_input, cwd)
        if touched:
            return (True, HAND_WRITE, touched)
        # a Bash write into a gated vault is judged like a Write: every write
        # target of the call is looked at, in order; a write outside a vault
        # stays free, and so does a read.
        targets = journal_guard.write_targets("Bash", tool_input, cwd)
        if not targets:
            return (False, "", [])
        for target in targets:
            if target == "<unknown>":
                # a write nobody can resolve, made from a gated folder, is
                # refused like one that names it - but not attested.
                vault = gated_dir(cwd)
                if vault is None:
                    continue
                pages, errors = load(vault)
                if errors:
                    return (
                        True,
                        "Reading gate refused: " + vault + " cannot read its required pages (" + "; ".join(errors) + "). "
                        "To fix: repair SCHEMA.md and the pages it names; nothing is written into this vault while they are broken.",
                        [target],
                    )
                code, _message = status(vault, pages)
                if code != 0:
                    # refused once, like a named write: the refusal delivers the
                    # lines, so the next gesture passes (no endless loop).
                    _attest_rendered(vault, pages, ctx)
                    return (True, refusal_text(vault, pages), [target])
                continue
            vault = gated_vault(target, cwd)
            if vault is None:
                continue
            attest = os.path.join(vault, ATTEST)
            if target == absolute(attest, cwd):
                return (True, HAND_WRITE, [attest])
            pages, errors = load(vault)
            if errors:
                return (
                    True,
                    "Reading gate refused: " + vault + " cannot read its required pages (" + "; ".join(errors) + "). "
                    "To fix: repair SCHEMA.md and the pages it names; nothing is written into this vault while they are broken.",
                    [target],
                )
            code, _message = status(vault, pages)
            if code == 0:
                continue
            _attest_rendered(vault, pages, ctx)
            return (True, refusal_text(vault, pages), [target])

    return (False, "", [])


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
