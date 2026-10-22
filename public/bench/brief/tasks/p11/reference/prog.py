import json
import sys


def main():
    cfg = json.load(open(sys.argv[1]))
    enabled = cfg["features"]["logging"]["enabled"]
    for line in sys.stdin:
        line = line.rstrip("\n")
        print(("LOG: " + line) if enabled else line)


if __name__ == "__main__":
    main()
