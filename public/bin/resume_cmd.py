import sys
import os
import datetime
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_rules

NOTICE = (
    "NAME      resume_cmd.py - prints a text to paste into a new session: "
    "where the project stands, open todos, recent decisions, pages to reread.\n"
    "READS     the vault folder: overview.md, todo.md, log.md and the "
    "REQUIRED-READING block of SCHEMA.md; --vault DIR, else ./vault.\n"
    "WRITES    nothing: the text goes to the standard output. Exit 0 printed, "
    "2 usage, 3 no vault, 4 sealed log broken (text still printed).\n"
    "EXAMPLE   python3 resume_cmd.py --vault ~/projects/demo/vault --entries 5\n"
    "PITFALLS  2026-10-25 a new session started from memory of the last one "
    "and repeated a settled decision; the text is built from the sealed log, "
    "never from recall."
)

USAGE_MSG = (
    "usage: resume_cmd.py [--vault DIR] [--entries N] | --notice | --autotest"
)


def _read_file(file_path):
    if not os.path.isfile(file_path):
        return None
    with open(file_path, "r", encoding="utf-8") as f:
        return f.read()


def _get_project_name(overview_text, vault_dir):
    if overview_text is not None and overview_text.strip():
        lines = overview_text.splitlines()
        if lines:
            first_line = lines[0]
            if first_line.startswith("# "):
                name = first_line[2:]
                idx = name.find(" - ")
                if idx != -1:
                    name = name[:idx]
                return name
    abs_vault = os.path.abspath(vault_dir)
    parent = os.path.dirname(abs_vault)
    return os.path.basename(parent)


def _extract_required_reading(text):
    result = []
    in_block = False
    for line in text.splitlines():
        if not in_block:
            if line.startswith("<!-- REQUIRED-READING"):
                in_block = True
            continue
        if line.strip() == "-->":
            break
        if line.strip():
            result.append(line)
    return result


def _build_resume_lines(vault_dir, entries_count):
    overview_text = _read_file(os.path.join(vault_dir, "overview.md"))
    todo_text = _read_file(os.path.join(vault_dir, "todo.md"))
    log_text = _read_file(os.path.join(vault_dir, "log.md"))
    schema_text = _read_file(os.path.join(vault_dir, "SCHEMA.md"))

    lines = []

    project_name = _get_project_name(overview_text, vault_dir)
    lines.append("# Resume: " + project_name)

    today = datetime.date.today().isoformat()
    lines.append(
        "Built on " + today
        + " from the vault files. Every line below comes from the files;"
        " a part with nothing says NOTHING FOUND."
    )

    chain_ok = None
    if log_text is None:
        lines.append("Log: NOTHING FOUND")
    else:
        ok, n, bad, reason = chain_rules.verify(log_text)
        if ok:
            lines.append("Log: sealed, " + str(n) + " entries, chain OK")
        else:
            lines.append(
                "LOG CHAIN BROKEN (entry " + str(bad) + ": " + reason
                + "): do not trust the entries below"
            )
        chain_ok = ok

    lines.append("")
    lines.append("## Where we stand")
    if overview_text is not None:
        ov_lines = overview_text.splitlines()
        content_lines = []
        for j, line in enumerate(ov_lines):
            if j == 0:
                continue
            if line.strip() == "":
                continue
            if line.startswith("updated:"):
                continue
            content_lines.append(line)
            if len(content_lines) >= 20:
                break
        if content_lines:
            lines.extend(content_lines)
        else:
            lines.append("NOTHING FOUND")
    else:
        lines.append("NOTHING FOUND")

    lines.append("")
    lines.append("## Open todos")
    if todo_text is not None:
        todo_lines = []
        for line in todo_text.splitlines():
            if line.startswith("- [ ]"):
                todo_lines.append(line.rstrip())
        if todo_lines:
            lines.extend(todo_lines)
        else:
            lines.append("NOTHING FOUND")
    else:
        lines.append("NOTHING FOUND")

    lines.append("")
    lines.append("## Recent decisions")
    if log_text is not None:
        all_entries = chain_rules.entries(log_text)
        if entries_count < len(all_entries):
            selected = all_entries[-entries_count:]
        else:
            selected = all_entries
        if selected:
            for entry in selected:
                body = entry["body"]
                body_lines = body.splitlines()
                if body_lines:
                    first_line = body_lines[0]
                    if first_line.startswith("## "):
                        first_line = first_line[3:]
                    lines.append("### " + first_line)
                    for bline in body_lines[1:]:
                        stripped = bline.rstrip()
                        if stripped:
                            lines.append(stripped)
        else:
            lines.append("NOTHING FOUND")
    else:
        lines.append("NOTHING FOUND")

    lines.append("")
    lines.append("## Read first")
    if schema_text is not None:
        reading_lines = _extract_required_reading(schema_text)
        if reading_lines:
            for rl in reading_lines:
                lines.append("- " + rl)
        else:
            lines.append("NOTHING FOUND")
    else:
        lines.append("NOTHING FOUND")

    lines.append("")
    lines.append("## Rules for this session")
    lines.append(
        "- After each gesture that changes a state, write a log entry:"
        " frugalflow run journal_add --vault vault --title <title>"
        " --field Decision=<what> --field Why=<why>"
    )
    lines.append(
        "- Never edit an old log entry: the log is sealed and append-only."
    )
    lines.append(
        "- Before you write, restate the key lines of the Read first pages."
    )

    return lines, chain_ok


