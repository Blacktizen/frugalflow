import sys
from datetime import datetime


def main():
    path = sys.argv[1]
    thr = datetime.strptime(sys.argv[2], "%d/%m/%Y")
    n = 0
    with open(path) as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            d, _ = line.split(",", 1)
            dt = datetime.strptime(d, "%d/%m/%Y")
            if dt > thr:
                n += 1
    print(n)


if __name__ == "__main__":
    main()
