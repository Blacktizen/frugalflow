import argparse
import base64
import hashlib
import json
import os
import random
import subprocess
import sys
import tempfile


def clean(s):
    return s.replace("\u00a7", "")


def clean_pool(obj):
    if isinstance(obj, str):
        return clean(obj)
    if isinstance(obj, list):
        return [clean_pool(x) for x in obj]
    if isinstance(obj, dict):
        return {clean(k): clean_pool(v) for k, v in obj.items()}
    return obj


def json_escape(v):
    return v.replace("\\", "\\\\").replace("\"", "\\\"")


def make_value(form, parts, idx=0):
    if form == "split":
        return parts[idx]
    return parts[0]


def render_line(genre, where, label, value):
    if genre == "py":
        if where == "code":
            return label + " = \"" + value + "\""
        else:
            return "# " + value
    elif genre == "md":
        if where == "code":
            return "- " + label.lower() + " : " + value
        else:
            return "<!-- " + value + " -->"
    elif genre == "json":
        if where == "code":
            return "\"" + label.lower() + "\": \"" + json_escape(value) + "\""
        else:
            return "\"_comment\": \"" + json_escape(value) + "\""
    elif genre == "log":
        if where == "code":
            return "2026-03-04 10:11:12 INFO " + label.lower() + "=" + value
        else:
            return "2026-03-04 10:11:12 INFO # " + value


def render_decoy_line(genre, phrase):
    if genre == "py":
        return "# " + phrase
    elif genre == "md":
        return phrase
    elif genre == "json":
        return "\"doc\": \"" + json_escape(phrase) + "\""
    elif genre == "log":
        return "2026-03-04 10:11:12 INFO " + phrase


def build_file(genre, rng, filler_list, inserted_lines):
    num_filler = rng.randint(12, 22)
    fillers = [rng.choice(filler_list) for _ in range(num_filler)]
    num_inserted = len(inserted_lines)

    if genre == "json":
        min_pos = 2
        max_pos = num_filler - 1
        pos = rng.randint(min_pos, max_pos)
        content = fillers[:pos] + inserted_lines + fillers[pos:]
        out_lines = ["{"]
        for line in content:
            out_lines.append("  " + line + ",")
        out_lines.append("  \"end\": true")
        out_lines.append("}")
        line_numbers = []
        for j in range(num_inserted):
            line_numbers.append(pos + j + 2)
        return "\n".join(out_lines) + "\n", line_numbers
    else:
        min_pos = 3
        max_pos = num_filler - 1
        pos = rng.randint(min_pos, max_pos)
        all_lines = fillers[:pos] + inserted_lines + fillers[pos:]
        line_numbers = []
        for j in range(num_inserted):
            line_numbers.append(pos + j + 1)
        return "\n".join(all_lines) + "\n", line_numbers


