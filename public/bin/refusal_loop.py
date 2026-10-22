#!/usr/bin/env python3
"""refusal_loop.py - the refusal loop of a user project: new refusals of its tools become todo lines, and a commit is blocked while a tool logs no refusal or the project bench has a false refusal, a hole or a tool without a case."""

import json
import os
import shutil
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import exit_log

USAGE = "usage: refusal_loop.py todo|check --project DIR | --notice | --autotest"

NOTICE = (
    "NAME      refusal_loop.py - the refusal loop of a user project: new refusals of its tools become todo lines, and a commit is blocked while a tool logs no refusal or the project bench has a false refusal, a hole or a tool without a case.\n"
    "READS     --project DIR: DIR/bin/*.py, DIR/vault/todo.md, DIR/bench/cases.json; the block logs in FRUGALFLOW_HOME/blocks, else ~/.frugalflow/blocks.\n"
    "WRITES    todo: new lines at the end of DIR/vault/todo.md, then TODO n; check: one line per defect, then COMMIT ALLOWED (0) or COMMIT BLOCKED n (1). Exit 2 on usage, 3 when the todo is missing.\n"
    "EXAMPLE   python3 refusal_loop.py check --project ~/projects/demo\n"
    "PITFALLS  2026-10-05 a tool built without a refusal log hid its false refusals for weeks; check now refuses a tool whose entry point does not go through exit_log.\n"
)


def home_dir():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")


def project_tools(project_dir):
    bin_dir = os.path.join(project_dir, "bin")
    if not os.path.isdir(bin_dir):
        return []
    return sorted(f[:-3] for f in os.listdir(bin_dir) if f.endswith(".py"))


def todo_line(block_id, tool, rule):
    return (
        "- [ ] refusal " + str(block_id) + " " + str(tool) + " " + str(rule)
        + ": false refusal -> fix the tool and add a pass case to bench/cases.json;"
        " true refusal -> add a refuse case"
    )


def read_block_lines(home, tool):
    path = os.path.join(home, "blocks", tool + ".jsonl")
    if not os.path.isfile(path):
        return []
    records = []
    try:
        with open(path, "r", encoding="utf-8") as f:
            raw = f.readlines()
    except OSError:
        return []
    for line in raw:
        line = line.strip()
        if not line:
            continue
        try:
            record = json.loads(line)
        except ValueError:
            continue
        if isinstance(record, dict) and record.get("kind") == "block":
            records.append(record)
    return records


def run_todo(project_dir):
    todo_path = os.path.join(project_dir, "vault", "todo.md")
    if not os.path.isfile(todo_path):
        print("NO TODO: " + todo_path)
        return 3
    with open(todo_path, "r", encoding="utf-8") as f:
        text = f.read()
    home = home_dir()
    new_lines = []
    seen = set()
    for tool in project_tools(project_dir):
        for record in read_block_lines(home, tool):
            block_id = record.get("id")
            if not isinstance(block_id, str) or block_id == "":
                continue
            if block_id in text or block_id in seen:
                continue
            seen.add(block_id)
            new_lines.append(todo_line(block_id, tool, record.get("rule")))
    if new_lines:
        content = text
        if content and not content.endswith("\n"):
            content += "\n"
        content += "".join(line + "\n" for line in new_lines)
        with open(todo_path, "w", encoding="utf-8") as f:
            f.write(content)
    print("TODO " + str(len(new_lines)) + " new refusal(s)")
    return 0


