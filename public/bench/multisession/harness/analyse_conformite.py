#!/usr/bin/env python3
"""Analyse comparative du respect des conventions entre conditions A et B."""

import argparse
import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

SCRIPT_PATH = os.path.abspath(__file__)
HARNESS_DIR = os.path.dirname(SCRIPT_PATH)
CHECK_RULES_PATH = os.path.join(HARNESS_DIR, "check_rules.py")

CONDITIONS = ("A", "B")
SESSIONS = (1, 2, 3, 4, 5)
LATE_SESSIONS = (2, 3, 4, 5)

COLUMNS = [
    "livres",
    "stricts",
    "tolerants",
    "echecs_t1",
    "echecs_t2",
    "echecs_t3_strict",
    "echecs_t3_tolerant",
    "echecs_t4",
    "point_final",
]
STAT_KEYS = COLUMNS + ["total"]


def load_check_rules():
    spec = importlib.util.spec_from_file_location("check_rules", CHECK_RULES_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def blank_stats():
    return {k: {c: 0 for c in STAT_KEYS} for k in SESSIONS}


def fmt_pct(n, d):
    if d == 0:
        return 0.0
    return 100.0 * n / d


def docstring_first_line(path):
    try:
        with open(path, encoding="utf-8") as fh:
            tree = ast.parse(fh.read())
    except (SyntaxError, UnicodeDecodeError, ValueError, OSError):
        return None
    doc = ast.get_docstring(tree)
    if doc is None:
        return None
    lines = doc.splitlines()
    if not lines:
        return None
    return lines[0]


def t3_tolerant(first, slug):
    if first is None:
        return False
    clean = first.strip().rstrip(". ").strip()
    return clean == "Kata: " + slug


def point_final(first, slug):
    return first is not None and first == "Kata: " + slug + "."


def iter_chains(runs_dir):
    try:
        names = sorted(os.listdir(runs_dir))
    except OSError:
        return
    for name in names:
        path = os.path.join(runs_dir, name)
        if not os.path.isdir(path):
            continue
        if name[:1] not in CONDITIONS:
            continue
        if not os.path.isfile(os.path.join(path, "results.jsonl")):
            continue
        yield name, path


def read_sessions(chain_path):
    path = os.path.join(chain_path, "results.jsonl")
    sessions = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            if not isinstance(data, dict) or "k" not in data or "slugs" not in data:
                continue
            try:
                k = int(data["k"])
            except (TypeError, ValueError):
                continue
            sessions.append((k, list(data["slugs"])))
    return sessions


def collect(runs_dir, analyze_module):
    stats = {c: blank_stats() for c in CONDITIONS}
    chains = list(iter_chains(runs_dir))
    for name, chain_path in chains:
        condition = name[0]
        kata_dir = os.path.join(chain_path, "proj", "kata")
        for k, slugs in read_sessions(chain_path):
            if k not in SESSIONS:
                continue
            row = stats[condition][k]
            for slug in slugs:
                module = slug.replace("-", "_")
                path = os.path.join(kata_dir, module + ".py")
                res = analyze_module(path, slug)
                row["total"] += 1
                if not res["delivered"]:
                    continue
                first = docstring_first_line(path)
                row["livres"] += 1
                if res["ok"]:
                    row["stricts"] += 1
                if res["t1"] and res["t2"] and res["t4"] and t3_tolerant(first, slug):
                    row["tolerants"] += 1
                if not res["t1"]:
                    row["echecs_t1"] += 1
                if not res["t2"]:
                    row["echecs_t2"] += 1
                if not res["t3"]:
                    row["echecs_t3_strict"] += 1
                if not t3_tolerant(first, slug):
                    row["echecs_t3_tolerant"] += 1
                if not res["t4"]:
                    row["echecs_t4"] += 1
                if point_final(first, slug):
                    row["point_final"] += 1
    return stats


def render(stats):
    lines = ["# Respect des conventions par condition et par session", ""]
    header = [
        "Condition",
        "Session",
        "Livres",
        "Strict",
        "Tolerant",
        "Echecs t1",
        "Echecs t2",
        "Echecs t3 strict",
        "Echecs t3 tolerant",
        "Echecs t4",
        "Point final",
    ]
    lines.append("| " + " | ".join(header) + " |")
    lines.append("|" + "|".join(["---"] * len(header)) + "|")
    for condition in CONDITIONS:
        for k in SESSIONS:
            row = stats[condition][k]
            cells = [condition, str(k)] + [str(row[c]) for c in COLUMNS]
            lines.append("| " + " | ".join(cells) + " |")
    lines.append("")
    lines.append("## Synthese")
    lines.append("")
    for condition in CONDITIONS:
        s1 = stats[condition][1]
        s25 = {c: sum(stats[condition][k][c] for k in LATE_SESSIONS) for c in STAT_KEYS}
        lines.append(
            "- %s, session 1 : strict %.1f %% (%d/%d), tolerant %.1f %% (%d/%d)"
            % (
                condition,
                fmt_pct(s1["stricts"], s1["livres"]),
                s1["stricts"],
                s1["livres"],
                fmt_pct(s1["tolerants"], s1["livres"]),
                s1["tolerants"],
                s1["livres"],
            )
        )
        lines.append(
            "- %s, sessions 2-5 : strict %.1f %% (%d/%d), tolerant %.1f %% (%d/%d)"
            % (
                condition,
                fmt_pct(s25["stricts"], s25["livres"]),
                s25["stricts"],
                s25["livres"],
                fmt_pct(s25["tolerants"], s25["livres"]),
                s25["tolerants"],
                s25["livres"],
            )
        )
    lines.append("")
    lines.append("## Consigne suivie des la session 1 ?")
    lines.append("")
    for condition in CONDITIONS:
        s1 = stats[condition][1]
        pct = fmt_pct(s1["stricts"], s1["livres"])
        if pct < 50.0:
            verdict = "inferieure a 50 %, la consigne n'a pas ete suivie des la session 1"
        else:
            verdict = "superieure ou egale a 50 %, la consigne a ete suivie des la session 1"
        lines.append(
            "- %s : conformite stricte en session 1 = %.1f %% (%d/%d), donc %s."
            % (condition, pct, s1["stricts"], s1["livres"], verdict)
        )
    lines.append("")
    lines.append("## Score de respect tolerant a la session 5 (tous modules)")
    lines.append("")
    a5 = stats["A"][5]
    b5 = stats["B"][5]
    pa = fmt_pct(a5["tolerants"], a5["total"])
    pb = fmt_pct(b5["tolerants"], b5["total"])
    lines.append("- A : %d/%d modules tolerants, score %.1f %%" % (a5["tolerants"], a5["total"], pa))
    lines.append("- B : %d/%d modules tolerants, score %.1f %%" % (b5["tolerants"], b5["total"], pb))
    lines.append("- Difference B - A : %.1f points de pourcentage" % (pb - pa))
    return "\n".join(lines)


MODULE_DOT = (
    "\"\"\"Kata: x-y.\"\"\"\n"
    "\n"
    "\n"
    "def solve(n: int) -> int:\n"
    "    return n\n"
)

MODULE_PLAIN = (
    "\"\"\"Kata: x-y\"\"\"\n"
    "\n"
    "\n"
    "def solve(n: int) -> int:\n"
    "    return n\n"
)


def make_chain(root, name, module_content):
    chain_dir = os.path.join(root, name)
    os.makedirs(os.path.join(chain_dir, "proj", "kata"), exist_ok=True)
    with open(os.path.join(chain_dir, "results.jsonl"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"k": 1, "slugs": ["x-y"]}) + "\n")
    with open(os.path.join(chain_dir, "slugs.json"), "w", encoding="utf-8") as fh:
        fh.write(json.dumps({"x_y": "x-y"}))
    if module_content is not None:
        with open(os.path.join(chain_dir, "proj", "kata", "x_y.py"), "w", encoding="utf-8") as fh:
            fh.write(module_content)


