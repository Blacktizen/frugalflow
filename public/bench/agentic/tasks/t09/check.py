import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


try:
    with open("sessions.json", encoding="utf-8") as f:
        out = json.load(f)
except Exception as e:
    fail("sessions.json missing or invalid: %r" % (e,))

events = {}
with open("clicks.log", encoding="utf-8") as f:
    for raw in f:
        line = raw.strip()
        if not line:
            continue
        t_str, user = line.split()
        events.setdefault(user, []).append(int(t_str))

expected = {}
for user, times in events.items():
    times = sorted(times)
    sessions = 0
    prev = None
    for t in times:
        if prev is None or t - prev > 1800:
            sessions += 1
        prev = t
    expected[user] = sessions

if not isinstance(out, dict) or out != expected:
    fail("got %r, expected %r" % (out, expected))

print("PASS")
