import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


try:
    with open("summary.json", encoding="utf-8") as f:
        out = json.load(f)
except Exception as e:
    fail("summary.json missing or invalid: %r" % (e,))

total_valid = 0
skipped = 0
total_bytes = 0
classes = {"2xx": 0, "3xx": 0, "4xx": 0, "5xx": 0}
paths = {}

with open("access.log", encoding="utf-8") as f:
    for raw in f:
        line = raw.rstrip("\r\n")
        s = line.strip()
        if s == "":
            continue
        parts = s.split()
        if len(parts) != 6 or parts[0].startswith("#"):
            skipped += 1
            continue
        status, path = parts[4], parts[3]
        total_valid += 1
        total_bytes += int(parts[5])
        classes[status[0] + "xx"] += 1
        paths[path] = paths.get(path, 0) + 1

maxc = max(paths.values())
top = min(p for p, c in paths.items() if c == maxc)

expected = {
    "total_valid": total_valid,
    "status_classes": classes,
    "top_path": top,
    "total_bytes": total_bytes,
    "skipped": skipped,
}

if not isinstance(out, dict):
    fail("summary.json must be a JSON object")

for key in expected:
    if out.get(key) != expected[key]:
        fail("mismatch in %r: got %r, expected %r" % (key, out.get(key), expected[key]))

if set(out) != set(expected):
    fail("unexpected keys in summary.json: got keys %r" % (sorted(out),))

print("PASS")
