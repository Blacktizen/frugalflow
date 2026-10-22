import json
import os
import subprocess
import sys

from usage_rules import fmt, num

DETAIL_KEYS = ("file_path", "command", "pattern")
CASE_NUMBERS = (1, 2, 3, 4, 5)


def context_of(msg):
    u = msg["usage"]
    return (
        num(u, "input_tokens")
        + num(u, "cache_read_input_tokens")
        + num(u, "cache_creation_input_tokens")
    )


def cause_of(msg):
    for block in msg["blocks"]:
        if block.get("type") == "tool_use":
            name = block.get("name", "")
            detail = ""
            inp = block.get("input")
            if isinstance(inp, dict):
                for key in DETAIL_KEYS:
                    value = inp.get(key)
                    if isinstance(value, str) and value:
                        detail = value[:60]
                        break
            if detail:
                return name + ": " + detail
            return name
    return "no tool call"


def analyze(msgs):
    turns = len(msgs)
    contexts = [context_of(m) for m in msgs]
    reread_total = sum(num(m["usage"], "cache_read_input_tokens") for m in msgs)
    reread_per_turn = round(reread_total / turns) if turns > 0 else 0
    startup_per_turn = contexts[0] if turns > 0 else 0
    startup_total = startup_per_turn * turns
    context_total = sum(contexts)
    startup_share = round(100 * startup_total / context_total, 1) if context_total > 0 else 0.0

    top = []
    for i in range(1, turns):
        growth = contexts[i] - contexts[i - 1]
        if growth > 0:
            top.append({"turn": i + 1, "growth": growth, "cause": cause_of(msgs[i - 1])})
    top.sort(key=lambda item: (-item["growth"], item["turn"]))

    return {
        "turns": turns,
        "reread_total": reread_total,
        "reread_per_turn": reread_per_turn,
        "startup_per_turn": startup_per_turn,
        "startup_total": startup_total,
        "context_total": context_total,
        "startup_share": startup_share,
        "top_turns": top[:3],
    }


def render(a):
    lines = [
        "turns: " + fmt(a["turns"]) + " [observed]",
        "context reread: " + fmt(a["reread_total"]) + " total, "
        + fmt(a["reread_per_turn"]) + " per turn [observed]",
        "startup context: " + fmt(a["startup_per_turn"]) + " per turn, about "
        + fmt(a["startup_share"]) + " % of all context [estimated]",
    ]
    for item in a["top_turns"]:
        lines.append(
            "costliest turn " + fmt(item["turn"])
            + ": +" + fmt(item["growth"])
            + " tokens after " + item["cause"] + " [observed]"
        )
    return lines


def summary_lines(a):
    lines = [
        "FrugalFlow - session summary",
        "  " + fmt(a["turns"]) + " turns - " + fmt(a["reread_total"])
        + " context reread - startup: " + fmt(a["startup_per_turn"]) + " per turn",
    ]
    if a["top_turns"]:
        item = a["top_turns"][0]
        lines.append(
            "  costliest: turn " + fmt(item["turn"])
            + ", +" + fmt(item["growth"])
            + " tokens after " + item["cause"]
        )
    lines.append("  details: frugalflow report")
    return lines


# Four assistant messages, as (input, cache_read, cache_creation, output).
FIXTURE = [
    {
        "usage": {"input_tokens": 100, "cache_read_input_tokens": 0,
                  "cache_creation_input_tokens": 9900, "output_tokens": 50},
        "blocks": [{"type": "tool_use", "name": "Read", "input": {"file_path": "big.log"}}],
        "time": "t1",
    },
    {
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 10000,
                  "cache_creation_input_tokens": 30000, "output_tokens": 20},
        "blocks": [{"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}],
        "time": "t2",
    },
    {
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 40000,
                  "cache_creation_input_tokens": 500, "output_tokens": 10},
        "blocks": [{"type": "text", "text": "ok"}],
        "time": "t3",
    },
    {
        "usage": {"input_tokens": 10, "cache_read_input_tokens": 40500,
                  "cache_creation_input_tokens": 2000, "output_tokens": 5},
        "blocks": [{"type": "text", "text": "done"}],
        "time": "t4",
    },
]