def main(argv):
    vault_dir = None
    entries_count = 5
    notice_flag = False
    autotest_flag = False

    i = 0
    while i < len(argv):
        arg = argv[i]
        if arg == "--vault":
            i += 1
            if i >= len(argv):
                print(USAGE_MSG)
                return 2
            vault_dir = argv[i]
        elif arg == "--entries":
            i += 1
            if i >= len(argv):
                print(USAGE_MSG)
                return 2
            try:
                entries_count = int(argv[i])
            except ValueError:
                print(USAGE_MSG)
                return 2
            if entries_count < 1:
                print(USAGE_MSG)
                return 2
        elif arg == "--notice":
            notice_flag = True
        elif arg == "--autotest":
            autotest_flag = True
        else:
            print(USAGE_MSG)
            return 2
        i += 1

    if notice_flag:
        print(NOTICE)
        return 0

    if autotest_flag:
        return _run_autotest()

    if vault_dir is None:
        vault_dir = os.path.join(os.getcwd(), "vault")

    if not os.path.isdir(vault_dir):
        print("NO VAULT: " + vault_dir)
        return 3

    lines, chain_ok = _build_resume_lines(vault_dir, entries_count)
    for line in lines:
        print(line)

    if chain_ok is False:
        return 4
    return 0


def _run_autotest():
    bin_dir = os.path.dirname(os.path.abspath(__file__))
    tmp_dir = tempfile.mkdtemp()
    try:
        proj_dir = os.path.join(tmp_dir, "PROJ")
        vault_dir = os.path.join(proj_dir, "vault")
        script_path = os.path.abspath(__file__)

        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "vault_new.py"),
             "--root", proj_dir, "--name", "demo", "--today", "2026-01-05"],
            check=True, capture_output=True)
        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "journal_add.py"),
             "--vault", vault_dir, "--title", "Picked sqlite",
             "--field", "Decision=Picked sqlite",
             "--field", "Why=one file, no server"],
            check=True, capture_output=True)
        subprocess.run(
            [sys.executable, os.path.join(bin_dir, "journal_add.py"),
             "--vault", vault_dir, "--title", "Dropped the cache",
             "--field", "Decision=Dropped the cache",
             "--field", "Why=stale reads seen twice"],
            check=True, capture_output=True)

        with open(os.path.join(vault_dir, "todo.md"), "a", encoding="utf-8") as f:
            f.write("- [ ] (me) Write the parser tests\n")
            f.write("- [x] (me) Pick a license\n")

        all_pass = True

        # Test 1
        res = subprocess.run(
            [sys.executable, script_path, "--vault", vault_dir],
            capture_output=True, text=True)
        out1 = res.stdout
        code1 = res.returncode
        t1_ok = (
            out1 != ""
            and code1 == 0
            and "Write the parser tests" in out1
            and "Picked sqlite" in out1
            and "Dropped the cache" in out1
            and "stale reads seen twice" in out1
            and "sealed, 3 entries" in out1
            and "# Resume: demo" in out1
            and "- overview.md" in out1
            and "Pick a license" not in out1
        )
        if not t1_ok:
            all_pass = False
        print(
            ("PASS" if t1_ok else "FAIL")
            + " 1: expected code 0, all markers present, 'Pick a license' absent;"
            " got code " + str(code1)
            + (", EMPTY OUTPUT" if out1 == "" else "")
        )

        # Test 2
        res = subprocess.run(
            [sys.executable, script_path, "--vault", vault_dir,
             "--entries", "1"],
            capture_output=True, text=True)
        out2 = res.stdout
        code2 = res.returncode
        t2_ok = (
            out2 != ""
            and code2 == 0
            and "Dropped the cache" in out2
            and "Picked sqlite" not in out2
        )
        if not t2_ok:
            all_pass = False
        print(
            ("PASS" if t2_ok else "FAIL")
            + " 2: expected 'Dropped the cache' present, 'Picked sqlite' absent;"
            " got code " + str(code2)
            + (", EMPTY OUTPUT" if out2 == "" else "")
        )

        # Test 3
        log_path = os.path.join(vault_dir, "log.md")
        with open(log_path, "r", encoding="utf-8") as f:
            log_content = f.read()
        modified = log_content.replace("Picked sqlite", "Picked postgres", 1)
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(modified)
        res = subprocess.run(
            [sys.executable, script_path, "--vault", vault_dir],
            capture_output=True, text=True)
        out3 = res.stdout
        code3 = res.returncode
        t3_ok = (
            out3 != ""
            and code3 == 4
            and "LOG CHAIN BROKEN" in out3
        )
        if not t3_ok:
            all_pass = False
        print(
            ("PASS" if t3_ok else "FAIL")
            + " 3: expected code 4 and 'LOG CHAIN BROKEN';"
            " got code " + str(code3)
            + (", EMPTY OUTPUT" if out3 == "" else "")
        )

        # Test 4
        bad_vault = os.path.join(tmp_dir, "DOES_NOT_EXIST")
        res = subprocess.run(
            [sys.executable, script_path, "--vault", bad_vault],
            capture_output=True, text=True)
        t4a_ok = res.returncode == 3 and "NO VAULT" in res.stdout

        res = subprocess.run(
            [sys.executable, script_path, "--bogus"],
            capture_output=True, text=True)
        t4b_ok = res.returncode == 2

        res = subprocess.run(
            [sys.executable, script_path, "--entries", "0"],
            capture_output=True, text=True)
        t4c_ok = res.returncode == 2

        t4_ok = t4a_ok and t4b_ok and t4c_ok
        if not t4_ok:
            all_pass = False
        print(
            ("PASS" if t4_ok else "FAIL")
            + " 4: expected codes 3, 2, 2;"
            + " got " + str(t4a_ok) + ", " + str(t4b_ok)
            + ", " + str(t4c_ok)
        )

        if all_pass:
            print("AUTOTEST 4/4")
        return 0 if all_pass else 1
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
