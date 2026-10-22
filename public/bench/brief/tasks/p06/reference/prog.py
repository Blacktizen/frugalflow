import sys


def main():
    path = sys.argv[1]
    total = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            _, count = line.split("|")
            total += int(count)
    print(total)


if __name__ == "__main__":
    main()
