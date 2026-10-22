import json
import sys


def main():
    cfg = json.load(open(sys.argv[1]))
    cap = cfg["limits"]["daily"]["max"]
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        n = int(line)
        print("OK" if n <= cap else "OVER")


if __name__ == "__main__":
    main()
