import json
import os
import sys

TASK = "t16"


def compute_expected():
    total = 0
    total_bytes = 0
    sizes = {}
    content_files = {}
    exts = set()
    for root, dirs, files in os.walk("store"):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full).replace(os.sep, "/")
            total += 1
            size = os.path.getsize(full)
            total_bytes += size
            sizes[rel] = size
            with open(full) as handle:
                content = handle.read()
            content_files.setdefault(content, []).append(rel)
            if "." in name:
                exts.add(name.rsplit(".", 1)[1])
    dup_groups = sum(1 for paths in content_files.values() if len(paths) >= 2)
    largest = min(sizes, key=lambda p: (-sizes[p], p))
    return {
        "total_files": total,
        "total_bytes": total_bytes,
        "duplicate_content_groups": dup_groups,
        "largest_file": largest,
        "extensions": sorted(exts),
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
