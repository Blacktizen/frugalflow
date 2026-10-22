import os
import random
import sys

sys.dont_write_bytecode = True

SUBDIRS = ["records", "config", "cache"]
EXTS = ["csv", "json", "txt"]


def main():
    rng = random.Random(707)
    os.makedirs("store", exist_ok=True)
    pool = []
    for j in range(12):
        pool.append("payload-%d-" % j + ("x" * rng.randint(5, 40)))
    for i in range(48):
        sub = SUBDIRS[i % len(SUBDIRS)]
        folder = os.path.join("store", sub)
        os.makedirs(folder, exist_ok=True)
        ext = EXTS[(i * 2) % len(EXTS)]
        name = "entry_%02d.%s" % (i, ext)
        path = os.path.join(folder, name)
        content = pool[rng.randint(0, 11)]
        with open(path, "w") as handle:
            handle.write(content)


if __name__ == "__main__":
    main()