def run_check(project_dir):
    defects = []
    bin_dir = os.path.join(project_dir, "bin")
    py_names = [f for f in sorted(os.listdir(bin_dir)) if f.endswith(".py")] if os.path.isdir(bin_dir) else []
    for name in py_names:
        try:
            with open(os.path.join(bin_dir, name), "r", encoding="utf-8") as f:
                source = f.read()
        except OSError:
            continue
        if 'if __name__ == "__main__":' in source and "exit_log.run(" not in source:
            defects.append("NO REFUSAL LOG " + name)

    cases_path = os.path.join(project_dir, "bench", "cases.json")
    cases = None
    try:
        with open(cases_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            cases = data
    except (OSError, ValueError):
        cases = None
    if cases is None:
        defects.append("NO BENCH: " + cases_path)
        cases = []

    replay_home = tempfile.mkdtemp()
    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = replay_home
    try:
        for case in cases:
            if not isinstance(case, dict):
                continue
            case_id = case.get("id")
            tool = case.get("tool")
            argv = case.get("argv") or []
            expected = case.get("expected")
            tool_path = os.path.join(bin_dir, str(tool) + ".py")
            if not os.path.isfile(tool_path):
                defects.append("NOT RUN " + str(case_id))
                continue
            try:
                result = subprocess.run(
                    [sys.executable, tool_path] + list(argv),
                    input="",
                    cwd=project_dir,
                    env=env,
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
            except (OSError, subprocess.TimeoutExpired):
                defects.append("NOT RUN " + str(case_id))
                continue
            got = "refuse" if result.returncode != 0 else "pass"
            if expected == "pass" and got == "refuse":
                defects.append("FALSE REFUSAL " + str(case_id))
            elif expected == "refuse" and got == "pass":
                defects.append("HOLE " + str(case_id))
    finally:
        shutil.rmtree(replay_home, ignore_errors=True)

    benched = {case.get("tool") for case in cases if isinstance(case, dict)}
    for tool in project_tools(project_dir):
        if tool not in benched:
            defects.append("NO BENCH CASE " + tool)

    for defect in defects:
        print(defect)
    if defects:
        print("COMMIT BLOCKED " + str(len(defects)))
        return 1
    print("COMMIT ALLOWED")
    return 0


# --- fixtures for autotest ---

BIN_DIR = os.path.dirname(os.path.abspath(__file__))

GOOD_SRC = (
    "import sys\n"
    "sys.path.insert(0, " + repr(BIN_DIR) + ")\n"
    "import exit_log\n"
    "def main(argv):\n"
    "    if argv and argv[0] == \"--bad\":\n"
    "        print(\"REFUSED: bad\")\n"
    "        return 2\n"
    "    print(\"OK\")\n"
    "    return 0\n"
    "if __name__ == \"__main__\":\n"
    "    exit_log.run(main, \"good\", sys.argv[1:])\n"
)

BARE_SRC = "import sys\nif __name__ == \"__main__\":\n    sys.exit(0)\n"

GOOD_BLOCKS = (
    '{"kind": "block", "id": "a1", "tool": "good", "rule": "exit_2", "input": {}}\n'
    '{"kind": "block", "id": "a2", "tool": "good", "rule": "exit_2", "input": {}}\n'
)

OTHER_BLOCKS = '{"kind": "block", "id": "b1", "tool": "other", "rule": "exit_1", "input": {}}\n'

JUST_BENCH = json.dumps([
    {"id": "g-ok", "tool": "good", "argv": [], "expected": "pass"},
    {"id": "g-bad", "tool": "good", "argv": ["--bad"], "expected": "refuse"},
])

SWAPPED_BENCH = json.dumps([
    {"id": "g-ok", "tool": "good", "argv": [], "expected": "refuse"},
    {"id": "g-bad", "tool": "good", "argv": ["--bad"], "expected": "pass"},
])

GHOST_BENCH = json.dumps([
    {"id": "g-ok", "tool": "good", "argv": [], "expected": "pass"},
    {"id": "g-bad", "tool": "good", "argv": ["--bad"], "expected": "refuse"},
    {"id": "g-ghost", "tool": "ghost", "argv": [], "expected": "refuse"},
])


def _make_project(root, tools, todo_text, bench):
    os.makedirs(os.path.join(root, "bin"), exist_ok=True)
    for name, source in tools:
        with open(os.path.join(root, "bin", name + ".py"), "w", encoding="utf-8") as f:
            f.write(source)
    if todo_text is not None:
        os.makedirs(os.path.join(root, "vault"), exist_ok=True)
        with open(os.path.join(root, "vault", "todo.md"), "w", encoding="utf-8") as f:
            f.write(todo_text)
    if bench is not None:
        os.makedirs(os.path.join(root, "bench"), exist_ok=True)
        with open(os.path.join(root, "bench", "cases.json"), "w", encoding="utf-8") as f:
            f.write(bench)


def _make_home(root):
    os.makedirs(os.path.join(root, "blocks"), exist_ok=True)
    with open(os.path.join(root, "blocks", "good.jsonl"), "w", encoding="utf-8") as f:
        f.write(GOOD_BLOCKS)
    with open(os.path.join(root, "blocks", "other.jsonl"), "w", encoding="utf-8") as f:
        f.write(OTHER_BLOCKS)


def _run_cli(args, home):
    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home
    result = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True,
        text=True,
        env=env,
    )
    return result.returncode, result.stdout


def _autotest():
    results = []

    def proof(number, ok, expected, got):
        if ok:
            results.append("PASS " + str(number) + ": expected=" + expected + " got=" + got)
        else:
            results.append("FAIL " + str(number) + ": expected=" + expected + " got=" + got)

    line_a1 = todo_line("a1", "good", "exit_2")
    line_a2 = todo_line("a2", "good", "exit_2")

    # --- Proof 1: todo adds a1 and a2, never b1; a second run adds nothing ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", JUST_BENCH)
        _make_home(home)
        code, out = _run_cli(["todo", "--project", project], home)
        with open(os.path.join(project, "vault", "todo.md"), "r", encoding="utf-8") as f:
            todo = f.read()
        ok = (
            code == 0
            and out == "TODO 2 new refusal(s)\n"
            and line_a1 in todo and line_a2 in todo
            and "b1" not in todo
        )
        code2, out2 = _run_cli(["todo", "--project", project], home)
        with open(os.path.join(project, "vault", "todo.md"), "r", encoding="utf-8") as f:
            todo2 = f.read()
        ok = ok and code2 == 0 and out2 == "TODO 0 new refusal(s)\n" and todo2 == todo
        proof(1, ok, "code 0, TODO 2 then TODO 0, a1+a2 lines, no b1, no duplicate",
              "code " + str(code) + "/" + str(code2) + ", out " + repr(out) + "/" + repr(out2) + ", b1=" + str("b1" in todo2))

    # --- Proof 2: todo without a todo file: code 3 ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], None, JUST_BENCH)
        _make_home(home)
        code, out = _run_cli(["todo", "--project", project], home)
        ok = code == 3 and out.startswith("NO TODO: ")
        proof(2, ok, "code 3, NO TODO: line", "code " + str(code) + ", out " + repr(out))

    # --- Proof 3: check with an unlogged tool: 2 defects, code 1 ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC), ("bare", BARE_SRC)], "# todo\n", JUST_BENCH)
        _make_home(home)
        code, out = _run_cli(["check", "--project", project], home)
        lines = out.splitlines()
        ok = (
            code == 1
            and "NO REFUSAL LOG bare.py" in lines
            and "NO BENCH CASE bare" in lines
            and lines[-1] == "COMMIT BLOCKED 2"
        )
        proof(3, ok, "code 1, NO REFUSAL LOG bare.py, NO BENCH CASE bare, COMMIT BLOCKED 2",
              "code " + str(code) + ", lines " + repr(lines))

    # --- Proof 4: check with the just bench on good alone: allowed, code 0 ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", JUST_BENCH)
        _make_home(home)
        code, out = _run_cli(["check", "--project", project], home)
        ok = code == 0 and out.splitlines()[-1] == "COMMIT ALLOWED"
        proof(4, ok, "code 0, COMMIT ALLOWED", "code " + str(code) + ", out " + repr(out))

    # --- Proof 5: swapped expectations: HOLE and FALSE REFUSAL, code 1 ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", SWAPPED_BENCH)
        _make_home(home)
        code, out = _run_cli(["check", "--project", project], home)
        lines = out.splitlines()
        ok = code == 1 and "HOLE g-ok" in lines and "FALSE REFUSAL g-bad" in lines and lines[-1] == "COMMIT BLOCKED 2"
        proof(5, ok, "code 1, HOLE g-ok, FALSE REFUSAL g-bad, COMMIT BLOCKED 2",
              "code " + str(code) + ", lines " + repr(lines))

    # --- Proof 6: a case naming an absent tool: NOT RUN ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", GHOST_BENCH)
        _make_home(home)
        code, out = _run_cli(["check", "--project", project], home)
        lines = out.splitlines()
        ok = code == 1 and "NOT RUN g-ghost" in lines
        proof(6, ok, "code 1, NOT RUN g-ghost", "code " + str(code) + ", lines " + repr(lines))

    # --- Proof 7: no bench file: NO BENCH ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", None)
        _make_home(home)
        code, out = _run_cli(["check", "--project", project], home)
        lines = out.splitlines()
        ok = code == 1 and any(line.startswith("NO BENCH: ") for line in lines)
        proof(7, ok, "code 1, NO BENCH: line", "code " + str(code) + ", lines " + repr(lines))

    # --- Proof 8: a replay never writes into the real block log ---
    with tempfile.TemporaryDirectory() as tmp:
        project = os.path.join(tmp, "proj")
        home = os.path.join(tmp, "home")
        _make_project(project, [("good", GOOD_SRC)], "# todo\n", JUST_BENCH)
        _make_home(home)
        _run_cli(["check", "--project", project], home)
        with open(os.path.join(home, "blocks", "good.jsonl"), "r", encoding="utf-8") as f:
            after = f.read()
        ok = after == GOOD_BLOCKS
        proof(8, ok, "blocks/good.jsonl unchanged after check", "file " + repr(after))

    # --- Proof 9: --notice: code 0 ---
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _run_cli(["--notice"], tmp)
        ok = code == 0 and out.startswith("NAME      refusal_loop.py") and "PITFALLS" in out
        proof(9, ok, "code 0, notice starting NAME      refusal_loop.py",
              "code " + str(code) + ", out " + repr(out[:40]))

    # --- Proof 10: bad usage: code 2 and one exit_2 line in the tool's own log ---
    with tempfile.TemporaryDirectory() as tmp:
        code, out = _run_cli(["todo"], tmp)
        log_path = os.path.join(tmp, "blocks", "refusal_loop.jsonl")
        logged = False
        if os.path.isfile(log_path):
            with open(log_path, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line)
                    except ValueError:
                        continue
                    if record.get("kind") == "block" and record.get("rule") == "exit_2":
                        logged = True
        ok = code == 2 and out.startswith("usage: refusal_loop.py") and logged
        proof(10, ok, "code 2, usage line, exit_2 logged",
              "code " + str(code) + ", out " + repr(out) + ", logged=" + str(logged))

    for line in results:
        print(line)
    return 0 if all(line.startswith("PASS") for line in results) else 1


def main(argv):
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    if len(argv) == 3 and argv[0] in ("todo", "check") and argv[1] == "--project":
        if argv[0] == "todo":
            return run_todo(argv[2])
        return run_check(argv[2])
    print(USAGE)
    return 2


if __name__ == "__main__":
    exit_log.run(main, "refusal_loop", sys.argv[1:])
