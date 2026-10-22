#!/usr/bin/env python3
import json
import os
import re
import sys
import subprocess
import tempfile
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import block_rules

USAGE = "usage: block_log.py add --tool T --json FILE | replay --tool T --tool-version V [--timeout S] | report --tool T | --notice | --autotest"

NOTICE = (
    "NAME      block_log.py - one block log per refusing tool: appends the refused input, then the dated result of each replay; never erases.\n"
    "READS     FRUGALFLOW_HOME/blocks/<tool>.jsonl, else ~/.frugalflow/blocks/<tool>.jsonl; the JSON list given to add.\n"
    "WRITES    appended lines only, to that same file. Exits 0 on success, 2 on a bad argument or an unreadable input file.\n"
    "EXAMPLE   python3 block_log.py replay --tool guard --tool-version 1a2b3c4\n"
    "PITFALLS  2026-09-26 a refusal seen weeks ago may come from an older version of the tool: replay it today and write what happened next to it, never in its place."
)


def home_dir():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")


def log_path(home, tool):
    if not re.fullmatch(r"[a-z0-9_-]+", tool):
        raise ValueError("invalid tool name: " + tool)
    return os.path.join(home, "blocks", tool + ".jsonl")


def now():
    return datetime.datetime.now().astimezone().isoformat(timespec="seconds")


def read_log(home, tool):
    p = log_path(home, tool)
    if not os.path.isfile(p):
        return [], 0
    with open(p, "r", encoding="utf-8") as f:
        content = f.read()
    return block_rules.parse_lines(content)


def append(home, tool, records):
    p = log_path(home, tool)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        for r in records:
            f.write(json.dumps(r, ensure_ascii=False) + "\n")


def record_block(tool, rule, tool_input, reason, version, replay, source="live", home=None, when=None):
    if home is None:
        home = home_dir()
    if when is None:
        when = now()
    b = block_rules.make_block(tool, rule, tool_input, reason, when, version, replay, source)
    log_path(home, tool)
    append(home, tool, [b])
    return b


def add_blocks(home, tool, blocks):
    records, _ = read_log(home, tool)
    added = []
    duplicates = 0
    rejected = 0
    for b in blocks:
        if not isinstance(b, dict):
            rejected += 1
            continue
        if b.get("kind") != "block":
            rejected += 1
            continue
        if b.get("tool") != tool:
            rejected += 1
            continue
        if b.get("id") != block_rules.block_id(tool, b.get("input")):
            rejected += 1
            continue
        if b.get("replay") is not None and block_rules.check_replay(b["replay"]) != "":
            rejected += 1
            continue
        if block_rules.is_duplicate(records + added, b):
            duplicates += 1
            continue
        added.append(b)
    if added:
        append(home, tool, added)
    return (len(added), duplicates, rejected)


