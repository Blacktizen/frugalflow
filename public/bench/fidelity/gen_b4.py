#!/usr/bin/env python3
import argparse
import json
import os
import random
import re
import subprocess
import sys
import tempfile


def validate_pools(data):
    if not isinstance(data, dict):
        return False
    for lang in ("fr", "en"):
        if lang not in data:
            return False
        pool = data[lang]
        if not isinstance(pool, dict):
            return False
        if not isinstance(pool.get("words"), list) or len(pool["words"]) == 0:
            return False
        if not isinstance(pool.get("templates"), list) or len(pool["templates"]) < 3:
            return False
        if not isinstance(pool.get("filler"), list) or len(pool["filler"]) < 5:
            return False
        for pair in pool["words"]:
            if not isinstance(pair, list) or len(pair) != 2:
                return False
    return True


def generate(pools_path, out_dir, seed, count):
    try:
        with open(pools_path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (json.JSONDecodeError, OSError):
        sys.exit(2)

    if not validate_pools(data):
        sys.exit(2)

    rng = random.Random(seed)
    os.makedirs(out_dir, exist_ok=True)

    truth = {}
    for i in range(count):
        lang = "fr" if i % 2 == 0 else "en"
        pool = data[lang]
        W0 = pool["words"][(i // 2) % len(pool["words"])][0]
        W1 = pool["words"][(i // 2) % len(pool["words"])][1]

        chosen_tpl = rng.sample(pool["templates"], 3)
        chosen_fill = rng.sample(pool["filler"], 5)

        lines = [t.replace("{W}", W0) for t in chosen_tpl]
        lines.extend(chosen_fill)
        rng.shuffle(lines)

        fname = "t%02d.txt" % i
        text = "\n".join(lines) + "\n"
        with open(os.path.join(out_dir, fname), "w", encoding="utf-8", newline="\n") as f:
            f.write(text)

        pattern = r'\b' + re.escape(W0) + r'\b'
        expected = re.sub(pattern, W1, text)
        with open(os.path.join(out_dir, "t%02d.expected.txt" % i), "w", encoding="utf-8", newline="\n") as f:
            f.write(expected)

        truth[fname] = {"lang": lang, "from": W0, "to": W1, "lines": 8}

    with open(os.path.join(out_dir, "truth.json"), "w", encoding="utf-8", newline="\n") as f:
        json.dump(truth, f, ensure_ascii=False)


def run_autotest():
    total = 0
    passed = 0

    fixture = json.dumps({
        "note": "x",
        "fr": {"words": [["aa", "bb"]],
               "templates": ["t1 {W} one", "t2 {W} two", "t3 {W} three"],
               "filler": ["f1", "f2", "f3", "f4", "f5", "f6"]},
        "en": {"words": [["cc", "dd"]],
               "templates": ["u1 {W} one", "u2 {W} two", "u3 {W} three", "u4 {W} four"],
               "filler": ["g1", "g2", "g3", "g4", "g5"]}
    })

    # Test 1
    total += 1
    ok1 = True
    with tempfile.TemporaryDirectory() as tmp:
        pp = os.path.join(tmp, "pools.json")
        od = os.path.join(tmp, "out")
        with open(pp, "w", encoding="utf-8") as f:
            f.write(fixture)
        r = subprocess.run(
            [sys.executable, __file__, "--pools", pp, "--out", od, "--seed", "1", "--n", "4"],
            capture_output=True, text=True)
        files = sorted(os.listdir(od)) if os.path.isdir(od) else []
        line_counts = []
        if os.path.isdir(od):
            for fn in files:
                if fn.endswith(".txt") and not fn.endswith(".expected.txt") and fn != "truth.json":
                    with open(os.path.join(od, fn), "r", encoding="utf-8") as f:
                        line_counts.append(f.read().count("\n"))
        ok1 = r.returncode == 0 and len(files) == 9 and len(line_counts) == 4 and all(c == 8 for c in line_counts)
    if ok1:
        passed += 1
    print("PASS test1: 9 files, 8 lines each" if ok1
          else "FAIL test1: expected 9 files 8 lines, got rc=%d files=%d counts=%s"
          % (r.returncode, len(files), line_counts))

    # Test 2
    total += 1
    ok2 = True
    with tempfile.TemporaryDirectory() as tmp:
        pp = os.path.join(tmp, "pools.json")
        od = os.path.join(tmp, "out")
        with open(pp, "w", encoding="utf-8") as f:
            f.write(fixture)
        subprocess.run(
            [sys.executable, __file__, "--pools", pp, "--out", od, "--seed", "1", "--n", "4"],
            capture_output=True, text=True)
        with open(os.path.join(od, "t00.txt"), "r", encoding="utf-8") as f:
            c00 = f.read()
        with open(os.path.join(od, "t00.expected.txt"), "r", encoding="utf-8") as f:
            e00 = f.read()
        with open(os.path.join(od, "t01.txt"), "r", encoding="utf-8") as f:
            c01 = f.read()
        with open(os.path.join(od, "truth.json"), "r", encoding="utf-8") as f:
            tr = json.load(f)
        if len(re.findall(r'\baa\b', c00)) != 3:
            ok2 = False
        if len(re.findall(r'\bbb\b', e00)) != 3 or len(re.findall(r'\baa\b', e00)) != 0:
            ok2 = False
        if tr.get("t00.txt", {}).get("lang") != "fr" or tr.get("t00.txt", {}).get("from") != "aa":
            ok2 = False
        if tr.get("t01.txt", {}).get("lang") != "en" or tr.get("t01.txt", {}).get("from") != "cc":
            ok2 = False
        if tr.get("t01.txt", {}).get("to") != "dd":
            ok2 = False
        del c01
    if ok2:
        passed += 1
    print("PASS test2: t00 fr aa/bb, t01 en cc/dd correct" if ok2
          else "FAIL test2: word counts or lang mismatch")

    # Test 3
    total += 1
    ok3 = True
    with tempfile.TemporaryDirectory() as tmp:
        pp = os.path.join(tmp, "pools.json")
        with open(pp, "w", encoding="utf-8") as f:
            f.write(fixture)
        od1 = os.path.join(tmp, "o1")
        od2 = os.path.join(tmp, "o2")
        od3 = os.path.join(tmp, "o3")
        for od, sd in [(od1, "1"), (od2, "1"), (od3, "2")]:
            subprocess.run(
                [sys.executable, __file__, "--pools", pp, "--out", od, "--seed", sd, "--n", "4"],
                capture_output=True, text=True)
        f1 = sorted(os.listdir(od1))
        f2 = sorted(os.listdir(od2))
        if f1 != f2:
            ok3 = False
        for fn in f1:
            with open(os.path.join(od1, fn), "r", encoding="utf-8") as a, \
                 open(os.path.join(od2, fn), "r", encoding="utf-8") as b:
                if a.read() != b.read():
                    ok3 = False
        any_diff = False
        for fn in f1:
            if fn.endswith(".txt") and not fn.endswith(".expected.txt") and fn != "truth.json":
                p1 = os.path.join(od1, fn)
                p3 = os.path.join(od3, fn)
                if os.path.exists(p1) and os.path.exists(p3):
                    with open(p1, "r", encoding="utf-8") as a, open(p3, "r", encoding="utf-8") as b:
                        if a.read() != b.read():
                            any_diff = True
        if not any_diff:
            ok3 = False
    if ok3:
        passed += 1
    print("PASS test3: same seed identical, seed 2 differs" if ok3
          else "FAIL test3: determinism check failed")

    # Test 4
    total += 1
    ok4 = True
    with tempfile.TemporaryDirectory() as tmp:
        pp = os.path.join(tmp, "pools.json")
        od = os.path.join(tmp, "out")
        with open(pp, "w", encoding="utf-8") as f:
            f.write("not valid json {{{")
        r = subprocess.run(
            [sys.executable, __file__, "--pools", pp, "--out", od, "--seed", "1", "--n", "4"],
            capture_output=True, text=True)
        if r.returncode != 2:
            ok4 = False
        if os.path.isdir(od) and len(os.listdir(od)) > 0:
            ok4 = False
    if ok4:
        passed += 1
    print("PASS test4: invalid json -> exit 2, no files" if ok4
          else "FAIL test4: expected exit 2 no files, got rc=%d dir=%s"
          % (r.returncode, os.listdir(od) if os.path.isdir(od) else "absent"))

    sys.exit(0 if passed == total else 1)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pools", type=str)
    parser.add_argument("--out", type=str)
    parser.add_argument("--seed", type=int)
    parser.add_argument("--n", type=int)
    parser.add_argument("--autotest", action="store_true")
    args = parser.parse_args()

    if args.autotest:
        run_autotest()
    else:
        if args.pools is None or args.out is None or args.seed is None or args.n is None:
            sys.exit(2)
        generate(args.pools, args.out, args.seed, args.n)


if __name__ == "__main__":
    main()