def generate_corpus(pools_path, out_dir, seed):
    try:
        with open(pools_path, "r", encoding="utf-8") as f:
            raw = json.load(f)
    except (json.JSONDecodeError, ValueError):
        return 2
    except (OSError, IOError):
        return 2

    pools = clean_pool(raw)

    if "leaks" not in pools or "decoys" not in pools or "filler" not in pools:
        return 2

    leaks = pools["leaks"]
    decoys = pools["decoys"]
    filler = pools["filler"]

    total = len(leaks) + len(decoys)
    corpus_dir = os.path.join(out_dir, "corpus")
    os.makedirs(corpus_dir, exist_ok=True)

    rng = random.Random(seed)
    ext_map = {0: "py", 1: "md", 2: "json", 3: "log"}

    verite = {}
    file_hashes = {}

    for i in range(total):
        genre = ext_map[i % 4]
        fname = "f%02d.%s" % (i, genre)
        filler_list = filler[genre]

        if i < len(leaks):
            leak = leaks[i]
            label = leak["label"]
            where = leak["where"]
            form = leak["form"]
            parts = leak["parts"]

            if form == "split":
                val1 = make_value(form, parts, 0)
                val2 = make_value(form, parts, 1)
                label2 = label + "_2"
                line1 = render_line(genre, where, label, val1)
                line2 = render_line(genre, where, label2, val2)
                inserted = [line1, line2]
            else:
                if form == "encoded":
                    val = base64.b64encode(parts[0].encode("utf-8")).decode("ascii")
                elif form == "plain":
                    val = parts[0]
                else:
                    val = parts[0]
                inserted = [render_line(genre, where, label, val)]

            content, line_nums = build_file(genre, rng, filler_list, inserted)
            hard = (form != "plain") or (where == "comment")
            verite[fname] = {
                "leaks": [{"id": leak["id"], "type": leak["type"], "form": form, "lines": line_nums}],
                "hard": hard,
                "decoy": False,
            }
        else:
            phrase = decoys[i - len(leaks)]
            inserted = [render_decoy_line(genre, phrase)]
            content, line_nums = build_file(genre, rng, filler_list, inserted)
            verite[fname] = {
                "leaks": [],
                "hard": False,
                "decoy": True,
            }

        fpath = os.path.join(corpus_dir, fname)
        with open(fpath, "w", encoding="utf-8", newline="") as f:
            f.write(content)
        file_hashes[fname] = hashlib.sha256(content.encode("utf-8")).hexdigest()

    verite_path = os.path.join(out_dir, "verite.json")
    with open(verite_path, "w", encoding="utf-8", newline="") as f:
        json.dump(verite, f, indent=2)
        f.write("\n")

    sha_path = os.path.join(out_dir, "corpus.sha256")
    sorted_names = sorted(file_hashes.keys())
    with open(sha_path, "w", encoding="utf-8", newline="") as f:
        for name in sorted_names:
            f.write(file_hashes[name] + "  " + name + "\n")

    return 0


def copy_dir(src, dst):
    os.makedirs(dst, exist_ok=True)
    for item in os.listdir(src):
        s = os.path.join(src, item)
        d = os.path.join(dst, item)
        if os.path.isdir(s):
            copy_dir(s, d)
        else:
            with open(s, "rb") as fi:
                with open(d, "wb") as fo:
                    fo.write(fi.read())


