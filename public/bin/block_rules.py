#!/usr/bin/env python3
import json
import hashlib
import sys
import subprocess
import os

OUTCOMES = ("reproduced", "no_longer_reproduced", "not_replayable")


def block_id(tool, tool_input):
    return hashlib.sha256(
        json.dumps([tool, tool_input], sort_keys=True, ensure_ascii=False).encode("utf-8")
    ).hexdigest()[:16]


def check_replay(spec):
    if not isinstance(spec, dict):
        return "spec is not a dict"
    if "argv" not in spec:
        return "missing argv"
    argv = spec["argv"]
    if not isinstance(argv, list) or len(argv) == 0:
        return "argv must be a non-empty list"
    for item in argv:
        if not isinstance(item, str):
            return "argv elements must be str"
    stdin = spec.get("stdin")
    if stdin is not None and not isinstance(stdin, str):
        return "stdin must be None or str"
    env = spec.get("env")
    if env is not None:
        if not isinstance(env, dict):
            return "env must be a dict"
        for k, v in env.items():
            if not isinstance(k, str) or not isinstance(v, str):
                return "env keys and values must be str"
    if "blocked_if" not in spec:
        return "missing blocked_if"
    bi = spec["blocked_if"]
    if not isinstance(bi, dict):
        return "blocked_if must be a dict"
    if len(bi) != 1:
        return "blocked_if must have exactly one key"
    if "rc" in bi:
        if not isinstance(bi["rc"], int) or isinstance(bi["rc"], bool):
            return "rc value must be int"
    elif "stdout_contains" in bi:
        if not isinstance(bi["stdout_contains"], str) or bi["stdout_contains"] == "":
            return "stdout_contains must be a non-empty str"
    else:
        return "blocked_if key must be rc or stdout_contains"
    return ""


def make_block(tool, rule, tool_input, reason, when, version, replay, source):
    if not isinstance(tool, str) or tool == "":
        raise ValueError("tool must be a non-empty str")
    if not isinstance(when, str) or when == "":
        raise ValueError("when must be a non-empty str")
    if replay is not None and check_replay(replay) != "":
        raise ValueError("invalid replay spec")
    return {
        "kind": "block",
        "id": block_id(tool, tool_input),
        "time": when,
        "tool": tool,
        "rule": rule,
        "input": tool_input,
        "reason": reason,
        "tool_version": version,
        "replay": replay,
        "source": source,
    }


def judge(spec, ran, rc, stdout):
    if not ran:
        return "not_replayable"
    bi = spec["blocked_if"]
    if "rc" in bi:
        if rc == bi["rc"]:
            return "reproduced"
        elif rc == 0:
            return "no_longer_reproduced"
        else:
            return "not_replayable"
    else:
        needle = bi["stdout_contains"]
        if needle in stdout:
            return "reproduced"
        elif rc == 0:
            return "no_longer_reproduced"
        else:
            return "not_replayable"


def make_replay(bid, when, version, outcome, rc, detail):
    if outcome not in OUTCOMES:
        raise ValueError("outcome not in OUTCOMES")
    return {
        "kind": "replay",
        "id": bid,
        "time": when,
        "tool_version": version,
        "outcome": outcome,
        "rc": rc,
        "detail": detail[:300],
    }


def parse_lines(text):
    records = []
    bad = 0
    for line in text.splitlines():
        if line.strip() == "":
            continue
        try:
            obj = json.loads(line)
        except (json.JSONDecodeError, ValueError):
            bad += 1
            continue
        if not isinstance(obj, dict):
            bad += 1
            continue
        if obj.get("kind") not in ("block", "replay"):
            bad += 1
            continue
        if "id" not in obj or not isinstance(obj["id"], str):
            bad += 1
            continue
        records.append(obj)
    return (records, bad)


def latest(records):
    order = []
    block_first = {}
    block_count = {}
    replay_last = {}
    for rec in records:
        rid = rec["id"]
        if rec["kind"] == "block":
            if rid not in block_first:
                block_first[rid] = rec
                order.append(rid)
            block_count[rid] = block_count.get(rid, 0) + 1
        else:
            replay_last[rid] = rec
    result = {}
    for rid in order:
        rec = replay_last.get(rid)
        if rec is not None:
            outcome = rec["outcome"]
            replayed_at = rec["time"]
        else:
            outcome = "never_replayed"
            replayed_at = None
        result[rid] = {
            "block": block_first[rid],
            "count": block_count[rid],
            "outcome": outcome,
            "replayed_at": replayed_at,
        }
    return result