def run_script(runs_dir):
    proc = subprocess.run(
        [sys.executable, "-I", SCRIPT_PATH, runs_dir],
        capture_output=True,
        text=True,
    )
    return proc.returncode, proc.stdout


def parse_table(stdout):
    rows = {}
    for line in stdout.splitlines():
        line = line.strip()
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2 + len(COLUMNS):
            continue
        condition, k_text = cells[0], cells[1]
        if condition not in CONDITIONS:
            continue
        try:
            k = int(k_text)
            values = [int(c) for c in cells[2:]]
        except ValueError:
            continue
        rows[(condition, k)] = dict(zip(COLUMNS, values))
    return rows


def test_1():
    root = tempfile.mkdtemp(prefix="conformite_autotest_")
    try:
        make_chain(root, "A1", MODULE_DOT)
        make_chain(root, "B1", MODULE_PLAIN)
        code, out = run_script(root)
        rows = parse_table(out)
        a = rows.get(("A", 1))
        b = rows.get(("B", 1))
        expected = "A session 1 strict=0 tolerant=1, B session 1 strict=1 tolerant=1, exit=0"
        passed = (
            code == 0
            and a is not None
            and a["stricts"] == 0
            and a["tolerants"] == 1
            and b is not None
            and b["stricts"] == 1
            and b["tolerants"] == 1
        )
        obtained = "exit=%s A=%s B=%s" % (
            code,
            "None" if a is None else "strict=%d tolerant=%d" % (a["stricts"], a["tolerants"]),
            "None" if b is None else "strict=%d tolerant=%d" % (b["stricts"], b["tolerants"]),
        )
        return ("epreuve1_strict_vs_tolerant", expected, obtained, passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def test_2():
    root = tempfile.mkdtemp(prefix="conformite_autotest_")
    try:
        code, out = run_script(root)
        passed = code == 0 and "aucune chaine" in out
        expected = "exit=0 et texte 'aucune chaine'"
        obtained = "exit=%s sortie=%s" % (code, out.strip().replace("\n", " ") or "(vide)")
        return ("epreuve2_sans_chaine", expected, obtained, passed)
    finally:
        shutil.rmtree(root, ignore_errors=True)


def run_autotest():
    tests = [test_1(), test_2()]
    all_ok = True
    for name, expected, obtained, passed in tests:
        if not passed:
            all_ok = False
        tag = "PASS" if passed else "FAIL"
        print("%s %s attendu=%s obtenu=%s" % (tag, name, expected, obtained))
    return 0 if all_ok else 1


def main():
    parser = argparse.ArgumentParser(prog="analyse_conformite.py")
    parser.add_argument("runs_dir", nargs="?")
    parser.add_argument("--autotest", action="store_true")
    args = parser.parse_args()
    if args.autotest:
        sys.exit(run_autotest())
    if args.runs_dir is None:
        parser.error("RUNS_DIR requis")
    check_rules = load_check_rules()
    stats = collect(args.runs_dir, check_rules.analyze_module)
    if all(stats[c][k]["total"] == 0 for c in CONDITIONS for k in SESSIONS):
        print("aucune chaine exploitable.")
        sys.exit(0)
    print(render(stats))


if __name__ == "__main__":
    main()
