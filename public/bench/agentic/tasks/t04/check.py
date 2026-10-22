import csv
import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


try:
    with open("weight.json", encoding="utf-8") as f:
        out = json.load(f)
except Exception as e:
    fail("weight.json missing or invalid: %r" % (e,))

factors = {"kg": 1.0, "g": 0.001, "lb": 0.45359237}

total = 0.0
with open("parcels.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        unit = row["unit"].strip().lower()
        total += float(row["weight"]) * factors[unit]

expected = {"total_kg": round(total, 3)}

if not isinstance(out, dict) or out != expected:
    fail("got %r, expected %r" % (out, expected))

print("PASS")
