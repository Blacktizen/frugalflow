#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""End-to-end test of the automatic memory."""

import os
import sys
import re
import shutil
import tempfile
import subprocess

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

NEW_RULE = "- ⛔ new rule\n"
GIST = "Karpathy gist `a1b2c3d4e5f6a7b8c9d0`.\n"
UNKNOWN = "see `abc1234`\n"
LOST = "# Lost\n"
INDEX_ADD = "- [[lost]]\n"
SOURCES_ADD = "- paper.pdf\n"

USAGE = "usage: e2e_memory.py [--notice | --autotest]\n"

NOTICE = (
    "NAME      e2e_memory.py - end-to-end test of the automatic memory: runs the real tools on a vault mounted in a temporary folder.\n"
    "READS     the tools next to this folder: vault_new.py, journal_add.py, reading_gate.py, vault_check.py; git, for a throwaway repository.\n"
    "WRITES    only in a temporary folder, always removed, even on failure. Exit 0 all steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_memory.py\n"
    "PITFALLS  2026-09-26 an earlier end-to-end test left its temporary folder behind on every run; this one removes it in a finally block.\n"
)


def tool(name, *args):
    """Run a tool as a subprocess; return (returncode, stdout)."""
    r = subprocess.run(
        [sys.executable, os.path.join(BIN, name)] + [str(a) for a in args],
        capture_output=True,
        text=True,
    )
    return (r.returncode, r.stdout)


def fresh(tmp, label):
    """Create a new vault under tmp/label and return the vault path."""
    root = os.path.join(tmp, label)
    tool("vault_new.py", "--root", root, "--name", "demo", "--today", "2026-09-26")
    return os.path.join(root, "vault")


def edit(path, old, new):
    """Replace old with new in the file at path (utf-8)."""
    with open(path, "r", encoding="utf-8") as f:
        content = f.read()
    content = content.replace(old, new)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)


def append_text(path, text):
    """Append text to the file at path (utf-8, mode a)."""
    with open(path, "a", encoding="utf-8") as f:
        f.write(text)


