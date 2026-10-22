import json
import os
import sys

TASK = "t14"


def compute_expected():
    total = 0
    total_bytes = 0
    empty = []
    sizes = {}
    subdirs = 0
    for root, dirs, files in os.walk("assets"):
        subdirs += len(dirs)
        for name in files:
            full = os.path.join(root, name)
            rel = os.path.relpath(full).replace(os.sep, "/")
            total += 1
            size = os.path.getsize(full)
            total_bytes += size
            sizes[rel] = size
            if size == 0:
                empty.append(rel)
    largest = min(sizes, key=lambda p: (-sizes[p], p))
    return {
        "total_files": total,
        "empty_files": sorted(empty),
        "total_bytes": total_bytes,
        "largest_file": largest,
        "subdir_count": subdirs,
    }


def main():
    try:
        with open("inventory.json") as handle:
            got = json.load(handle)
    except Exception as exc:
        print("FAIL %s cannot read inventory.json: %s" % (TASK, exc))
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
