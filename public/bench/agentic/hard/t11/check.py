import glob
import json
import os
import sys

TASK = "t11"


def compute_expected():
    lines = []
    for fname in sorted(glob.glob("jobs.log")):
        with open(fname) as handle:
            lines.extend(handle.read().splitlines())
    succeeded = 0
    failed = 0
    total_duration = 0
    durations = {}
    failed_ids = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        job_id = parts[1]
        status = parts[2]
        duration = int(parts[3])
        total_duration += duration
        durations[job_id] = duration
        if status == "OK":
            succeeded += 1
        else:
            failed += 1
            failed_ids.append(job_id)
    longest = min(durations, key=lambda j: (-durations[j], j))
    return {
        "total_jobs": len(lines),
        "succeeded": succeeded,
        "failed": failed,
        "total_duration_ms": total_duration,
        "longest_job": longest,
        "failed_ids": sorted(failed_ids),
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
