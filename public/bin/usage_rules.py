import json
import os
import subprocess
import sys

CATEGORIES = ["conversation", "work", "thinking"]


def category(block):
    block_type = block.get("type")
    if block_type == "tool_use":
        return "work"
    if block_type in ("thinking", "redacted_thinking"):
        return "thinking"
    return "conversation"


def block_chars(block):
    return len(json.dumps(block, ensure_ascii=False))


def allocate(tokens, fractions):
    total = sum(fractions)
    if total <= 0:
        result = [0] * len(fractions)
        if result:
            result[0] = tokens
        return result

    exact = [tokens * f / total for f in fractions]
    result = [int(e) for e in exact]
    rest = tokens - sum(result)
    order = sorted(range(len(exact)), key=lambda i: exact[i] - result[i], reverse=True)
    for i in range(rest):
        result[order[i % len(order)]] += 1
    return result


def group(objs):
    messages = []
    by_key = {}

    for i, o in enumerate(objs):
        if not isinstance(o, dict):
            continue
        m = o.get("message")
        if not isinstance(m, dict):
            continue
        u = m.get("usage")
        if not isinstance(u, dict):
            continue

        mid = m.get("id")
        if isinstance(mid, str) and mid:
            key = (mid, o.get("requestId"))
        else:
            key = ("line", i)

        if key not in by_key:
            msg = {"usage": u, "blocks": [], "time": o.get("timestamp")}
            by_key[key] = msg
            messages.append(msg)

        content = m.get("content")
        if isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    by_key[key]["blocks"].append(block)

    return messages


def num(usage, key):
    value = usage.get(key)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def split_output(msg):
    out = num(msg["usage"], "output_tokens")
    chars = [0, 0, 0]
    for block in msg["blocks"]:
        chars[CATEGORIES.index(category(block))] += block_chars(block)
    return allocate(out, chars)


def totals(msgs):
    conversation = 0
    work = 0
    thinking = 0
    input_tokens = 0
    cache_write = 0
    cache_read = 0
    output = 0
    tool_calls = 0
    turns_with_tools = 0

    for msg in msgs:
        u = msg["usage"]
        input_tokens += num(u, "input_tokens")
        cache_write += num(u, "cache_creation_input_tokens")
        cache_read += num(u, "cache_read_input_tokens")
        output += num(u, "output_tokens")

        parts = split_output(msg)
        conversation += parts[0]
        work += parts[1]
        thinking += parts[2]

        has_tool = False
        for block in msg["blocks"]:
            if category(block) == "work":
                tool_calls += 1
                has_tool = True
        if has_tool:
            turns_with_tools += 1

    share = round(100 * conversation / output, 1) if output > 0 else 0.0
    grouping = round(tool_calls / turns_with_tools, 2) if turns_with_tools > 0 else 0.0
    reread_per_turn = round(cache_read / len(msgs)) if len(msgs) > 0 else 0

    return {
        "messages": len(msgs),
        "input": input_tokens,
        "cache_write": cache_write,
        "cache_read": cache_read,
        "output": output,
        "conversation": conversation,
        "work": work,
        "thinking": thinking,
        "share": share,
        "tool_calls": tool_calls,
        "turns_with_tools": turns_with_tools,
        "grouping": grouping,
        "reread_per_turn": reread_per_turn,
    }


def fmt(n):
    return format(n, ",").replace(",", " ")


def receipt(t, threshold=12.0):
    line = (
        "Tokens: " + fmt(t["output"]) +
        " written (conversation " + str(t["share"]) +
        " %, threshold " + str(threshold) +
        " %) | context reread " + fmt(t["cache_read"]) +
        " | " + str(t["messages"]) +
        " turns | " + str(t["grouping"]) +
        " calls per turn"
    )
    if t["share"] > threshold:
        line += " | OVER THRESHOLD"
    return line