def run_autotest():
    results = []
    fixture_pools = (
        "{\"note\": \"x\",\n"
        " \"leaks\": [\n"
        "  {\"id\": \"a1\", \"type\": \"email\", \"where\": \"code\", \"form\": \"plain\", \"parts\": [\"val\u00a7one\"], \"label\": \"CONTACT\"},\n"
        "  {\"id\": \"a2\", \"type\": \"private_name\", \"where\": \"comment\", \"form\": \"case\", \"parts\": [\"VALTWO\"], \"label\": \"NOTE\"},\n"
        "  {\"id\": \"a3\", \"type\": \"api_key\", \"where\": \"code\", \"form\": \"split\", \"parts\": [\"valthree\", \"valfour\"], \"label\": \"KEY\"},\n"
        "  {\"id\": \"a4\", \"type\": \"token\", \"where\": \"code\", \"form\": \"encoded\", \"parts\": [\"valfive\"], \"label\": \"TOKEN_B64\"}\n"
        " ],\n"
        " \"decoys\": [\"a harmless sentence\", \"another harmless sentence\"],\n"
        " \"filler\": {\n"
        "  \"py\": [\"import os\", \"import sys\", \"\", \"def f():\", \"    return 1\", \"\", \"def g():\", \"    return 2\", \"\", \"x = 3\", \"y = 4\", \"z = 5\", \"w = 6\"],\n"
        "  \"md\": [\"# Title\", \"\", \"text one\", \"text two\", \"\", \"text three\", \"\", \"text four\", \"text five\", \"\", \"text six\", \"text seven\", \"text eight\"],\n"
        "  \"json\": [\"\\\"a\\\": 1\", \"\\\"b\\\": 2\", \"\\\"c\\\": 3\", \"\\\"d\\\": 4\", \"\\\"e\\\": 5\", \"\\\"f\\\": 6\", \"\\\"g\\\": 7\", \"\\\"h\\\": 8\", \"\\\"i\\\": 9\", \"\\\"j\\\": 10\", \"\\\"k\\\": 11\", \"\\\"l\\\": 12\"],\n"
        "  \"log\": [\"INFO one\", \"INFO two\", \"INFO three\", \"INFO four\", \"INFO five\", \"INFO six\", \"INFO seven\", \"INFO eight\", \"INFO nine\", \"INFO ten\", \"INFO eleven\", \"INFO twelve\"]\n"
        " }}\n"
    )

    def run_gen(pools_content, seed, tmp_out):
        pools_file = os.path.join(tmp_out, "pools.json")
        with open(pools_file, "w", encoding="utf-8") as f:
            f.write(pools_content)
        out_dir = os.path.join(tmp_out, "out")
        os.makedirs(out_dir, exist_ok=True)
        cmd = [sys.executable, os.path.abspath(__file__),
               "--pools", pools_file, "--out", out_dir, "--seed", str(seed)]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        return proc.returncode, out_dir

    with tempfile.TemporaryDirectory() as tmp:
        rc, out_dir = run_gen(fixture_pools, 1, tmp)
        corpus_dir = os.path.join(out_dir, "corpus")
        if os.path.isdir(corpus_dir):
            files = sorted(os.listdir(corpus_dir))
        else:
            files = []
        expected_files = ["f00.py", "f01.md", "f02.json", "f03.log", "f04.py", "f05.md"]
        ok = (rc == 0 and files == expected_files)
        results.append(("PASS" if ok else "FAIL",
                        "1: rc=0, 6 files f00-f05 extensions py/md/json/log/py/md",
                        "rc=%d files=%s" % (rc, files)))

    with tempfile.TemporaryDirectory() as tmp:
        rc, out_dir = run_gen(fixture_pools, 1, tmp)
        corpus_dir = os.path.join(out_dir, "corpus")
        verite_path = os.path.join(out_dir, "verite.json")
        ok = (rc == 0)
        msg2 = "2: line checks for f00/f03/f02"
        notes = []
        try:
            with open(verite_path, "r", encoding="utf-8") as f:
                verite = json.load(f)

            ln = verite["f00.py"]["leaks"][0]["lines"]
            if not isinstance(ln, list):
                ok = False
                notes.append("f00 lines not a list")
            else:
                with open(os.path.join(corpus_dir, "f00.py"), "r", encoding="utf-8") as f:
                    lines_f00 = f.read().split("\n")
                idx = ln[0] - 1
                if idx < 0 or idx >= len(lines_f00) or "valone" not in lines_f00[idx]:
                    ok = False
                    notes.append("f00 valone not on line %d: got [%s]" % (
                        ln[0],
                        lines_f00[idx] if 0 <= idx < len(lines_f00) else "OOB"))

            b64_val = base64.b64encode(b"valfive").decode("ascii")
            ln3 = verite["f03.log"]["leaks"][0]["lines"]
            if not isinstance(ln3, list) or len(ln3) != 1:
                ok = False
                notes.append("f03 lines wrong: %s" % ln3)
            else:
                with open(os.path.join(corpus_dir, "f03.log"), "r", encoding="utf-8") as f:
                    lines_f03 = f.read().split("\n")
                idx3 = ln3[0] - 1
                if idx3 < 0 or idx3 >= len(lines_f03) or b64_val not in lines_f03[idx3]:
                    ok = False
                    notes.append("f03 b64 not on line %d: got [%s]" % (
                        ln3[0],
                        lines_f03[idx3] if 0 <= idx3 < len(lines_f03) else "OOB"))

            ln2s = verite["f02.json"]["leaks"][0]["lines"]
            if len(ln2s) != 2 or ln2s[1] - ln2s[0] != 1:
                ok = False
                notes.append("f02 lines not 2 consecutive: %s" % ln2s)
            else:
                with open(os.path.join(corpus_dir, "f02.json"), "r", encoding="utf-8") as f:
                    lines_f02 = f.read().split("\n")
                if "valthree" not in lines_f02[ln2s[0] - 1]:
                    ok = False
                    notes.append("f02 valthree not on line %d: got [%s]" % (
                        ln2s[0], lines_f02[ln2s[0] - 1]))
                if "valfour" not in lines_f02[ln2s[1] - 1]:
                    ok = False
                    notes.append("f02 valfour not on line %d: got [%s]" % (
                        ln2s[1], lines_f02[ln2s[1] - 1]))
        except Exception as e:
            ok = False
            notes.append(str(e))
        results.append(("PASS" if ok else "FAIL", msg2, "; ".join(notes) if notes else "all checks pass"))

    with tempfile.TemporaryDirectory() as tmp:
        rc1, out1 = run_gen(fixture_pools, 1, tmp)
        copy_dir(out1, os.path.join(tmp, "h1"))
        pools_file = os.path.join(tmp, "pools.json")
        with open(pools_file, "w", encoding="utf-8") as f:
            f.write(fixture_pools)
        out2 = os.path.join(tmp, "out2")
        os.makedirs(out2, exist_ok=True)
        subprocess.run([sys.executable, os.path.abspath(__file__),
                       "--pools", pools_file, "--out", out2, "--seed", "1"],
                       capture_output=True, text=True)
        copy_dir(out2, os.path.join(tmp, "h2"))
        sha1 = open(os.path.join(tmp, "h1", "corpus.sha256"), "r").read()
        sha2 = open(os.path.join(tmp, "h2", "corpus.sha256"), "r").read()
        same = (sha1 == sha2)

        out3 = os.path.join(tmp, "out3")
        os.makedirs(out3, exist_ok=True)
        subprocess.run([sys.executable, os.path.abspath(__file__),
                       "--pools", pools_file, "--out", out3, "--seed", "2"],
                       capture_output=True, text=True)
        copy_dir(out3, os.path.join(tmp, "h3"))
        sha3 = open(os.path.join(tmp, "h3", "corpus.sha256"), "r").read()
        diff = (sha1 != sha3)

        ok = same and diff
        results.append(("PASS" if ok else "FAIL",
                        "3: seed1 deterministic, seed2 differs",
                        "same=%s diff=%s" % (same, diff)))

    with tempfile.TemporaryDirectory() as tmp:
        rc, out_dir = run_gen(fixture_pools, 1, tmp)
        corpus_dir = os.path.join(out_dir, "corpus")
        verite_path = os.path.join(out_dir, "verite.json")
        ok = (rc == 0)
        try:
            with open(os.path.join(corpus_dir, "f02.json"), "r", encoding="utf-8") as f:
                json.loads(f.read())
            with open(verite_path, "r", encoding="utf-8") as f:
                verite = json.load(f)
            if len(verite) != 6:
                ok = False
            decoy_count = sum(1 for v in verite.values() if v.get("decoy"))
            if decoy_count != 2:
                ok = False
            if not verite["f01.md"]["hard"]:
                ok = False
        except Exception:
            ok = False
        results.append(("PASS" if ok else "FAIL",
                        "4: f02 json valid, verite 6 entries, 2 decoy, f01 hard",
                        "rc=%d" % rc))

    with tempfile.TemporaryDirectory() as tmp:
        pools_file = os.path.join(tmp, "pools.json")
        with open(pools_file, "w") as f:
            f.write("NOT VALID JSON {{{")
        out_dir = os.path.join(tmp, "out")
        os.makedirs(out_dir, exist_ok=True)
        cmd = [sys.executable, os.path.abspath(__file__),
               "--pools", pools_file, "--out", out_dir, "--seed", "1"]
        proc = subprocess.run(cmd, capture_output=True, text=True)
        rc = proc.returncode
        corpus_exists = os.path.isdir(os.path.join(out_dir, "corpus"))
        ok = (rc == 2 and not corpus_exists)
        results.append(("PASS" if ok else "FAIL",
                        "5: invalid pools -> rc=2, no corpus",
                        "rc=%d corpus=%s" % (rc, corpus_exists)))

    all_pass = True
    for status, expected, obtained in results:
        print("%s [%s] expected: %s | obtained: %s" % (status, status, expected, obtained))
        if status == "FAIL":
            all_pass = False
    return 0 if all_pass else 1


def main():
    if "--autotest" in sys.argv:
        sys.exit(run_autotest())

    parser = argparse.ArgumentParser()
    parser.add_argument("--pools", required=True)
    parser.add_argument("--out", required=True)
    parser.add_argument("--seed", type=int, required=True)
    args = parser.parse_args()

    rc = generate_corpus(args.pools, args.out, args.seed)
    sys.exit(rc)


if __name__ == "__main__":
    main()
