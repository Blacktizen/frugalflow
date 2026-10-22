import sys


def main():
    path = sys.argv[1]
    n = 0
    with open(path) as f:
        for line in f:
            if not line.startswith(";"):
                n += 1
    print(n)


if __name__ == "__main__":
    main()
