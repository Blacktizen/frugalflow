import os
import sys
import datetime
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import chain_rules

DIRS = ["raw", "01-context", "02-decisions", "03-measures", "04-pitfalls", "05-reference"]

SCHEMA = "# SCHEMA - the rules of {name}'s memory\n\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n\n## Rules\n- \u26d4\u26d4 One fact lives in one place: link to it, never copy it.\n- \u26d4\u26d4 raw/ is immutable: a source is never edited.\n- \u26d4 log.md is append-only and sealed: add entries with journal_add.py, never edit one.\n- \u26d4 Every live page is listed in index.md, every raw/ file is cited in sources.md.\n- \u2b50\u2b50 Before writing, restate the bearing lines of the required pages (reading_gate.py).\n"
OVERVIEW = "# {name} - where we stand\nupdated: {today}\n\n- \u2b50\u2b50 Vault created on {today}. Nothing decided yet.\n"
TODO = "# {name} - todo\n\nEach line says who decides: (me) or (operator).\n\n- [ ] (operator) Describe the project in overview.md.\n"
INDEX = "# Index\n\n- [[SCHEMA]] the rules\n- [[overview]] where we stand\n- [[todo]] the only list\n- [[log]] the sealed log\n- [[sources]] every raw file\n"
SOURCES = "# Sources\n\nEvery file of raw/ is cited here by its name.\n"
LOG_HEAD = "# Log - append-only, sealed\n\n"

USAGE = "usage: vault_new.py --root DIR --name NAME [--today YYYY-MM-DD] | --notice | --autotest"

NOTICE = (
    "NAME      vault_new.py - mounts a new project's memory vault in one command: folders, rules, todo, sealed log, index and sources.\n"
    "READS     --root, --name, --today (default: today's date).\n"
    "WRITES    <root>/vault and nothing else; a vault that exists and is not empty is refused, nothing written. Exit 0 created, 2 usage, 3 refused.\n"
    "EXAMPLE   python3 vault_new.py --root ~/projects/demo --name demo\n"
    "PITFALLS  2026-09-22 vaults made by hand forgot the todo or the index, and the closing check failed on day one.\n"
    "          Every vault now starts complete, with a sealed log, and passes vault_check.py as created."
)


def templates(name, today):
    """Return a dict of relative-path to content for all 12 vault files."""
    d = {}
    d["SCHEMA.md"] = SCHEMA.replace("{name}", name).replace("{today}", today)
    d["overview.md"] = OVERVIEW.replace("{name}", name).replace("{today}", today)
    d["todo.md"] = TODO.replace("{name}", name).replace("{today}", today)
    d["index.md"] = INDEX.replace("{name}", name).replace("{today}", today)
    d["sources.md"] = SOURCES.replace("{name}", name).replace("{today}", today)
    d["log.md"] = LOG_HEAD + chain_rules.render(
        chain_rules.GENESIS, today + " 00:00", "setup",
        [("Decision", "vault created by vault_new.py")])
    for dir_name in DIRS:
        d[dir_name + "/.keep"] = ""
    return d


