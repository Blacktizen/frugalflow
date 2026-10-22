import glob
import json
import os
import sys

TASK = "t09"


def compute_expected():
    lines = []
    for fname in sorted(glob.glob("access.log")):
        with open(fname) as handle:
            lines.extend(handle.read().splitlines())
    status_groups = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
    path_counts = {}
    total_bytes = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        path = parts[3]
        status = int(parts[4])
        size = int(parts[5])
        path_counts[path] = path_counts.get(path, 0) + 1
        status_groups[str(status)[0] + "xx"] += 1
        total_bytes += size
    top_path = min(path_counts, key=lambda p: (-path_counts[p], p))
    return {
        "total_requests": len(lines),
        "status_2xx": status_groups["2xx"],
        "status_3xx": status_groups["3xx"],
        "status_4xx": status_groups["4xx"],
        "status_5xx": status_groups["5xx"],
        "top_path": top_path,
        "total_bytes": total_bytes,
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
