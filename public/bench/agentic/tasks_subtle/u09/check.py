import sys
import json
import re

PAT = re.compile(r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (INFO|WARN|ERROR|DEBUG)\b")


def main():
    try:
        with open("app.log", encoding="utf-8") as f:
            lines = f.read().splitlines()
        with open("levels.json", encoding="utf-8") as f:
            got = json.load(f)
    except Exception as e:
        print("FAIL: %r" % e)
        return 1
    want = {"INFO": 0, "WARN": 0, "ERROR": 0, "DEBUG": 0}
    for ln in lines:
        m = PAT.match(ln)
        if m:
            want[m.group(1)] += 1
    if got != want:
        print("FAIL: levels.json = %r, want %r" % (got, want))
        return 1
    print("PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
