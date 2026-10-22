import json
import sys


def main():
    cfg = json.load(open(sys.argv[1]))
    weight = cfg["scoring"]["weights"]["priority"]
    print(int(sys.argv[2]) * weight)


if __name__ == "__main__":
    main()
