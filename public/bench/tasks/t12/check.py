import glob
import json
import os
import sys

TASK = "t12"


def compute_expected():
    lines = []
    for fname in sorted(glob.glob("events.log")):
        with open(fname) as handle:
            lines.extend(handle.read().splitlines())
    type_counts = {"purchase": 0, "refund": 0, "signup": 0, "chargeback": 0, "adjustment": 0}
    total_amount = 0
    amounts = {}
    above = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        etype = parts[1]
        event_id = parts[2]
        amount = int(parts[3])
        type_counts[etype] = type_counts.get(etype, 0) + 1
        total_amount += amount
        amounts[event_id] = amount
        if amount > 1000:
            above += 1
    largest = min(amounts, key=lambda e: (-amounts[e], e))
    return {
        "total_events": len(lines),
        "type_counts": type_counts,
        "total_amount": total_amount,
        "largest_event": largest,
        "events_above_1000": above,
    }


def main():
    try:
        with open("summary.json") as handle:
            got = json.load(handle)
    except Exception as exc:
        print("FAIL %s cannot read summary.json: %s" % (TASK, exc))
        sys.exit(1)
    try:
        expected = compute_expected()
    except Exception as exc:
        print("FAIL %s checker error: %s" % (TASK, exc))
        sys.exit(1)
    problems = []
    for key in sorted(expected):
        if got.get(key) != expected[key]:
            problems.append((key, expected[key], got.get(key)))
    if problems:
        print("FAIL %s mismatches: %r" % (TASK, problems))
        sys.exit(1)
    print("PASS %s" % TASK)
    sys.exit(0)


if __name__ == "__main__":
    main()
