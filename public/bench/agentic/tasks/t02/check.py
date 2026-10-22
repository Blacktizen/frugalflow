import datetime
import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


try:
    with open("busiest.json", encoding="utf-8") as f:
        out = json.load(f)
except Exception as e:
    fail("busiest.json missing or invalid: %r" % (e,))

counts = {}
with open("events.log", encoding="utf-8") as f:
    for raw in f:
        line = raw.strip()
        if not line:
            continue
        ts = line.split()[0]
        dt = datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
        dt = dt.astimezone(datetime.timezone.utc)
        hour = dt.strftime("%Y-%m-%dT%H")
        counts[hour] = counts.get(hour, 0) + 1

maxc = max(counts.values())
hour = min(h for h, c in counts.items() if c == maxc)
expected = {"hour": hour, "count": maxc}

if not isinstance(out, dict) or out != expected:
    fail("got %r, expected %r" % (out, expected))

print("PASS")