def run_replay(spec, timeout):
    env = dict(os.environ)
    env.update(spec.get("env") or {})
    try:
        result = subprocess.run(
            spec["argv"],
            input=spec.get("stdin"),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return (True, result.returncode, result.stdout)
    except (FileNotFoundError, PermissionError, OSError, subprocess.TimeoutExpired):
        return (False, None, "")


def replay_tool(home, tool, version, timeout):
    records, _ = read_log(home, tool)
    latest = block_rules.latest(records)
    replays = []
    counters = {"reproduced": 0, "no_longer_reproduced": 0, "not_replayable": 0}
    for bid, state in latest.items():
        spec = state["block"]["replay"]
        if spec is None:
            outcome = "not_replayable"
            rc = None
            detail = "no replay command kept"
        else:
            ran, rc, out = run_replay(spec, timeout)
            outcome = block_rules.judge(spec, ran, rc, out)
            detail = out.strip() if ran else "could not run within the time limit or not found"
        replay_line = block_rules.make_replay(bid, now(), version, outcome, rc, detail)
        replays.append(replay_line)
        counters[outcome] = counters.get(outcome, 0) + 1
    if replays:
        append(home, tool, replays)
    return (len(replays), counters)


def report_lines(home, tool):
    records, bad = read_log(home, tool)
    st = block_rules.latest(records)
    s = block_rules.summary(records)
    nb = sum(1 for r in records if r.get("kind") == "block")
    return [
        f"tool {tool}: {nb} blocks, {len(st)} distinct, {bad} unreadable lines",
        f"reproduced: {s['reproduced']}",
        f"no_longer_reproduced: {s['no_longer_reproduced']}",
        f"not_replayable: {s['not_replayable']}",
        f"never_replayed: {s['never_replayed']}",
    ]


def _cli_add(rest):
    tool = None
    json_file = None
    i = 0
    while i < len(rest):
        if rest[i] == "--tool" and i + 1 < len(rest):
            tool = rest[i + 1]
            i += 2
        elif rest[i] == "--json" and i + 1 < len(rest):
            json_file = rest[i + 1]
            i += 2
        else:
            print(USAGE)
            sys.exit(2)
    if tool is None or json_file is None:
        print(USAGE)
        sys.exit(2)
    try:
        log_path(home_dir(), tool)
    except ValueError:
        print(USAGE)
        sys.exit(2)
    try:
        with open(json_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        print(f"cannot read {json_file}")
        sys.exit(2)
    if not isinstance(data, list):
        print(f"cannot read {json_file}")
        sys.exit(2)
    a, d, r = add_blocks(home_dir(), tool, data)
    print(f"added {a}, duplicates {d}, rejected {r}")
    sys.exit(0)


def _cli_replay(rest):
    tool = None
    tool_version = None
    timeout = 20.0
    i = 0
    while i < len(rest):
        if rest[i] == "--tool" and i + 1 < len(rest):
            tool = rest[i + 1]
            i += 2
        elif rest[i] == "--tool-version" and i + 1 < len(rest):
            tool_version = rest[i + 1]
            i += 2
        elif rest[i] == "--timeout" and i + 1 < len(rest):
            timeout = float(rest[i + 1])
            i += 2
        else:
            print(USAGE)
            sys.exit(2)
    if tool is None or tool_version is None:
        print(USAGE)
        sys.exit(2)
    try:
        log_path(home_dir(), tool)
    except ValueError:
        print(USAGE)
        sys.exit(2)
    n, c = replay_tool(home_dir(), tool, tool_version, timeout)
    print(f"replayed {n}: reproduced {c['reproduced']}, no_longer_reproduced {c['no_longer_reproduced']}, not_replayable {c['not_replayable']}")
    sys.exit(0)


def _cli_report(rest):
    tool = None
    i = 0
    while i < len(rest):
        if rest[i] == "--tool" and i + 1 < len(rest):
            tool = rest[i + 1]
            i += 2
        else:
            print(USAGE)
            sys.exit(2)
    if tool is None:
        print(USAGE)
        sys.exit(2)
    try:
        log_path(home_dir(), tool)
    except ValueError:
        print(USAGE)
        sys.exit(2)
    for line in report_lines(home_dir(), tool):
        print(line)
    sys.exit(0)


def _autotest():
    PY = sys.executable
    S_RC = {"argv": [PY, "-c", "import sys; sys.exit(5)"], "stdin": None, "blocked_if": {"rc": 5}}
    S_OK = {"argv": [PY, "-c", "print('ok')"], "stdin": None, "blocked_if": {"stdout_contains": "deny"}}
    S_MISSING = {"argv": ["/nonexistent/tool-xyz"], "stdin": None, "blocked_if": {"rc": 5}}
    S_SLOW = {"argv": [PY, "-c", "import time; time.sleep(5)"], "stdin": None, "blocked_if": {"rc": 5}}
    S_ENV = {"argv": [PY, "-c", "import os; print(os.environ.get('ZZ_REPLAY'))"], "stdin": None, "env": {"ZZ_REPLAY": "deny"}, "blocked_if": {"stdout_contains": "deny"}}

    def MK(n, spec):
        return block_rules.make_block("guard", "r", {"command": "c" + str(n)}, "refused", "2026-09-01T00:00:00+02:00", "v1", spec, "history")

    def RUN(home, args):
        env = dict(os.environ)
        env["FRUGALFLOW_HOME"] = home
        result = subprocess.run(
            [sys.executable, os.path.abspath(__file__)] + args,
            capture_output=True,
            text=True,
            env=env,
        )
        return (result.returncode, result.stdout)

    def LOG(home):
        p = os.path.join(home, "blocks", "guard.jsonl")
        if not os.path.isfile(p):
            return []
        with open(p, "r", encoding="utf-8") as f:
            return [json.loads(line) for line in f if line.strip()]

    def JS(home, records):
        p = os.path.join(home, "in.json")
        with open(p, "w", encoding="utf-8") as f:
            json.dump(records, f)
        return p

    results = []

    # --- Proof 1 ---
    with tempfile.TemporaryDirectory() as h:
        ok = True
        msg = ""
        try:
            record_block("guard", "shell_write", {"command": "x"}, "no", "v1", None, home=h)
            log = LOG(h)
            if len(log) != 1:
                ok = False
                msg = f"expected 1 line, got {len(log)}"
            else:
                if log[0].get("kind") != "block":
                    ok = False
                    msg = f"kind={log[0].get('kind')}"
                if log[0].get("id") != block_rules.block_id("guard", {"command": "x"}):
                    ok = False
                    msg = f"id={log[0].get('id')}"
            try:
                record_block("Bad/Name", "r", {}, "", None, None, home=h)
                ok = False
                msg = "ValueError not raised"
            except ValueError:
                pass
            log2 = LOG(h)
            if len(log2) != 1:
                ok = False
                msg = f"expected 1 line after ValueError, got {len(log2)}"
        except Exception as e:
            ok = False
            msg = str(e)
        if ok:
            results.append("PASS 1: record_block direct + ValueError on bad tool")
        else:
            results.append(f"FAIL 1: {msg}")

    # --- Proof 2 ---
    with tempfile.TemporaryDirectory() as h:
        ok = True
        msg = ""
        p = JS(h, [MK(1, S_RC), MK(2, None), dict(MK(3, None), id="0000000000000000")])
        code, stdout = RUN(h, ["add", "--tool", "guard", "--json", p])
        expected = "added 2, duplicates 0, rejected 1\n"
        if code != 0:
            ok = False
            msg = f"code={code}"
        elif stdout != expected:
            ok = False
            msg = f"got {stdout!r}"
        else:
            code2, stdout2 = RUN(h, ["add", "--tool", "guard", "--json", p])
            expected2 = "added 0, duplicates 2, rejected 1\n"
            if code2 != 0:
                ok = False
                msg = f"second code={code2}"
            elif stdout2 != expected2:
                ok = False
                msg = f"second got {stdout2!r}"
            else:
                log = LOG(h)
                if len(log) != 2:
                    ok = False
                    msg = f"log has {len(log)} lines, expected 2"
        if ok:
            results.append("PASS 2: add with duplicates and rejection")
        else:
            results.append(f"FAIL 2: {msg}")

    # --- Proof 3 ---
    with tempfile.TemporaryDirectory() as h:
        ok = True
        msg = ""
        p = JS(h, [MK(1, S_RC), MK(2, S_OK), MK(3, None), MK(4, S_MISSING)])
        RUN(h, ["add", "--tool", "guard", "--json", p])
        code, stdout = RUN(h, ["replay", "--tool", "guard", "--tool-version", "v2"])
        expected = "replayed 4: reproduced 1, no_longer_reproduced 1, not_replayable 2\n"
        if code != 0:
            ok = False
            msg = f"code={code}"
        elif stdout != expected:
            ok = False
            msg = f"got {stdout!r}"
        else:
            log = LOG(h)
            blocks = [r for r in log if r.get("kind") == "block"]
            replays = [r for r in log if r.get("kind") == "replay"]
            if len(blocks) != 4:
                ok = False
                msg = f"blocks={len(blocks)}"
            elif len(replays) != 4:
                ok = False
                msg = f"replays={len(replays)}"
            else:
                for rp in replays:
                    if rp.get("tool_version") != "v2":
                        ok = False
                        msg = f"tool_version={rp.get('tool_version')}"
                        break
        if ok:
            results.append("PASS 3: replay with mixed outcomes")
        else:
            results.append(f"FAIL 3: {msg}")

    # --- Proof 4 ---
    with tempfile.TemporaryDirectory() as h:
        ok = True
        msg = ""
        p = JS(h, [MK(1, S_SLOW), MK(2, S_ENV)])
        RUN(h, ["add", "--tool", "guard", "--json", p])
        code, stdout = RUN(h, ["replay", "--tool", "guard", "--tool-version", "v2", "--timeout", "1"])
        expected = "replayed 2: reproduced 1, no_longer_reproduced 0, not_replayable 1\n"
        if code != 0:
            ok = False
            msg = f"code={code}"
        elif stdout != expected:
            ok = False
            msg = f"got {stdout!r}"
        else:
            log = LOG(h)
            replays = [r for r in log if r.get("kind") == "replay"]
            slow_id = MK(1, S_SLOW)["id"]
            slow_replays = [r for r in replays if r.get("id") == slow_id]
            if not slow_replays:
                ok = False
                msg = "slow replay line not found"
            else:
                if slow_replays[0].get("outcome") != "not_replayable":
                    ok = False
                    msg = f"slow outcome={slow_replays[0].get('outcome')}"
                if slow_replays[0].get("rc") is not None:
                    ok = False
                    msg = f"slow rc={slow_replays[0].get('rc')}"
        if ok:
            results.append("PASS 4: replay with timeout and env")
        else:
            results.append(f"FAIL 4: {msg}")

    # --- Proof 5 ---
    with tempfile.TemporaryDirectory() as h:
        ok = True
        msg = ""
        p = JS(h, [MK(1, S_RC), MK(2, S_OK), MK(3, None), MK(4, S_MISSING)])
        RUN(h, ["add", "--tool", "guard", "--json", p])
        RUN(h, ["replay", "--tool", "guard", "--tool-version", "v2"])
        code, stdout = RUN(h, ["report", "--tool", "guard"])
        expected_report = (
            "tool guard: 4 blocks, 4 distinct, 0 unreadable lines\n"
            "reproduced: 1\n"
            "no_longer_reproduced: 1\n"
            "not_replayable: 2\n"
            "never_replayed: 0\n"
        )
        if code != 0:
            ok = False
            msg = f"report code={code}"
        elif stdout != expected_report:
            ok = False
            msg = f"report got {stdout!r}"
        else:
            code2, stdout2 = RUN(h, ["add", "--tool", "guard", "--json", os.path.join(h, "absent.json")])
            if code2 != 2:
                ok = False
                msg = f"absent code={code2}"
            elif not stdout2.startswith("cannot read "):
                ok = False
                msg = f"absent stdout={stdout2!r}"
            else:
                code3, stdout3 = RUN(h, ["--notice"])
                if code3 != 0:
                    ok = False
                    msg = f"notice code={code3}"
                elif not stdout3.startswith("NAME      block_log.py"):
                    ok = False
                    msg = f"notice stdout={stdout3!r}"
                else:
                    code4, stdout4 = RUN(h, [])
                    if code4 != 2:
                        ok = False
                        msg = f"noargs code={code4}"
                    elif not stdout4.startswith("usage: block_log.py add"):
                        ok = False
                        msg = f"noargs stdout={stdout4!r}"
        if ok:
            results.append("PASS 5: report + error paths + notice + no-args")
        else:
            results.append(f"FAIL 5: {msg}")

    for r in results:
        print(r)
    if all(r.startswith("PASS") for r in results):
        sys.exit(0)
    else:
        sys.exit(1)


def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        sys.exit(2)
    cmd = args[0]
    if cmd == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif cmd == "--autotest":
        _autotest()
    elif cmd == "add":
        _cli_add(args[1:])
    elif cmd == "replay":
        _cli_replay(args[1:])
    elif cmd == "report":
        _cli_report(args[1:])
    else:
        print(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    main()
