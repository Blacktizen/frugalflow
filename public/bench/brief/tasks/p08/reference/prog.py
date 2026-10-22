import json
import sys


def main():
    cfg = json.load(open(sys.argv[1]))
    suffix = cfg["output"]["format"]["suffix"]
    print(sys.argv[2] + suffix)


if __name__ == "__main__":
    main()
