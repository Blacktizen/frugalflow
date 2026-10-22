import json
import os
import sys


def main():
    cfg = json.load(open(sys.argv[1]))
    exts = cfg["filters"]["allowed"]["extensions"]
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        ext = os.path.splitext(line)[1]
        if ext in exts:
            print(line)


if __name__ == "__main__":
    main()