TH = {"type": "thinking", "thinking": "plan the work"}
TU1 = {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
TU2 = {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}
TX = {"type": "text", "text": "Done, all green."}
U1 = {"input_tokens": 10, "cache_read_input_tokens": 1000, "output_tokens": 90}
U2 = {"input_tokens": 5, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 300, "output_tokens": 30}
LINES = [
    {"type": "assistant", "requestId": "r1", "timestamp": "t1", "message": {"id": "m1", "usage": U1, "content": [TH]}},
    {"type": "assistant", "requestId": "r1", "timestamp": "t1", "message": {"id": "m1", "usage": U1, "content": [TU1]}},
    {"type": "assistant", "requestId": "r1", "timestamp": "t1", "message": {"id": "m1", "usage": U1, "content": [TU2]}},
    {"type": "user", "message": {"role": "user", "content": "go"}},
    "x",
    {"type": "assistant", "requestId": "r2", "timestamp": "t2", "message": {"id": "m2", "usage": U2, "content": [TX]}},
    {"type": "assistant", "requestId": "r2", "timestamp": "t2", "message": {"id": "m2", "usage": U2, "content": []}},
    {"type": "assistant", "timestamp": "t3", "message": {"usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "ok"}]}},
]

NOTICE = """NAME      usage_rules.py - counts a session's tokens once per message, splits the output into conversation, work and thinking, and writes a one-line receipt.
READS     nothing: pure module; it works on the transcript lines it is given, already decoded.
WRITES    nothing: totals() returns the counts, receipt() the line to show.
EXAMPLE   python3 usage_rules.py --notice
PITFALLS  2026-09-23 one message spread over several lines had its usage summed once per line: 372 019 output tokens reported for 144 595 real.
          Lines are now grouped by message id and request id before counting.
"""


def autotest():
    ok_all = True

    def check(ok, name, expected, got):
        status = "PASS" if ok else "FAIL"
        print(f"{status} {name}: expected={expected!r} got={got!r}")
        return ok

    expected1 = ([4, 3, 3], [7, 0, 0], [0, 66, 24], "conversation", "work", 49)
    got1 = (
        allocate(10, [1, 1, 1]),
        allocate(7, [0, 0, 0]),
        allocate(90, [0, 132, 49]),
        category(TX),
        category(TU1),
        block_chars(TH),
    )
    ok_all = check(got1 == expected1, "test 1", expected1, got1) and ok_all

    g = group(LINES)
    expected2 = (3, [TH, TU1, TU2], U1, [TX], "t3")
    got2 = (
        len(g),
        g[0]["blocks"] if len(g) > 0 else None,
        g[0]["usage"] if len(g) > 0 else None,
        g[1]["blocks"] if len(g) > 1 else None,
        g[2]["time"] if len(g) > 2 else None,
    )
    ok_all = check(got2 == expected2, "test 2", expected2, got2) and ok_all

    expected3 = ([0, 66, 24], [30, 0, 0], [8, 0, 0])
    got3 = (
        split_output(g[0]) if len(g) > 0 else None,
        split_output(g[1]) if len(g) > 1 else None,
        split_output({"usage": {"output_tokens": 8}, "blocks": []}),
    )
    ok_all = check(got3 == expected3, "test 3", expected3, got3) and ok_all

    t = totals(g)
    expected_t = {
        "messages": 3,
        "input": 15,
        "cache_write": 300,
        "cache_read": 3000,
        "output": 125,
        "conversation": 35,
        "work": 66,
        "thinking": 24,
        "share": 28.0,
        "tool_calls": 2,
        "turns_with_tools": 1,
        "grouping": 2.0,
        "reread_per_turn": 1000,
    }
    expected_receipt = "Tokens: 125 written (conversation 28.0 %, threshold 12.0 %) | context reread 3 000 | 3 turns | 2.0 calls per turn | OVER THRESHOLD"
    expected4 = (expected_t, expected_receipt, True)
    got4 = (
        t,
        receipt(t),
        receipt(t, 30.0).endswith("2.0 calls per turn"),
    )
    ok_all = check(got4 == expected4, "test 4", expected4, got4) and ok_all

    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True,
    )
    expected5 = (0, True)
    got5 = (proc.returncode, proc.stdout.startswith("NAME      usage_rules.py"))
    ok_all = check(got5 == expected5, "test 5", expected5, got5) and ok_all

    return 0 if ok_all else 1


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    sys.stdout.write("usage: usage_rules.py --notice | --autotest\n")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "usage_rules", sys.argv[1:])
