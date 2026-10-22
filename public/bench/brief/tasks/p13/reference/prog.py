import os
import sys


def main():
    d = sys.argv[1]
    total = 0
    for name in os.listdir(d):
        p = os.path.join(d, name)
        if os.path.isfile(p) and name.endswith(".log"):
            total += os.path.getsize(p)
    print(total)


if __name__ == "__main__":
    main()
