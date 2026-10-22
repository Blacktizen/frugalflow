import sys


def main():
    path = sys.argv[1]
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            _, status = line.split(",", 1)
            if status == "A":
                n += 1
    print(n)


if __name__ == "__main__":
    main()
