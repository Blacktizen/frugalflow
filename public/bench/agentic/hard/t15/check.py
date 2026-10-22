import json
import os
import sys

TASK = "t15"


def compute_expected():
    total = 0
    total_lines = 0
    todo = []
    linecounts = {}
    for root, dirs, files in os.walk("project"):
        dirs.sort()
        for name in sorted(files):
            full = os.path.join(root, name)
            rel = os.path.relpath(full).replace(os.sep, "/")
            total += 1
            with open(full) as handle:
                content = handle.read()
            count = content.count("\n")
            total_lines += count
            linecounts[rel] = count
            if "TODO" in content:
                todo.append(rel)
    longest = min(linecounts, key=lambda p: (-linecounts[p], p))
    return {
        "total_files": total,
        "total_lines": total_lines,
        "todo_files": sorted(todo),
        "longest_file": longest,
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