def summary(records):
    states = latest(records)
    counts = {"reproduced": 0, "no_longer_reproduced": 0, "not_replayable": 0, "never_replayed": 0}
    for _rid, state in states.items():
        counts[state["outcome"]] += 1
    return counts


def is_duplicate(records, block):
    bid = block["id"]
    btime = block["time"]
    for rec in records:
        if rec["kind"] == "block" and rec["id"] == bid and rec["time"] == btime:
            return True
    return False


SPEC_RC = {"argv": ["tool", "--check"], "stdin": None, "blocked_if": {"rc": 5}}
SPEC_OUT = {"argv": ["tool"], "stdin": "x", "env": {"A": "1"}, "blocked_if": {"stdout_contains": "deny"}}
LINES = '{"kind": "block", "id": "a"}\n\nnot json\n{"kind": "other", "id": "b"}\n{"kind": "replay", "id": "a"}\n   \n[1, 2]\n'


def B(i, t):
    return {"kind": "block", "id": i, "time": t, "tool": "g", "rule": "r", "input": {}, "reason": "", "tool_version": None, "replay": None, "source": "s"}


def R(i, t, o):
    return {"kind": "replay", "id": i, "time": t, "tool_version": None, "outcome": o, "rc": 0, "detail": ""}


RECORDS = [B("A", "t1"), R("C", "t0", "reproduced"), B("B", "t2"), B("A", "t3"), R("A", "t4", "reproduced"), R("A", "t5", "no_longer_reproduced")]

_NOTICE = (
    "NAME      block_rules.py - pure core of the block logs: builds and reads the lines where each refusing tool keeps the refused input, its version and the command that replays it.\n"
    "READS     nothing: every function takes its data as arguments.\n"
    "WRITES    nothing; --autotest prints one PASS or FAIL line per test.\n"
    "EXAMPLE   python3 block_rules.py --autotest\n"
    "PITFALLS  2026-09-25 old refusals were only counted, never kept whole: nobody could tell whether a refusal still happens with today's version.\n"
    "          A replay line is appended next to the block, never in its place: history is never erased.\n"
)

_USAGE = "usage: block_rules.py --notice | --autotest\n"


