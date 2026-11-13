#!/usr/bin/env python3
"""Refactor bench harness: prepares bench conditions and grades a delivered project."""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile

LIB_V2 = """class LibError(Exception):
    pass

def load_rows(table, page_size=50):
    if not table:
        raise KeyError("table")
    return [{"id": i, "table": table} for i in range(page_size)]

def price_cents(amount):
    return int(amount * 100 + 0.5)
"""

APP_GOOD = """from lib.fakelib import LibError, load_rows, price_cents

def run(table):
    try:
        return load_rows(table, page_size=20)
    except KeyError:
        raise LibError("empty table")

def price(amount):
    return round(amount * 100)
"""

APP_SILENT = """from lib.fakelib import LibError, load_rows, price_cents

def run(table):
    try:
        return load_rows(table)
    except KeyError:
        raise LibError("empty table")

def price(amount):
    return price_cents(amount)
"""

APP_BAD = """from lib.fakelib import LibError, fetch_rows, price_cents

def run(table):
    return fetch_rows(table)

def price(amount):
    return price_cents(amount)
"""

HIDDEN_CHECK = """import sys
try:
    import app
except Exception:
    app = None
from lib.fakelib import LibError

def ok(name, fn):
    try:
        r = bool(fn())
    except Exception:
        r = False
    print(("OK  " if r else "KO  ") + name)

def leve(arg):
    try:
        app.run(arg)
    except LibError:
        return True
    return False

ok("R1 import et noms", lambda: callable(app.run) and callable(app.price))
ok("R2 erreur bruyante LibError", lambda: leve(""))
ok("R3 defaut 20 lignes", lambda: len(app.run("t")) == 20)
ok("R4 arrondi 0,125 vaut 12", lambda: app.price(0.125) == 12)
"""

TPL_M1 = """# Consignes du projet
Ce projet change de version de bibliotheque. Avant de modifier du code :
- ecris d abord des tests qui decrivent le comportement actuel ;
- fais-les passer, puis seulement modifie le code ;
- garde les tests dans le dossier tests/ et lance-les avant de finir.
"""

TPL_M2 = """# Consignes du projet
Ce projet change de version de bibliotheque. Avant de modifier du code :
- ecris d abord des tests qui decrivent le comportement actuel ;
- lance-les AVANT toute modification : ils doivent echouer sur la nouvelle version (recu rouge) ;
- garde la sortie rouge dans RECU.txt ; tant que RECU.txt n existe pas, ne modifie rien ;
- apres modification, fais passer les tests, puis relance-les une fois de plus ;
- garde les tests dans le dossier tests/.
"""


def setup(directory, cond):
    os.makedirs(directory, exist_ok=True)
    if cond == "M1":
        target = os.path.join(directory, "CLAUDE.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(TPL_M1)
    elif cond == "M2":
        target = os.path.join(directory, "CLAUDE.md")
        with open(target, "w", encoding="utf-8") as fh:
            fh.write(TPL_M2)
    print("SETUP %s %s" % (directory, cond))
    return 0


def grade(directory):
    if not os.path.isfile(os.path.join(directory, "app.py")):
        print("ERREUR projet absent")
        return 2
    proc = subprocess.run(
        [sys.executable, "-c", HIDDEN_CHECK],
        cwd=directory,
        capture_output=True,
        text=True,
    )
    sys.stdout.write(proc.stdout)
    if proc.stdout and not proc.stdout.endswith("\n"):
        sys.stdout.write("\n")
    sys.stdout.flush()
    ok_lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("OK  ")]
    if proc.returncode == 0 and len(ok_lines) == 4:
        print("VERDICT REFONTE: VERT")
        return 0
    print("VERDICT REFONTE: ROUGE")
    return 1


def _run_self(*extra):
    return subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + list(extra),
        capture_output=True,
        text=True,
    )


def _write_project(root, app_text):
    lib_dir = os.path.join(root, "lib")
    os.makedirs(lib_dir, exist_ok=True)
    with open(os.path.join(root, "app.py"), "w", encoding="utf-8") as fh:
        fh.write(app_text)
    with open(os.path.join(lib_dir, "fakelib.py"), "w", encoding="utf-8") as fh:
        fh.write(LIB_V2)


def _count_ok(text):
    return sum(1 for ln in text.splitlines() if ln.startswith("OK  "))


def _verdict(out):
    if "VERDICT REFONTE: VERT" in out:
        return "VERT"
    if "VERDICT REFONTE: ROUGE" in out:
        return "ROUGE"
    return "ABSENT"


