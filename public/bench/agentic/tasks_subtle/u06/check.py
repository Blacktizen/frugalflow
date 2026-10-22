import sys
import json
from collections import defaultdict


def compute(log_text):
    by = defaultdict(list)
    for ln in log_text.splitlines():
        ln = ln.strip()
        if not ln:
            continue
        t, u = ln.split()
        by[u].append(int(t))
    refused = {}
    for u in sorted(by):
        ts = sorted(by[u])
        acc = []
        r = 0
        for t in ts:
            lo = t - 60
            if sum(1 for a in acc if a > lo) >= 5:
                r += 1
            else:
                acc.append(t)
        refused[u] = r
    return refused


def main():
    try:
        with open("ratelimit.log", encoding="utf-8") as f:
            log_text = f.read()
        with open("limited.json", encoding="utf-8") as f:
            got = json.load(f)
    except Exception as e:
        print("FAIL: %r" % e)
        return 1
    want = compute(log_text)
    if got != want:
        print("FAIL: limited.json = %r, want %r" % (got, want))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
