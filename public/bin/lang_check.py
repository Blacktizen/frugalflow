import json
import os
import re
import subprocess
import sys
import tempfile

ACCENTED = "àâäçéèêëîïôöùûüÿœæ"  # lang-ok
MARK = "lang-ok"
SKIP_DIRS = {"__pycache__", "data"}


def words(line):
    passages = re.findall(r"[^\W\d_]+", line)
    result = []
    for p in passages:
        p = re.sub(r"([a-zà-ÿ])([A-Z])", r"\1 \2", p)  # lang-ok
        for piece in p.split():
            result.append(piece.lower())
    return result


def scan(text, french, allowed):
    result = []
    for i, line in enumerate(text.splitlines(), 1):
        if MARK in line:
            continue
        seen = set()
        for w in words(line):
            if w in allowed:
                continue
            if w in seen:
                continue
            if w in french:
                seen.add(w)
                result.append((i, w, "word"))
            elif any(c in ACCENTED for c in w):
                seen.add(w)
                result.append((i, w, "accent"))
    return result


def check_tree(root, french, allowed, skip_paths):
    result = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        filenames.sort()
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for fname in filenames:
            full = os.path.join(dirpath, fname)
            if os.path.abspath(full) in skip_paths:
                continue
            rel = os.path.relpath(full, root)
            for (_ln, w, genre) in scan(os.path.basename(full), french, allowed):
                result.append((rel, 0, w, genre))
            try:
                with open(full, "r", encoding="utf-8") as f:
                    content = f.read()
            except UnicodeDecodeError:
                continue
            for (ln, w, genre) in scan(content, french, allowed):
                result.append((rel, ln, w, genre))
    return result


