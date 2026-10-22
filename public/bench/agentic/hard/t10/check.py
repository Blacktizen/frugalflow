import glob
import json
import os
import sys

TASK = "t10"


def compute_expected():
    lines = []
    for fname in sorted(glob.glob("svc.log")):
        with open(fname) as handle:
            lines.extend(handle.read().splitlines())
    level_counts = {"INFO": 0, "WARN": 0, "ERROR": 0, "DEBUG": 0}
    services = set()
    service_counts = {}
    error_codes = set()
    warn_timeouts = 0
    for line in lines:
        if not line.strip():
            continue
        parts = line.split(None, 4)
        level = parts[1]
        service = parts[2]
        code = parts[3]
        message = parts[4]
        level_counts[level] = level_counts.get(level, 0) + 1
        services.add(service)
        service_counts[service] = service_counts.get(service, 0) + 1
        if level == "ERROR":
            error_codes.add(code)
        if level == "WARN" and "timeout" in message:
            warn_timeouts += 1
    busiest = min(service_counts, key=lambda s: (-service_counts[s], s))
    return {
        "total_lines": len(lines),
        "level_counts": level_counts,
        "distinct_services": len(services),
        "busiest_service": busiest,
        "distinct_error_codes": len(error_codes),
        "warn_timeouts": warn_timeouts,
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