def create(root, name, today):
    """Create the vault under root/vault. Raise FileExistsError if vault is non-empty."""
    vault = os.path.join(root, "vault")
    if os.path.isdir(vault) and os.listdir(vault):
        raise FileExistsError(vault)
    files = templates(name, today)
    for rel_path, content in files.items():
        full_path = os.path.join(vault, rel_path)
        parent = os.path.dirname(full_path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as f:
            f.write(content)
    return sorted(files.keys())


def run_autotest():
    """Run the 5 acceptance tests and exit 0 or 1."""
    R = tempfile.mkdtemp()
    passed = 0
    total = 5
    try:
        # --- Test 1: templates structure and content ---
        t = templates("demo", "2026-09-26")
        cond1 = (
            len(t) == 12
            and "raw/.keep" in t
            and t["overview.md"].startswith("# demo - where we stand\nupdated: 2026-09-26\n")
            and "{" not in t["SCHEMA.md"]
            and chain_rules.verify(t["log.md"]) == (True, 1, None, "")
        )
        if cond1:
            print("PASS 1: expected=12 keys, no brace, sealed log ok; obtained=ok")
            passed += 1
        else:
            print("FAIL 1: expected=12 keys, no brace, sealed log ok; obtained=len="
                  + str(len(t)) + " raw_keep=" + str("raw/.keep" in t)
                  + " brace=" + str("{" in t["SCHEMA.md"])
                  + " verify=" + str(chain_rules.verify(t["log.md"])))

        # --- Test 2: create writes 12 files, correct structure ---
        R2 = os.path.join(R, "t2")
        os.makedirs(R2)
        try:
            res2 = create(R2, "demo", "2026-09-26")
            exp2_list = sorted(templates("demo", "2026-09-26"))
            schema_ok = os.path.isfile(os.path.join(R2, "vault", "SCHEMA.md"))
            keep_ok = os.path.isfile(os.path.join(R2, "vault", "05-reference", ".keep"))
            cond2 = (len(res2) == 12 and res2 == exp2_list and schema_ok and keep_ok)
            if cond2:
                print("PASS 2: expected=12 paths, SCHEMA.md and .keep exist; obtained=ok")
                passed += 1
            else:
                print("FAIL 2: expected=12 paths, SCHEMA.md and .keep exist; obtained=len="
                      + str(len(res2)) + " match=" + str(res2 == exp2_list)
                      + " schema=" + str(schema_ok) + " keep=" + str(keep_ok))
        except Exception as e:
            print("FAIL 2: expected=12 paths, SCHEMA.md and .keep exist; obtained=exception " + repr(e))

        # --- Test 3: non-empty vault is refused without modification ---
        R3 = os.path.join(R, "t3")
        vault3 = os.path.join(R3, "vault")
        os.makedirs(vault3)
        with open(os.path.join(vault3, "notes.md"), "w", encoding="utf-8") as f:
            f.write("mine\n")
        try:
            create(R3, "demo", "2026-09-26")
            raised = False
        except FileExistsError:
            raised = True
        listdir_ok = os.listdir(vault3) == ["notes.md"]
        with open(os.path.join(vault3, "notes.md"), "r", encoding="utf-8") as f:
            content_ok = f.read() == "mine\n"
        cond3 = raised and listdir_ok and content_ok
        if cond3:
            print("PASS 3: expected=FileExistsError, vault untouched; obtained=ok")
            passed += 1
        else:
            print("FAIL 3: expected=FileExistsError, vault untouched; obtained=raised="
                  + str(raised) + " listdir=" + str(os.listdir(vault3))
                  + " content_ok=" + str(content_ok))

        # --- Test 4: subprocess created then refused ---
        R4 = os.path.join(R, "t4")
        os.makedirs(R4)
        script = os.path.abspath(__file__)
        cmd4 = [sys.executable, script, "--root", R4, "--name", "demo", "--today", "2026-09-26"]
        p4a = subprocess.run(cmd4, capture_output=True, text=True)
        vault4 = os.path.join(R4, "vault")
        exp4a_out = "CREATED 12 files in " + vault4 + "\n"
        cond4a = (p4a.returncode == 0 and p4a.stdout == exp4a_out)
        if cond4a:
            p4b = subprocess.run(cmd4, capture_output=True, text=True)
            exp4b_out = "REFUSED " + vault4 + " is not empty: nothing written\n"
            cond4b = (p4b.returncode == 3 and p4b.stdout == exp4b_out)
            if cond4b:
                print("PASS 4: expected=code 0 CREATED then code 3 REFUSED; obtained=ok")
                passed += 1
            else:
                print("FAIL 4: expected=code 3, REFUSED; obtained=code="
                      + str(p4b.returncode) + " out=" + repr(p4b.stdout))
        else:
            print("FAIL 4: expected=code 0, CREATED; obtained=code="
                  + str(p4a.returncode) + " out=" + repr(p4a.stdout))

        # --- Test 5: notice, usage with no args, missing --name ---
        R5 = os.path.join(R, "t5")
        os.makedirs(R5)
        p5a = subprocess.run([sys.executable, script, "--notice"], capture_output=True, text=True)
        cond5a = (p5a.returncode == 0 and p5a.stdout.startswith("NAME      vault_new.py"))
        p5b = subprocess.run([sys.executable, script], capture_output=True, text=True)
        cond5b = (p5b.returncode == 2 and p5b.stdout == USAGE + "\n")
        p5c = subprocess.run([sys.executable, script, "--root", R5], capture_output=True, text=True)
        cond5c = (p5c.returncode == 2)
        cond5 = cond5a and cond5b and cond5c
        if cond5:
            print("PASS 5: expected=notice 0, no-arg 2, missing-name 2; obtained=ok")
            passed += 1
        else:
            print("FAIL 5: expected=notice 0, no-arg 2, missing-name 2; obtained=notice_code="
                  + str(p5a.returncode) + " noarg_code=" + str(p5b.returncode)
                  + " noarg_out=" + repr(p5b.stdout) + " missing_code=" + str(p5c.returncode))
    finally:
        shutil.rmtree(R)

    if passed == total:
        sys.exit(0)
    else:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if args == ["--autotest"]:
        run_autotest()
        return
    if args == ["--notice"]:
        print(NOTICE)
        sys.exit(0)

    root = None
    name = None
    today = None
    i = 0
    while i < len(args):
        if args[i] == "--root":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            root = args[i]
        elif args[i] == "--name":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            name = args[i]
        elif args[i] == "--today":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            today = args[i]
        else:
            print(USAGE)
            sys.exit(2)
        i += 1

    if root is None or name is None:
        print(USAGE)
        sys.exit(2)

    if today is None:
        today = datetime.date.today().isoformat()

    vault = os.path.join(root, "vault")
    try:
        create(root, name, today)
        print("CREATED 12 files in " + vault)
        sys.exit(0)
    except FileExistsError:
        print("REFUSED " + vault + " is not empty: nothing written")
        sys.exit(3)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "vault_new", sys.argv[1:])
