#!/usr/bin/env python3
"""resume_note.py"""

import sys
import os
import subprocess
import tempfile

NOTICE = [
    "NAME      resume_note.py - prints the open tasks and the last journal entry of a project vault, in under 25 lines, to resume a session without reading the vault.",
    "READS     --vault: todo.md and the log.md found by name under it (the raw folder is skipped).",
    "WRITES    nothing: the summary on the standard output; exit 0 done, 2 usage, 3 todo.md or log.md missing.",
    "EXAMPLE   python3 resume_note.py --vault project/vault",
    "PITFALLS  2026-10-23 a resumed session read twelve vault files to learn what one entry and three lines already said, and cost more tokens than a session with no memory.",
]

FIXTURE_T = """\
# stock - todo

Each line says who decides: (me) or (operator).

- [x] (me) item 3: report
- [ ] (me) item 4: finish stock/adjust.py
- [ ] (me) item 5: implement stock/merge.py per SPEC.md
"""

FIXTURE_L = """\
# Log - append-only, sealed

## [2026-10-22 00:00] setup
Decision: vault created
<!-- chain prev=0000 hash=aaaa -->

## [2026-10-22 16:40] Session 1 closing note (stock)
Done: items 1-3 complete

Partial: item 4 in stock/adjust.py, decided to mutate in place
Next step: finish item 4
<!-- chain prev=aaaa hash=bbbb -->
"""

FIXTURE_T_CLOSED = """\
# stock - todo

- [x] (me) item 1: setup
- [x] (me) item 2: report
- [x] (me) item 3: report
"""


def find_file_recursive(vault_path, filename):
    candidates = []
    for root, dirs, files in os.walk(vault_path):
        dirs[:] = [d for d in dirs if d != "raw"]
        if filename in files:
            rel = os.path.relpath(os.path.join(root, filename), vault_path)
            candidates.append((rel, os.path.join(root, filename)))
    if not candidates:
        return None
    candidates.sort(key=lambda x: (len(x[0]), x[0]))
    return candidates[0][1]


def parse_todo(path):
    tasks = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            s = line.rstrip("\n")
            if s.startswith("- [ ] "):
                tasks.append("- " + s[6:])
            elif s.startswith("- [ ]"):
                tasks.append("- " + s[5:].lstrip(" ") if s[5:].strip() else "- ")
    return tasks


def parse_log_last(path):
    with open(path, "r", encoding="utf-8") as f:
        lines = f.readlines()
    entry_indices = []
    for i, line in enumerate(lines):
        s = line.rstrip("\n")
        if s.startswith("## [") and "] " in s:
            entry_indices.append(i)
    if not entry_indices:
        return None, []
    last = entry_indices[-1]
    title_line = lines[last].rstrip("\n")
    pos = title_line.index("] ")
    title = title_line[pos + 2:]
    content = []
    for i in range(last + 1, len(lines)):
        s = lines[i].rstrip("\n")
        if s.startswith("## [") and "] " in s:
            break
        if s == "" or s.startswith("<!--"):
            continue
        content.append(s)
    return title, content


def build_output(vault_path):
    abs_vault = os.path.abspath(vault_path)
    base = os.path.basename(abs_vault)
    if base == "vault":
        name = os.path.basename(os.path.dirname(abs_vault))
    else:
        name = base

    todo_path = find_file_recursive(abs_vault, "todo.md")
    if todo_path is None:
        return None, "todo.md not found in vault"

    log_path = find_file_recursive(abs_vault, "log.md")
    if log_path is None:
        return None, "log.md not found in vault"

    tasks = parse_todo(todo_path)
    title, content = parse_log_last(log_path)

    out = []
    out.append("RESUME " + name)
    out.append("OPEN")
    if not tasks:
        out.append("- none")
    else:
        for t in tasks:
            out.append(t)
    out.append("LAST ENTRY " + title)
    for c in content:
        out.append(c)
    return out, None