def _grade_report(proc, want_code, want_ok, want_verdict):
    out = proc.stdout
    if not out:
        return False, "sortie non vide", "sortie vide (exit %d)" % proc.returncode
    got_ok = _count_ok(out)
    got_verdict = _verdict(out)
    attendu = "exit %d, %d lignes OK, %s" % (want_code, want_ok, want_verdict)
    obtenu = "exit %d, %d lignes OK, %s" % (proc.returncode, got_ok, got_verdict)
    passed = (
        proc.returncode == want_code
        and got_ok == want_ok
        and got_verdict == want_verdict
    )
    return passed, attendu, obtenu


def _test_bon():
    root = tempfile.mkdtemp()
    try:
        _write_project(root, APP_GOOD)
        proc = _run_self("--grade", root)
        passed, attendu, obtenu = _grade_report(proc, 0, 4, "VERT")
        return ("PASS" if passed else "FAIL"), "bon", attendu, obtenu
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _test_silent():
    root = tempfile.mkdtemp()
    try:
        _write_project(root, APP_SILENT)
        proc = _run_self("--grade", root)
        passed, attendu, obtenu = _grade_report(proc, 1, 2, "ROUGE")
        return ("PASS" if passed else "FAIL"), "silencieux", attendu, obtenu
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _test_bad():
    root = tempfile.mkdtemp()
    try:
        _write_project(root, APP_BAD)
        proc = _run_self("--grade", root)
        passed, attendu, obtenu = _grade_report(proc, 1, 0, "ROUGE")
        return ("PASS" if passed else "FAIL"), "mauvais", attendu, obtenu
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _test_empty():
    root = tempfile.mkdtemp()
    try:
        proc = _run_self("--grade", root)
        out = proc.stdout
        if not out:
            return "FAIL", "vide", "exit 2, ERREUR projet absent", "sortie vide (exit %d)" % proc.returncode
        passed = proc.returncode == 2 and "ERREUR projet absent" in out
        attendu = "exit 2, ERREUR projet absent"
        obtenu = "exit %d, %s" % (proc.returncode, out.strip())
        return ("PASS" if passed else "FAIL"), "vide", attendu, obtenu
    finally:
        shutil.rmtree(root, ignore_errors=True)


def _test_setup():
    parent = tempfile.mkdtemp()
    try:
        d1 = os.path.join(parent, "s1")
        proc1 = _run_self("--setup", d1, "--cond", "M1")
        d2 = os.path.join(parent, "s2")
        proc2 = _run_self("--setup", d2, "--cond", "M0")
        if not proc1.stdout or not proc2.stdout:
            return "FAIL", "setup", "exit 0, CLAUDE.md == TPL_M1 / absent en M0", "sortie vide"
        path1 = os.path.join(d1, "CLAUDE.md")
        content1 = None
        if os.path.isfile(path1):
            with open(path1, "r", encoding="utf-8") as fh:
                content1 = fh.read()
        passed = (
            proc1.returncode == 0
            and content1 == TPL_M1
            and proc2.returncode == 0
            and not os.path.isfile(os.path.join(d2, "CLAUDE.md"))
        )
        attendu = "exit 0, CLAUDE.md == TPL_M1 / absent en M0"
        obtenu = "exit %d/%d, M1 egal TPL_M1: %s, M0 CLAUDE.md absent: %s" % (
            proc1.returncode,
            proc2.returncode,
            content1 == TPL_M1,
            not os.path.isfile(os.path.join(d2, "CLAUDE.md")),
        )
        return ("PASS" if passed else "FAIL"), "setup", attendu, obtenu
    finally:
        shutil.rmtree(parent, ignore_errors=True)


def autotest():
    tests = [_test_bon, _test_silent, _test_bad, _test_empty, _test_setup]
    failures = 0
    for test in tests:
        status, name, attendu, obtenu = test()
        if status == "FAIL":
            failures += 1
        print("%s %s attendu=%s obtenu=%s" % (status, name, attendu, obtenu))
    return 0 if failures == 0 else 1


def main(argv):
    parser = argparse.ArgumentParser(
        description="Refactor bench harness: setup bench conditions, grade a delivered project."
    )
    parser.add_argument("--grade", metavar="DIR", help="run the hidden check on DIR and print VERT or ROUGE")
    parser.add_argument("--setup", metavar="DIR", help="prepare DIR for a bench condition")
    parser.add_argument("--cond", choices=["M0", "M1", "M2"], help="bench condition for --setup")
    parser.add_argument("--autotest", action="store_true", help="run the harness self-tests")
    args = parser.parse_args(argv)
    if args.autotest:
        return autotest()
    if args.grade:
        return grade(args.grade)
    if args.setup:
        if args.cond is None:
            parser.error("--setup requires --cond {M0,M1,M2}")
        return setup(args.setup, args.cond)
    parser.print_help()
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
