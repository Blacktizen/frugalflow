import os
import random
import sys

sys.dont_write_bytecode = True

SUBDIRS = ["images", "data", "cache", "logs", "meta"]


def main():
    rng = random.Random(881)
    os.makedirs("assets", exist_ok=True)
    for i in range(50):
        sub = SUBDIRS[i % len(SUBDIRS)]
        folder = os.path.join("assets", sub)
        os.makedirs(folder, exist_ok=True)
        name = "item_%03d.bin" % i
        path = os.path.join(folder, name)
        if i % 6 == 0:
            content = ""
        else:
            content = ("chunk-%d-" % i) * rng.randint(1, 30)
        with open(path, "w") as handle:
            handle.write(content)


if __name__ == "__main__":
    main()
