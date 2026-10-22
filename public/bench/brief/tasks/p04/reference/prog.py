import sys


def main():
    path = sys.argv[1]
    rows = []
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            name, count = line.split(",")
            rows.append((name, int(count)))
    rows.sort(key=lambda r: -r[1])
    for name, _ in rows:
        print(name)


if __name__ == "__main__":
    main()
