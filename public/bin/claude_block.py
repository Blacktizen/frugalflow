import sys
import os
import subprocess

BEGIN = "<!-- FRUGALFLOW begin -->"
END = "<!-- FRUGALFLOW end -->"


class BlockError(ValueError):
    pass


def _line_bounds(text, index):
    start = text.rfind("\n", 0, index) + 1
    end = text.find("\n", index)
    if end == -1:
        end = len(text)
    return start, end


def find_block(text):
    n_begin = text.count(BEGIN)
    n_end = text.count(END)
    if n_begin == 0 and n_end == 0:
        return None
    if n_begin != 1 or n_end != 1:
        raise BlockError("block markers must appear once or not at all")
    begin_at = text.find(BEGIN)
    end_at = text.find(END)
    if end_at < begin_at:
        raise BlockError("END marker precedes BEGIN marker")
    for index, marker in ((begin_at, BEGIN), (end_at, END)):
        line_start, line_end = _line_bounds(text, index)
        if text[line_start:line_end] != marker:
            raise BlockError("a marker is not alone on its line")
    start = text.rfind("\n", 0, begin_at) + 1
    end = text.find("\n", end_at)
    if end == -1:
        end = len(text)
    else:
        end += 1
    return start, end


def render_block(body):
    if body.endswith("\n"):
        return BEGIN + "\n" + body + END + "\n"
    return BEGIN + "\n" + body + "\n" + END + "\n"


def insert_block(text, body):
    found = find_block(text)
    if found is not None:
        start, end = found
        return text[:start] + render_block(body) + text[end:]
    if text == "":
        return render_block(body)
    return text + "\n" + render_block(body)


def remove_block(text):
    found = find_block(text)
    if found is None:
        return text, False
    start, end = found
    before = text[:start]
    after = text[end:]
    if start > 0:
        before = before[:-1]
    return before + after, True


def block_body(bin_dir):
    examples_dir = os.path.join(os.path.dirname(bin_dir), "examples")
    return (
        "## FrugalFlow\n"
        "FrugalFlow is installed. Its hooks enforce the rules; this block only tells you they exist.\n"
        "- Check its state: python3 {BIN}/frugalflow.py doctor\n"
        "- Code beyond a few lines is written by a delegated model, not by you: python3 {BIN}/delegate.py --role code --file <task file> --out <file> (task template: {EX}/brief_template.md).\n"
        "- Never shrink or split a file to slip under the guard threshold: that is working around it.\n"
        "- Check a task file before delegating: python3 {BIN}/frugalflow.py lint <task file>. Every refusal names its fix: never read FrugalFlow source code.\n"
        "- Change a setting through the tool, never by hand: python3 {BIN}/frugalflow.py config\n"
        "- A refusal from the guard names its fix: follow it, never work around it.\n"
    ).replace("{BIN}", bin_dir).replace("{EX}", examples_dir)


NOTICE = (
    "NAME      claude_block.py - finds, renders, inserts and removes the FrugalFlow block of a CLAUDE.md.\n"
    "READS     nothing: pure module; it reads the text it is given.\n"
    "WRITES    nothing: the functions return the new text, they never write it.\n"
    "EXAMPLE   python3 claude_block.py --notice\n"
    "PITFALLS  2026-10-03 a marker glued to other text was kept in silence; find_block now refuses a line that is not exactly the marker.\n"
)


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    print("usage: claude_block.py --notice | --autotest")
    return 2


def _autotest():
    body = "## FrugalFlow\nhello\n"
    results = []

    # Test 1
    ok = True
    detail = ""
    for t in ("", "\n", "a", "a\n"):
        got, changed = remove_block(insert_block(t, body))
        if got != t or changed is not True:
            ok = False
            detail = "t=%r got=%r changed=%r" % (t, got, changed)
            break
    results.append(("1 remove_block(insert_block(t)) == t for '', '\\n', 'a', 'a\\n'", ok, detail))

    # Test 2
    got2 = insert_block("a", body)
    ok = got2 == "a\n" + render_block(body) and insert_block("", body) == render_block(body)
    results.append(("2 insert_block keeps the user text verbatim and adds one separator newline", ok,
                    "got2=%r" % got2 if not ok else ""))

    # Test 3
    once = insert_block("a", body)
    twice = insert_block(once, body)
    ok = twice == once
    results.append(("3 insert_block is idempotent", ok, "once=%r twice=%r" % (once, twice) if not ok else ""))

    # Test 4
    bad = [
        "x\n" + BEGIN + "\n" + BEGIN + "\n" + END + "\n",
        BEGIN + "\nbody\n",
        END + "\n" + BEGIN + "\n",
        "text " + BEGIN + "\n" + END + "\n",
    ]
    ok = True
    detail = ""
    for b in bad:
        try:
            find_block(b)
        except BlockError:
            continue
        ok = False
        detail = "no BlockError for %r" % b
        break
    results.append(("4 find_block refuses malformed blocks", ok, detail))

    # Test 5
    ok = (render_block("x\n") == BEGIN + "\n" + "x\n" + END + "\n"
          and render_block("x") == BEGIN + "\n" + "x\n" + END + "\n"
          and find_block("plain text") is None)
    results.append(("5 render_block places BEGIN, body, END on their own lines; no marker means None", ok, ""))

    # Test 6
    r = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    ok = r.returncode == 0 and r.stdout.startswith("NAME      claude_block.py")
    results.append(("6 --notice prints the notice", ok, "rc=%d stdout=%r" % (r.returncode, r.stdout) if not ok else ""))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + (" | " + detail if detail else ""))
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "claude_block", sys.argv[1:])
