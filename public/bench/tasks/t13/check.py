import json
import os
import sys

TASK = "t13"


def compute_expected():
    counts = {}
    total_bytes = 0
    fixme = []
    sizes = {}
    for root, dirs, files in os.walk("tree"):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full).replace(os.sep, "/")
            ext = name.rsplit(".", 1)[1] if "." in name else ""
            counts[ext] = counts.get(ext, 0) + 1
            size = os.path.getsize(full)
            total_bytes += size
            sizes[rel] = size
            with open(full) as handle:
                content = handle.read()
            if "FIXME" in content:
                fixme.append(rel)
    largest = min(sizes, key=lambda p: (-sizes[p], p))
    return {
        "total_files": len(sizes),
        "extension_counts": counts,
        "total_bytes": total_bytes,
        "fixme_files": sorted(fixme),
        "largest_file": largest,
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
