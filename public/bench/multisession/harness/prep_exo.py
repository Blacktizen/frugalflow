import json
import os
import re
import shutil
import sys

IGNORED = {"paasio", "react", "hangman", "grep", "rest-api"}


def transform_test(text, module):
    text = re.sub(
        "from " + re.escape(module) + " import",
        "from kata." + module + " import",
        text,
        flags=re.MULTILINE,
    )
    text = re.sub(
        "^([ \t]*)import " + re.escape(module) + r"\b",
        r"\1from kata import " + module,
        text,
        flags=re.MULTILINE,
    )
    return text


def main():
    src, dst = sys.argv[1], sys.argv[2]
    count = 0
    for slug in sorted(os.listdir(src)):
        if slug in IGNORED:
            continue
        ex_dir = os.path.join(src, slug)
        if not os.path.isdir(ex_dir):
            continue
        module = slug.replace("-", "_")
        with open(os.path.join(ex_dir, ".meta", "config.json"), encoding="utf-8") as fh:
            config = json.load(fh)
        assert config["files"]["solution"] == [module + ".py"]
        out_dir = os.path.join(dst, slug)
        os.makedirs(out_dir, exist_ok=True)
        shutil.copyfile(
            os.path.join(ex_dir, module + ".py"),
            os.path.join(out_dir, "stub.py"),
        )
        with open(os.path.join(ex_dir, module + "_test.py"), encoding="utf-8") as fh:
            test_text = fh.read()
        with open(os.path.join(out_dir, "test.py"), "w", encoding="utf-8") as fh:
            fh.write(transform_test(test_text, module))
        with open(os.path.join(ex_dir, ".docs", "instructions.md"), encoding="utf-8") as fh:
            doc = fh.read()
        append_path = os.path.join(ex_dir, ".docs", "instructions.append.md")
        if os.path.exists(append_path):
            with open(append_path, encoding="utf-8") as fh:
                doc += "\n" + fh.read()
        with open(os.path.join(out_dir, "doc.md"), "w", encoding="utf-8") as fh:
            fh.write(doc)
        count += 1
    print(str(count) + " exercices")


if __name__ == "__main__":
    main()
