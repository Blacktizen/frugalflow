import sys


def main():
    path = sys.argv[1]
    with open(path) as f:
        lines = [ln for ln in f.read().splitlines() if ln.strip()]
    print(len(lines[1:]))


if __name__ == "__main__":
    main()