def git_repo(d):
    """Initialise a git repo at d, make one empty commit, return the HEAD sha."""
    subprocess.run(["git", "init", "-q", d], check=True)
    subprocess.run(
        ["git", "-C", d, "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "--allow-empty", "-m", "x"],
        check=True,
    )
    r = subprocess.run(["git", "-C", d, "rev-parse", "HEAD"],
                       capture_output=True, text=True, check=True)
    return r.stdout.strip()


def _step1(tmp):
    V = fresh(tmp, "s1")
    ok = os.path.isdir(V)
    if not ok:
        return False
    c, out = tool("vault_check.py", "--vault", V)
    ok = (c == 0 and "PASS LOG 1 entries chained" in out and out.endswith("VAULT OK\n"))
    if not ok:
        return False
    c, _ = tool("vault_new.py", "--root", os.path.dirname(V), "--name", "demo")
    return c == 3


def _step2(tmp):
    V = fresh(tmp, "s2")
    c, out = tool("reading_gate.py", "--vault", V, "--show")
    if c != 0:
        return False
    filtered = [l for l in out.splitlines()
                if not l.startswith("PAGE ") and not l.startswith("FINGERPRINT ")]
    attest_path = os.path.join(tmp, "s2.txt")
    with open(attest_path, "w", encoding="utf-8") as f:
        for line in filtered:
            f.write(line + "\n")
    c, _ = tool("reading_gate.py", "--vault", V, "--attest", attest_path)
    if c != 0:
        return False
    src = os.path.join(V, "overview.md")
    dst = os.path.join(V, "01-context", "overview.md")
    os.makedirs(os.path.dirname(dst), exist_ok=True)
    os.rename(src, dst)
    c, _ = tool("reading_gate.py", "--vault", V, "--status")
    if c != 0:
        return False
    c, _ = tool("vault_check.py", "--vault", V)
    if c != 0:
        return False
    append_text(dst, NEW_RULE)
    c, _ = tool("reading_gate.py", "--vault", V, "--status")
    return c == 5


def _step3(tmp):
    V = fresh(tmp, "s3")
    c, _ = tool("journal_add.py", "--vault", V, "--title", "gesture",
                "--field", "Decision=a", "--when", "2026-09-26 10:00")
    if c != 0:
        return False
    c, out = tool("vault_check.py", "--vault", V)
    if c != 0 or "PASS LOG 2 entries chained" not in out:
        return False
    edit(os.path.join(V, "log.md"), "Decision: a", "Decision: A")
    c, out = tool("vault_check.py", "--vault", V)
    if c != 6 or "FAIL LOG entry 1 was rewritten" not in out:
        return False
    c, _ = tool("journal_add.py", "--vault", V, "--title", "gesture",
                "--field", "Decision=a", "--when", "2026-09-26 10:00")
    return c == 4


def _step4(tmp):
    R = os.path.join(tmp, "repo")
    sha = git_repo(R)
    V = fresh(tmp, "s4")
    append_text(os.path.join(V, "overview.md"), "Done in `" + sha + "`.\n" + GIST)
    c, out = tool("vault_check.py", "--vault", V, "--repo", R)
    if c != 0 or "PASS COMMITS 1 claims found, 1 set apart" not in out:
        return False
    append_text(os.path.join(V, "todo.md"), UNKNOWN)
    c, out = tool("vault_check.py", "--vault", V, "--repo", R)
    return c == 6 and "FAIL COMMITS unknown: abc1234 (todo.md)" in out


def _step5(tmp):
    V = fresh(tmp, "s5")
    lost_path = os.path.join(V, "02-decisions", "lost.md")
    os.makedirs(os.path.dirname(lost_path), exist_ok=True)
    with open(lost_path, "w", encoding="utf-8") as f:
        f.write(LOST)
    pdf_path = os.path.join(V, "raw", "paper.pdf")
    os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
    with open(pdf_path, "w", encoding="utf-8") as f:
        f.write("x")
    c, out = tool("vault_check.py", "--vault", V)
    if c != 6:
        return False
    if "FAIL INDEX not listed: 02-decisions/lost.md" not in out:
        return False
    if "FAIL SOURCES not cited: raw/paper.pdf" not in out:
        return False
    append_text(os.path.join(V, "index.md"), INDEX_ADD)
    append_text(os.path.join(V, "sources.md"), SOURCES_ADD)
    c, _ = tool("vault_check.py", "--vault", V)
    return c == 0


def steps(tmp):
    """Run the five steps on their own vaults; return a list of (label, ok) tuples."""
    labels = [
        "a new vault passes the closing check",
        "a page moved into a subfolder keeps the gate and the check green",
        "the log is sealed: an append passes, a rewrite is caught",
        "a gist hash is set apart, an unknown commit fails",
        "a page left out of the index or a raw file left uncited fails",
    ]
    fns = [_step1, _step2, _step3, _step4, _step5]
    results = []
    for i, (label, fn) in enumerate(zip(labels, fns), 1):
        try:
            ok = fn(tmp)
        except Exception:
            ok = False
        results.append((label, bool(ok)))
    return results


def main_run(parent):
    """Create a temp dir under parent, run steps, remove it in finally. Return (code, lines)."""
    tmp = tempfile.mkdtemp(dir=parent)
    try:
        results = steps(tmp)
    finally:
        shutil.rmtree(tmp)
    lines = []
    for i, (label, ok) in enumerate(results, 1):
        if ok:
            lines.append("PASS {} {}".format(i, label))
        else:
            lines.append("FAIL {} {}".format(i, label))
    k = sum(1 for _, ok in results if not ok)
    if k == 0:
        lines.append("E2E MEMORY OK")
    else:
        lines.append("E2E MEMORY FAILED {} of 5".format(k))
    code = 0 if k == 0 else 1
    return (code, lines)


def _autotest():
    """Run the five self-checks; print one line per proof; return exit code."""
    script = os.path.abspath(__file__)
    failures = 0

    # Proof 1: --notice
    r = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
    expected1 = "code 0 and stdout starts NAME      e2e_memory.py"
    got1 = "code {} stdout starts {}".format(r.returncode, repr(r.stdout[:30]))
    ok1 = (r.returncode == 0 and r.stdout.startswith("NAME      e2e_memory.py"))
    if not r.stdout:
        ok1 = False
    if ok1:
        print("PASS 1 expected {} | got {}".format(expected1, got1))
    else:
        failures += 1
        print("FAIL 1 expected {} | got {}".format(expected1, got1))

    # Proof 2: --bogus
    r = subprocess.run([sys.executable, script, "--bogus"], capture_output=True, text=True)
    expected2 = "code 2 and stdout == usage line"
    got2 = "code {} stdout == {}".format(r.returncode, repr(r.stdout))
    ok2 = (r.returncode == 2 and r.stdout == USAGE)
    if not r.stdout:
        ok2 = False
    if ok2:
        print("PASS 2 expected {} | got {}".format(expected2, got2))
    else:
        failures += 1
        print("FAIL 2 expected {} | got {}".format(expected2, got2))

    # Proof 3: main_run cleans up
    tmp_parent = tempfile.mkdtemp()
    try:
        main_run(tmp_parent)
        got3 = "listdir={}".format(os.listdir(tmp_parent))
        ok3 = (os.listdir(tmp_parent) == [])
    except Exception as e:
        got3 = "exception: {}".format(e)
        ok3 = False
    finally:
        shutil.rmtree(tmp_parent, ignore_errors=True)
    expected3 = "parent dir empty after main_run"
    if ok3:
        print("PASS 3 expected {} | got {}".format(expected3, got3))
    else:
        failures += 1
        print("FAIL 3 expected {} | got {}".format(expected3, got3))

    # Proof 4: main_run return structure
    tmp_parent2 = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent2)
        got4 = "code={} len(lines)={} first5_ok={} last_start={}".format(
            code, len(lines),
            all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:5]),
            repr(lines[5][:11]) if len(lines) > 5 else "N/A")
        ok4 = (
            code in (0, 1)
            and len(lines) == 6
            and all(l.startswith("PASS ") or l.startswith("FAIL ") for l in lines[:5])
            and lines[5].startswith("E2E MEMORY ")
        )
    except Exception as e:
        got4 = "exception: {}".format(e)
        ok4 = False
    finally:
        shutil.rmtree(tmp_parent2, ignore_errors=True)
    expected4 = "code in (0,1), 6 lines: 5 PASS/FAIL + 1 E2E MEMORY"
    if ok4:
        print("PASS 4 expected {} | got {}".format(expected4, got4))
    else:
        failures += 1
        print("FAIL 4 expected {} | got {}".format(expected4, got4))

    # Proof 5: consistency of FAIL count, last line, and code
    tmp_parent3 = tempfile.mkdtemp()
    try:
        code, lines = main_run(tmp_parent3)
        k = sum(1 for l in lines[:5] if l.startswith("FAIL "))
        if k == 0:
            expected_last = "E2E MEMORY OK"
            expected_code = 0
        else:
            expected_last = "E2E MEMORY FAILED {} of 5".format(k)
            expected_code = 1
        got5 = "k={} last={} code={}".format(k, lines[5], code)
        ok5 = (lines[5] == expected_last and code == expected_code)
    except Exception as e:
        got5 = "exception: {}".format(e)
        ok5 = False
    finally:
        shutil.rmtree(tmp_parent3, ignore_errors=True)
    expected5 = "FAIL count matches last line and exit code"
    if ok5:
        print("PASS 5 expected {} | got {}".format(expected5, got5))
    else:
        failures += 1
        print("FAIL 5 expected {} | got {}".format(expected5, got5))

    return 0 if failures == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) == 1:
        code, lines = main_run(None)
        for line in lines:
            print(line)
        sys.exit(code)
    elif sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)