def run_autotest():
    sys.dont_write_bytecode = True
    script = os.path.abspath(__file__)
    tmpdir = tempfile.mkdtemp()
    results = []
    all_pass = True

    env = os.environ.copy()
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = os.path.join(tmpdir, "pycache")

    def run(args_list):
        cmd = [sys.executable, script] + args_list
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, cwd=tmpdir)
        return p.returncode, p.stdout, p.stderr

    def check(idx, args_list, exp_code, exp_stdout, exp_stderr_contains=None):
        code, stdout, stderr = run(args_list)
        lines_out = stdout.rstrip("\n").split("\n") if stdout.strip() else []
        expected_lines = exp_stdout.rstrip("\n").split("\n") if exp_stdout.strip() else []
        ok = (code == exp_code and lines_out == expected_lines)
        if exp_stderr_contains:
            ok = ok and (exp_stderr_contains in stderr)
        if ok:
            results.append("PASS test {} code={} lines={}".format(idx, exp_code, len(expected_lines)))
        else:
            all_pass = False
            results.append(
                "FAIL test {} expected code={} got={} expected_lines={} got_lines={}".format(
                    idx, exp_code, code, len(expected_lines), len(lines_out)
                )
            )
        return ok

    # --- Test 1 ---
    vault1 = os.path.join(tmpdir, "stock", "vault")
    os.makedirs(vault1, exist_ok=True)
    with open(os.path.join(vault1, "todo.md"), "w", encoding="utf-8") as f:
        f.write(FIXTURE_T)
    with open(os.path.join(vault1, "log.md"), "w", encoding="utf-8") as f:
        f.write(FIXTURE_L)

    exp1 = (
        "RESUME stock\n"
        "OPEN\n"
        "- (me) item 4: finish stock/adjust.py\n"
        "- (me) item 5: implement stock/merge.py per SPEC.md\n"
        "LAST ENTRY Session 1 closing note (stock)\n"
        "Done: items 1-3 complete\n"
        "Partial: item 4 in stock/adjust.py, decided to mutate in place\n"
        "Next step: finish item 4"
    )
    check(1, ["--vault", "stock/vault"], 0, exp1)

    # --- Test 2 ---
    exp2 = (
        "RESUME stock\n"
        "OPEN\n"
        "- (me) item 4: finish stock/adjust.py\n"
        "- (me) item 5: implement stock/merge.py per SPEC.md\n"
        "... 4 more lines"
    )
    check(2, ["--vault", "stock/vault", "--max-lines", "5"], 0, exp2)

    # --- Test 3 ---
    vault3 = os.path.join(tmpdir, "closed", "vault")
    os.makedirs(vault3, exist_ok=True)
    with open(os.path.join(vault3, "todo.md"), "w", encoding="utf-8") as f:
        f.write(FIXTURE_T_CLOSED)
    with open(os.path.join(vault3, "log.md"), "w", encoding="utf-8") as f:
        f.write(FIXTURE_L)
    code3, stdout3, _ = run(["--vault", "closed/vault"])
    if code3 == 0 and "- none" in stdout3:
        results.append("PASS test 3 code=0 contains '- none'")
    else:
        all_pass = False
        results.append("FAIL test 3 expected code=0 got={} missing '- none'".format(code3))

    # --- Test 4a: no log.md ---
    vault4 = os.path.join(tmpdir, "nolog", "vault")
    os.makedirs(vault4, exist_ok=True)
    with open(os.path.join(vault4, "todo.md"), "w", encoding="utf-8") as f:
        f.write(FIXTURE_T)
    code4a, stdout4a, stderr4a = run(["--vault", "nolog/vault"])
    ok4a = (code4a == 3 and stdout4a == "")
    if not ok4a:
        all_pass = False
    results.append("PASS test 4a code=3 stdout empty" if ok4a else "FAIL test 4a expected code=3 empty got code={} out={!r}".format(code4a, stdout4a[:40]))

    # --- Test 4b: no --vault ---
    code4b, stdout4b, stderr4b = run([])
    ok4b = (code4b == 2 and "usage:" in stderr4b)
    if not ok4b:
        all_pass = False
    results.append("PASS test 4b code=2 usage in stderr" if ok4b else "FAIL test 4b expected code=2 got={} stderr={!r}".format(code4b, stderr4b[:60]))

    # --- Test 5: --notice ---
    code5, stdout5, _ = run(["--notice"])
    lines5 = stdout5.rstrip("\n").split("\n")
    ok5 = (code5 == 0 and lines5 == NOTICE)
    if not ok5:
        all_pass = False
    results.append("PASS test 5 notice 5 lines" if ok5 else "FAIL test 5 expected 5 lines got {} lines".format(len(lines5)))

    shutil.rmtree(tmpdir, ignore_errors=True)

    for r in results:
        print(r)

    return all_pass


import shutil


def main():
    if "--notice" in sys.argv:
        for line in NOTICE:
            print(line)
        sys.exit(0)

    if "--autotest" in sys.argv:
        passed = run_autotest()
        sys.exit(0 if passed else 1)

    vault_path = None
    max_lines = 25
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--vault":
            if i + 1 < len(sys.argv):
                vault_path = sys.argv[i + 1]
                i += 2
            else:
                vault_path = None
                i += 1
        elif sys.argv[i] == "--max-lines":
            if i + 1 < len(sys.argv):
                try:
                    max_lines = int(sys.argv[i + 1])
                except ValueError:
                    sys.stderr.write("usage: resume_note.py --vault DIR [--max-lines N]\n")
                    sys.exit(2)
                i += 2
            else:
                i += 1
        else:
            sys.stderr.write("usage: resume_note.py --vault DIR [--max-lines N]\n")
            sys.exit(2)

    if vault_path is None:
        sys.stderr.write("usage: resume_note.py --vault DIR [--max-lines N]\n")
        sys.exit(2)

    output, error = build_output(vault_path)

    if error:
        sys.stderr.write(error + "\n")
        sys.exit(3)

    if len(output) > max_lines:
        k = len(output) - (max_lines - 1)
        output = output[:max_lines - 1]
        output.append("... " + str(k) + " more lines")

    for line in output:
        print(line)

    sys.exit(0)


if __name__ == "__main__":
    main()
