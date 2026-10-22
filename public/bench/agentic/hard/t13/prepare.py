import os
import random
import sys

sys.dont_write_bytecode = True

SUBDIRS = ["src", "lib", "docs", "tests", "config", "assets"]
EXTS = ["py", "js", "md", "txt", "json", "yml", "html", "css"]


def main():
    rng = random.Random(5150)
    os.makedirs("tree", exist_ok=True)
    for i in range(60):
        sub = SUBDIRS[i % len(SUBDIRS)]
        ext = EXTS[(i * 5 + 3) % len(EXTS)]
        folder = os.path.join("tree", sub)
        os.makedirs(folder, exist_ok=True)
        name = "file_%02d.%s" % (i, ext)
        path = os.path.join(folder, name)
        lines = []
        for _ in range(rng.randint(3, 12)):
            lines.append("line %d in %s" % (rng.randint(0, 9999), name))
        if i % 7 == 3:
            lines.append("FIXME: review this part")
        with open(path, "w") as handle:
            handle.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