def _autotest():
    failures = 0

    # Test 1
    try:
        h1 = block_id("Bash", {"a": 1, "b": 2})
        h2 = block_id("Bash", {"b": 2, "a": 1})
        h3 = block_id("Read", {"a": 1, "b": 2})
        assert h1 == h2, f"block_id mismatch: {h1} != {h2}"
        assert len(h1) == 16, f"length {len(h1)}"
        assert h1 != h3, f"block_id collision: {h1}"
        blk = make_block("Bash", "r", {"c": "ls"}, "no", "2026-09-26T00:00:00", "abc", SPEC_RC, "live")
        expected_keys = ["kind", "id", "time", "tool", "rule", "input", "reason", "tool_version", "replay", "source"]
        assert list(blk.keys()) == expected_keys, f"keys {list(blk.keys())}"
        try:
            make_block("", "r", {}, "", "t", None, None, "s")
            assert False, "empty tool did not raise"
        except ValueError:
            pass
        try:
            make_block("g", "r", {}, "", "t", None, {"argv": ["x"], "blocked_if": {"rc": 1, "stdout_contains": "d"}}, "s")
            assert False, "two-key blocked_if did not raise"
        except ValueError:
            pass
        assert check_replay(SPEC_OUT) == "", f"SPEC_OUT invalid: {check_replay(SPEC_OUT)}"
        assert check_replay({"argv": [], "blocked_if": {"rc": 1}}) != "", "empty argv accepted"
        print("PASS 1: block_id / make_block / check_replay")
    except Exception as e:
        print(f"FAIL 1: expected id-order/keys/ValueError, got {e}")
        failures += 1

    # Test 2
    try:
        assert judge(SPEC_RC, True, 5, "") == "reproduced", f"got {judge(SPEC_RC, True, 5, '')}"
        assert judge(SPEC_RC, True, 0, "") == "no_longer_reproduced", f"got {judge(SPEC_RC, True, 0, '')}"
        assert judge(SPEC_RC, True, 1, "") == "not_replayable", f"got {judge(SPEC_RC, True, 1, '')}"
        assert judge(SPEC_RC, False, 0, "") == "not_replayable", f"got {judge(SPEC_RC, False, 0, '')}"
        assert judge(SPEC_OUT, True, 0, "a deny b") == "reproduced", f"got {judge(SPEC_OUT, True, 0, 'a deny b')}"
        assert judge(SPEC_OUT, True, 0, "") == "no_longer_reproduced", f"got {judge(SPEC_OUT, True, 0, '')}"
        assert judge(SPEC_OUT, True, 2, "") == "not_replayable", f"got {judge(SPEC_OUT, True, 2, '')}"
        print("PASS 2: judge all seven cases")
    except Exception as e:
        print(f"FAIL 2: expected outcomes reproduced/no_longer_reproduced/not_replayable, got {e}")
        failures += 1

    # Test 3
    try:
        records, bad = parse_lines(LINES)
        assert len(records) == 2, f"expected 2 records, got {len(records)}"
        assert records[0]["kind"] == "block", f"first kind {records[0].get('kind')}"
        assert records[1]["kind"] == "replay", f"second kind {records[1].get('kind')}"
        assert bad == 3, f"expected bad=3, got {bad}"
        print("PASS 3: parse_lines 2 records, bad=3")
    except Exception as e:
        print(f"FAIL 3: expected 2 records and bad=3, got {e}")
        failures += 1

    # Test 4
    try:
        lt = latest(RECORDS)
        assert list(lt.keys()) == ["A", "B"], f"keys {list(lt.keys())}"
        assert lt["A"]["count"] == 2, f"count {lt['A']['count']}"
        assert lt["A"]["outcome"] == "no_longer_reproduced", f"outcome {lt['A']['outcome']}"
        assert lt["A"]["replayed_at"] == "t5", f"replayed_at {lt['A']['replayed_at']}"
        assert lt["A"]["block"]["time"] == "t1", f"block time {lt['A']['block']['time']}"
        assert lt["B"]["outcome"] == "never_replayed", f"B outcome {lt['B']['outcome']}"
        assert lt["B"]["replayed_at"] is None, f"B replayed_at {lt['B']['replayed_at']}"
        s = summary(RECORDS)
        expected_summary = {"reproduced": 0, "no_longer_reproduced": 1, "not_replayable": 0, "never_replayed": 1}
        assert s == expected_summary, f"summary {s}"
        assert is_duplicate(RECORDS, B("A", "t3")) is True, "should be duplicate"
        assert is_duplicate(RECORDS, B("A", "t9")) is False, "should not be duplicate"
        print("PASS 4: latest / summary / is_duplicate")
    except Exception as e:
        print(f"FAIL 4: expected A/B states and summary counts, got {e}")
        failures += 1

    # Test 5
    try:
        try:
            make_replay("A", "t", None, "maybe", 0, "")
            assert False, "invalid outcome did not raise"
        except ValueError:
            pass
        r = make_replay("A", "t", None, "reproduced", 5, "x" * 400)
        assert len(r["detail"]) == 300, f"detail len {len(r['detail'])}"
        p = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        assert p.returncode == 0, f"notice rc={p.returncode}"
        assert p.stdout.startswith("NAME      block_rules.py"), f"notice stdout starts with {p.stdout[:40]!r}"
        p2 = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
        assert p2.returncode == 2, f"no-arg rc={p2.returncode}"
        assert p2.stdout == _USAGE, f"no-arg stdout={p2.stdout!r}"
        print("PASS 5: make_replay / subprocess notice and usage")
    except Exception as e:
        print(f"FAIL 5: expected ValueError, detail=300, subprocess codes 0/2, got {e}")
        failures += 1

    return failures


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(_NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        failures = _autotest()
        sys.exit(1 if failures else 0)
    else:
        sys.stdout.write(_USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "block_rules", sys.argv[1:])