EXPECTED_NUMBERS = {
    "turns": 4,
    "reread_total": 90500,
    "reread_per_turn": 22625,
    "startup_per_turn": 10000,
    "startup_total": 40000,
    "context_total": 133030,
    "startup_share": 30.1,
}

EXPECTED_TOP_TURNS = [
    {"turn": 2, "growth": 30010, "cause": "Read: big.log"},
    {"turn": 4, "growth": 2000, "cause": "no tool call"},
    {"turn": 3, "growth": 500, "cause": "Bash: ls"},
]

EXPECTED_RENDER = [
    "turns: 4 [observed]",
    "context reread: 90 500 total, 22 625 per turn [observed]",
    "startup context: 10 000 per turn, about 30.1 % of all context [estimated]",
    "costliest turn 2: +30 010 tokens after Read: big.log [observed]",
    "costliest turn 4: +2 000 tokens after no tool call [observed]",
    "costliest turn 3: +500 tokens after Bash: ls [observed]",
]

EXPECTED_SUMMARY = [
    "FrugalFlow - session summary",
    "  4 turns - 90 500 context reread - startup: 10 000 per turn",
    "  costliest: turn 2, +30 010 tokens after Read: big.log",
    "  details: frugalflow report",
]

EXPECTED_EMPTY = {
    "turns": 0,
    "reread_total": 0,
    "reread_per_turn": 0,
    "startup_per_turn": 0,
    "startup_total": 0,
    "context_total": 0,
    "startup_share": 0.0,
    "top_turns": [],
}

EXPECTED_EMPTY_SUMMARY = [
    "FrugalFlow - session summary",
    "  0 turns - 0 context reread - startup: 0 per turn",
    "  details: frugalflow report",
]


def case_got(i):
    a = analyze(FIXTURE)
    if i == 1:
        return {k: a[k] for k in EXPECTED_NUMBERS}
    if i == 2:
        return a["top_turns"]
    if i == 3:
        return render(a)
    if i == 4:
        return summary_lines(a)
    empty = analyze([])
    return {"analyze": empty, "summary_lines": summary_lines(empty)}


EXPECTED_CASES = {
    1: EXPECTED_NUMBERS,
    2: EXPECTED_TOP_TURNS,
    3: EXPECTED_RENDER,
    4: EXPECTED_SUMMARY,
    5: {"analyze": EXPECTED_EMPTY, "summary_lines": EXPECTED_EMPTY_SUMMARY},
}

NOTICE = """NAME      report_rules.py - explains where a session's tokens went: context reread, startup cost and the costliest turns.
READS     nothing: pure module; it works on the grouped messages it is given, already decoded.
WRITES    nothing: analyze() returns the numbers, render() and summary_lines() the lines to show.
EXAMPLE   python3 report_rules.py --notice
PITFALLS  2026-10-04 A growth line names the tool call of the PREVIOUS message, because the context grows after it.
          With no tool call there the cause reads "no tool call"; the share is an estimate, not a cost.
"""


def run_case(i):
    if i not in EXPECTED_CASES:
        return 2
    got = case_got(i)
    sys.stdout.write(json.dumps(got) + "\n")
    return 0 if got == EXPECTED_CASES[i] else 1


def autotest():
    passed = 0
    failed = 0
    for i in CASE_NUMBERS:
        expected = EXPECTED_CASES[i]
        proc = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--autotest-case", str(i)],
            capture_output=True,
            text=True,
        )
        raw = proc.stdout.strip()
        try:
            got = json.loads(raw)
        except ValueError:
            got = raw
        ok = proc.returncode == 0 and got == expected
        status = "PASS" if ok else "FAIL"
        print(f"{status} case {i}: expected={expected!r} got={got!r}")
        if ok:
            passed += 1
        else:
            failed += 1
    if failed == 0:
        print(f"AUTOTEST {passed} PASS")
    else:
        print(f"AUTOTEST {passed} PASS / {failed} FAIL")
    return 0 if failed == 0 else 1


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return autotest()
    if len(argv) == 2 and argv[0] == "--autotest-case" and argv[1].isdigit():
        return run_case(int(argv[1]))
    sys.stdout.write("usage: report_rules.py --notice | --autotest\n")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "report_rules", sys.argv[1:])
