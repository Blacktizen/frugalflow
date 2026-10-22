import os
import random
import sys

sys.dont_write_bytecode = True

EXTS = ["py", "md", "txt", "cfg"]


def main():
    rng = random.Random(31337)
    os.makedirs("project", exist_ok=True)
    for i in range(55):
        ext = EXTS[i % len(EXTS)]
        name = "mod_%02d.%s" % (i, ext)
        path = os.path.join("project", name)
        lines = []
        for _ in range(rng.randint(0, 25)):
            lines.append("row %d of %s" % (rng.randint(0, 999), name))
        if i % 5 == 1:
            lines.append("TODO: finish the %s handler" % ext)
        content = "\n".join(lines)
        if lines:
            content += "\n"
        with open(path, "w") as handle:
            handle.write(content)


if __name__ == "__main__":
    main()