def main(argv):
    if argv == ["--notice"]:
        print("NAME      lang_check.py - says whether French words remain in a tree that must be in English.")
        print('READS     every file under --root except the data and __pycache__ folders and the files listed under "skip"; the JSON word list given by --words.')
        print("WRITES    nothing; prints one line per French word found, then LANG OK or LANG FAIL. Exit 0 clean, 1 words found, 2 usage.")
        print("EXAMPLE   python3 public/bin/lang_check.py --root public --words public/config/lang_words.json")
        print("PITFALLS  2026-09-26 French words were found by an AI review, one file at a time, and nothing kept them out afterwards.")
        print("          A line that must keep a French word (a pattern that reads French text) carries the marker lang-ok.")
        return 0

    if argv == ["--autotest"]:
        return _autotest()

    if len(argv) == 4 and argv[0] == "--root" and argv[2] == "--words":
        root = argv[1]
        words_file = argv[3]
        try:
            with open(words_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            french = set(data["french"])
            allowed = set(data["allowed"])
            skip = data.get("skip", [])
        except (OSError, json.JSONDecodeError, KeyError, TypeError):
            print("lang_check: cannot read word list")
            return 2
        skip_paths = {os.path.abspath(words_file)}
        for x in skip:
            skip_paths.add(os.path.abspath(os.path.join(root, x)))
        quadruplets = check_tree(root, french, allowed, skip_paths)
        for (rel, num, w, genre) in quadruplets:
            print(rel + ":" + str(num) + ": " + w + " (" + genre + ")")
        if not quadruplets:
            print("LANG OK 0 French words")
            return 0
        else:
            distinct_files = len(set(q[0] for q in quadruplets))
            print("LANG FAIL " + str(len(quadruplets)) + " French words in " + str(distinct_files) + " files")
            return 1
    else:
        print("usage: lang_check.py --notice | --autotest | --root DIR --words FILE")
        return 2


def _autotest():
    FR = {"chemin", "valeur", "epreuve", "rapport"}  # lang-ok
    OK = {"verdict"}
    TEXT = "x = 1\nchemin_valeur = getValeur(x2)  # verdict\ns = '\u00e9preuve'  # lang-ok\nt = 'd\u00e9j\u00e0 vu'\n"  # lang-ok
    TREE = {
        "bin/rapport_tool.py": "a = 1\nchemin = 2\n",  # lang-ok
        "bin/clean.py": "a = 1\n",
        "data/x.json": "chemin\n",  # lang-ok
        "__pycache__/y.py": "valeur\n",  # lang-ok
        "blob.bin": b"\xff\xfe\x00chemin",  # lang-ok
    }

    all_pass = True
    with tempfile.TemporaryDirectory() as tmp:
        for rel, content in TREE.items():
            path = os.path.join(tmp, rel)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            if isinstance(content, bytes):
                with open(path, "wb") as f:
                    f.write(content)
            else:
                with open(path, "w", encoding="utf-8") as f:
                    f.write(content)

        words_json = os.path.join(tmp, "words.json")
        with open(words_json, "w", encoding="utf-8") as f:
            json.dump({"french": sorted(FR), "allowed": sorted(OK)}, f)

        # Test 1
        e1a = ["chemin", "valeur", "get", "valeur", "x"]  # lang-ok
        g1a = words("chemin_valeur = getValeur(x2)")  # lang-ok
        e1b = []
        g1b = words("")
        e1c = ["déjà"]  # lang-ok
        g1c = words("déjà")  # lang-ok
        if g1a == e1a and g1b == e1b and g1c == e1c:
            print("PASS test 1: words()")
        else:
            all_pass = False
            print(f"FAIL test 1: expected {e1a}, {e1b}, {e1c} got {g1a}, {g1b}, {g1c}")

        # Test 2
        e2a = [(2, "chemin", "word"), (2, "valeur", "word"), (4, "déjà", "accent")]  # lang-ok
        g2a = scan(TEXT, FR, OK)
        e2b = []
        g2b = scan("verdict chemin", FR, {"chemin", "verdict"})  # lang-ok
        if g2a == e2a and g2b == e2b:
            print("PASS test 2: scan()")
        else:
            all_pass = False
            print(f"FAIL test 2: expected {e2a}, {e2b} got {g2a}, {g2b}")

        # Test 3
        skip_paths = {os.path.abspath(words_json)}
        e3 = [("bin/rapport_tool.py", 0, "rapport", "word"), ("bin/rapport_tool.py", 2, "chemin", "word")]  # lang-ok
        g3 = check_tree(tmp, FR, OK, skip_paths)
        if g3 == e3:
            print("PASS test 3: check_tree()")
        else:
            all_pass = False
            print(f"FAIL test 3: expected {e3} got {g3}")

        # Test 4
        r1 = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--root", tmp, "--words", words_json],
            capture_output=True, text=True,
        )
        lines1 = [l for l in r1.stdout.strip().splitlines() if l]
        last1 = lines1[-1] if lines1 else ""
        ok4a = (r1.returncode == 1 and last1 == "LANG FAIL 2 French words in 1 files")

        with open(words_json, "w", encoding="utf-8") as f:
            json.dump({"french": sorted(FR), "allowed": sorted(OK), "skip": ["bin/rapport_tool.py"]}, f)  # lang-ok
        r2 = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--root", tmp, "--words", words_json],
            capture_output=True, text=True,
        )
        lines2 = [l for l in r2.stdout.strip().splitlines() if l]
        last2 = lines2[-1] if lines2 else ""
        ok4b = (r2.returncode == 0 and last2 == "LANG OK 0 French words")

        with tempfile.TemporaryDirectory() as tmp2:
            with open(os.path.join(tmp2, "clean.py"), "w", encoding="utf-8") as f:
                f.write("a = 1\n")
            words_json2 = os.path.join(tmp2, "words.json")
            with open(words_json2, "w", encoding="utf-8") as f:
                json.dump({"french": sorted(FR), "allowed": sorted(OK)}, f)
            r3 = subprocess.run(
                [sys.executable, os.path.abspath(__file__), "--root", tmp2, "--words", words_json2],
                capture_output=True, text=True,
            )
            lines3 = [l for l in r3.stdout.strip().splitlines() if l]
            last3 = lines3[-1] if lines3 else ""
            ok4c = (r3.returncode == 0 and last3 == "LANG OK 0 French words")

        if ok4a and ok4b and ok4c:
            print("PASS test 4: subprocess exit codes")
        else:
            all_pass = False
            print(f"FAIL test 4: ok4a={ok4a} last1={last1!r} ok4b={ok4b} last2={last2!r} ok4c={ok4c} last3={last3!r}")

        # Test 5
        r_n = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--notice"],
            capture_output=True, text=True,
        )
        ok5a = r_n.returncode == 0 and r_n.stdout.startswith("NAME      lang_check.py")

        r_z = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True,
        )
        ok5b = r_z.returncode == 2 and r_z.stdout == "usage: lang_check.py --notice | --autotest | --root DIR --words FILE\n"

        r_x = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--root", tmp, "--words", os.path.join(tmp, "nope.json")],
            capture_output=True, text=True,
        )
        ok5c = r_x.returncode == 2 and r_x.stdout == "lang_check: cannot read word list\n"

        if ok5a and ok5b and ok5c:
            print("PASS test 5: CLI modes")
        else:
            all_pass = False
            print(f"FAIL test 5: ok5a={ok5a} ok5b={ok5b} ok5c={ok5c}")

    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "lang_check", sys.argv[1:])
