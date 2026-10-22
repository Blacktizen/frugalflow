import sys
import csv
import json
from decimal import Decimal


def main():
    try:
        with open("report.csv", encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f, delimiter=";"))
        with open("rows.json", encoding="utf-8") as f:
            got = json.load(f)
    except Exception as e:
        print("FAIL: %r" % e)
        return 1
    header = rows[0]
    amount_col = header.index("amount")
    data = [r for r in rows[1:] if any(c.strip() for c in r)]
    total = sum(Decimal(r[amount_col]) for r in data)
    if got.get("data_rows") != data:
        print("FAIL: data_rows mismatch")
        return 1
    try:
        got_total = float(got.get("total"))
    except Exception:
        print("FAIL: total missing or not numeric")
        return 1
    if abs(got_total - float(total)) > 0.005:
        print("FAIL: total = %r, want %r" % (got.get("total"), float(total)))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
