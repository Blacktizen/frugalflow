import csv
import datetime
import json
import sys


def fail(msg):
    print("FAIL", msg)
    sys.exit(1)


try:
    with open("value.json", encoding="utf-8") as f:
        out = json.load(f)
except Exception as e:
    fail("value.json missing or invalid: %r" % (e,))

state = {}
with open("stock.csv", encoding="utf-8", newline="") as f:
    for row in csv.DictReader(f):
        sku = row["sku"]
        updated = datetime.datetime.fromisoformat(row["updated"])
        if sku not in state or updated > state[sku]["updated"]:
            state[sku] = {
                "qty": int(row["qty"]),
                "price": float(row["unit_price"]),
                "updated": updated,
            }

total = 0.0
for v in state.values():
    qty = v["qty"] if v["qty"] > 0 else 0
    total += qty * v["price"]

expected = {"total": round(total, 2)}

if not isinstance(out, dict) or out != expected:
    fail("got %r, expected %r" % (out, expected))

print("PASS")
