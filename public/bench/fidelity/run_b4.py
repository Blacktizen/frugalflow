import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import unicodedata


U2019 = chr(0x2019)


def fold(text):
    repl = {}
    for cp in (0x2018, 0x2019, 0x201B, 0x2032):
        repl[chr(cp)] = chr(0x27)
    for cp in (0x201C, 0x201D, 0x201E, 0x2033, 0x00AB, 0x00BB):
        repl[chr(cp)] = chr(0x22)
    for cp in (0x2010, 0x2011, 0x2012, 0x2013, 0x2014, 0x2015, 0x2212):
        repl[chr(cp)] = chr(0x2D)
    repl[chr(0x2026)] = "..."
    out = []
    for ch in text:
        if ch in repl:
            out.append(repl[ch])
        elif unicodedata.category(ch) == "Zs":
            out.append(" ")
        else:
            out.append(ch)
    return "".join(out)


def extract_code_block(text):
    lines = text.split("\n")
    start = None
    for i, line in enumerate(lines):
        if line.startswith("```"):
            start = i
            break
    if start is None:
        return None
    for i in range(start + 1, len(lines)):
        if lines[i].rstrip() == "```":
            content = "\n".join(lines[start + 1:i])
            return content
    return None


def build_instruction(frm, to, original):
    return (
        'Rewrite the text below. Change ONLY this: replace every '
        'occurrence of the word "' + frm + '" with "' + to + '". '
        'Everything else must stay exactly the same, line by line. '
        'Reply with the full text only, in ONE code block.\n\n'
        '=== TEXT ===\n' + original
    )


def read_tokens(ffhome):
    path = os.path.join(ffhome, "delegations.jsonl")
    if not os.path.isfile(path):
        return 0, 0
    try:
        with open(path, "r", encoding="utf-8") as f:
            lines = f.read().strip().split("\n")
        if not lines:
            return 0, 0
        last = json.loads(lines[-1])
        return int(last.get("tokens_in", 0)), int(last.get("tokens_out", 0))
    except (json.JSONDecodeError, OSError, ValueError):
        return 0, 0


def cmd_run(args):
    texts_dir = os.path.abspath(args.texts)
    bin_dir = os.path.abspath(args.bin)
    models_file = os.path.abspath(args.models)
    fidelite_path = os.path.abspath(args.fidelite)
    result_path = os.path.abspath(args.out)
    reps = args.reps
    effort = args.effort
    write_flag = args.write_flag

    truth_path = os.path.join(texts_dir, "truth.json")
    if not os.path.isfile(truth_path):
        sys.stderr.write("Missing file: " + truth_path + "\n")
        sys.exit(2)
    if not os.path.isfile(os.path.join(bin_dir, "delegate.py")):
        sys.stderr.write("Missing file: delegate.py in " + bin_dir + "\n")
        sys.exit(2)
    if not os.path.isfile(fidelite_path):
        sys.stderr.write("Missing file: " + fidelite_path + "\n")
        sys.exit(2)

    ffhome = tempfile.mkdtemp(prefix="ffhome_")
    out_dir = os.path.join(os.path.dirname(result_path), "out")
    os.makedirs(out_dir, exist_ok=True)

    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    records = []
    for text_name, meta in truth.items():
        original_path = os.path.join(texts_dir, text_name)
        if not os.path.isfile(original_path):
            continue
        with open(original_path, "r", encoding="utf-8") as f:
            original = f.read()
        frm = meta["from"]
        to = meta["to"]
        for rep in range(1, reps + 1):
            instruction = build_instruction(frm, to, original)
            prompt_file = os.path.join(ffhome, "prompt.txt")
            with open(prompt_file, "w", encoding="utf-8", newline="\n") as f:
                f.write(instruction)

            delegate_script = os.path.join(bin_dir, "delegate.py")
            env = dict(os.environ)
            env["FRUGALFLOW_HOME"] = ffhome
            cmd = [
                sys.executable, delegate_script,
                "--role", "documents",
                "--file", prompt_file,
                "--models", models_file,
                "--effort", effort,
                "--brief-waiver", "bench prompt, not a code brief",
            ]
            try:
                proc = subprocess.run(
                    cmd, capture_output=True, text=True,
                    timeout=600, env=env,
                )
                if proc.returncode != 0:
                    response = ""
                else:
                    response = proc.stdout
            except subprocess.TimeoutExpired:
                response = ""

            tokens_in, tokens_out = read_tokens(ffhome)

            extracted = extract_code_block(response)
            if extracted is None:
                error = True
                produced = ""
            else:
                produced = extracted
                if produced == "":
                    error = True
                else:
                    error = False

            if produced and not produced.endswith("\n"):
                produced += "\n"

            stem = text_name.rsplit(".", 1)[0]
            c0_name = stem + ".r" + str(rep) + ".c0.txt"
            c1_name = stem + ".r" + str(rep) + ".c1.txt"
            c0_path = os.path.join(out_dir, c0_name)
            c1_path = os.path.join(out_dir, c1_name)

            with open(c0_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(produced)

            with open(c1_path, "w", encoding="utf-8", newline="\n") as f:
                f.write(produced)

            fidel_cmd = [sys.executable, fidelite_path, original_path, c1_path, write_flag]
            try:
                fid_proc = subprocess.run(fidel_cmd, capture_output=True, text=True, timeout=60)
                fidelite_exit = fid_proc.returncode
            except subprocess.TimeoutExpired:
                fidelite_exit = -1

            records.append({
                "text": text_name,
                "rep": rep,
                "error": error,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "fidelite_exit": fidelite_exit,
                "c0_path": c0_name,
                "c1_path": c1_name,
            })

    with open(result_path, "w", encoding="utf-8", newline="\n") as f:
        json.dump({"records": records}, f, indent=2, ensure_ascii=False)
        f.write("\n")

    shutil.rmtree(ffhome, ignore_errors=True)
    sys.exit(0)


import shutil


def cmd_report(args):
    result_path = os.path.abspath(args.result)
    texts_dir = os.path.abspath(args.texts)

    if not os.path.isfile(result_path):
        sys.stderr.write("Missing file: " + result_path + "\n")
        sys.exit(2)
    truth_path = os.path.join(texts_dir, "truth.json")
    if not os.path.isfile(truth_path):
        sys.stderr.write("Missing file: " + truth_path + "\n")
        sys.exit(2)

    with open(result_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    records = data.get("records", [])

    with open(truth_path, "r", encoding="utf-8") as f:
        truth = json.load(f)

    out_dir = os.path.join(os.path.dirname(result_path), "out")

    runs = len(records)
    errors = sum(1 for r in records if r.get("error"))
    structure_changed = 0
    lines_total = 0

    c0_exact = 0
    c0_typo = 0
    c0_other = 0
    c1_exact = 0
    c1_typo = 0
    c1_other = 0

    background_touched = 0
    good_lines_damaged = 0
    fidelite_changed_runs = 0
    fidelite_errors = 0

    for rec in records:
        if rec.get("fidelite_exit") == 1:
            fidelite_changed_runs += 1
        fe = rec.get("fidelite_exit")
        if fe is None or (fe != 0 and fe != 1):
            fidelite_errors += 1

        if rec.get("error"):
            continue

        text_name = rec["text"]
        meta = truth.get(text_name)
        if meta is None:
            continue
        expected_name = text_name.rsplit(".", 1)[0] + ".expected.txt"
        expected_path = os.path.join(texts_dir, expected_name)
        if not os.path.isfile(expected_path):
            structure_changed += 1
            continue

        c0_file = os.path.join(out_dir, rec["c0_path"])
        c1_file = os.path.join(out_dir, rec["c1_path"])
        if not os.path.isfile(c0_file) or not os.path.isfile(c1_file):
            structure_changed += 1
            continue

        with open(expected_path, "r", encoding="utf-8") as f:
            expected = f.read()
        with open(c0_file, "r", encoding="utf-8") as f:
            c0_text = f.read()
        with open(c1_file, "r", encoding="utf-8") as f:
            c1_text = f.read()

        exp_lines = expected.splitlines()
        c0_lines = c0_text.splitlines()
        c1_lines = c1_text.splitlines()

        if len(exp_lines) != len(c0_lines) or len(exp_lines) != len(c1_lines):
            structure_changed += 1
            continue

        for i in range(len(exp_lines)):
            lines_total += 1
            el = exp_lines[i]
            c0l = c0_lines[i]
            c1l = c1_lines[i]

            # C0 comparison
            if c0l == el:
                c0_exact += 1
            elif fold(c0l) == fold(el):
                c0_typo += 1
            else:
                c0_other += 1

            # C1 comparison
            if c1l == el:
                c1_exact += 1
            elif fold(c1l) == fold(el):
                c1_typo += 1
            else:
                c1_other += 1

            # background_touched
            if fold(c1l) != fold(c0l):
                background_touched += 1

            # good_lines_damaged: C0 exact but C1 not exact
            if c0l == el and c1l != el:
                good_lines_damaged += 1

    def damaged_pct(typo, total):
        if total == 0:
            return 0.0
        return round(typo / total * 100, 2)

    result = {
        "runs": runs,
        "errors": errors,
        "structure_changed": structure_changed,
        "lines_total": lines_total,
        "C0": {
            "exact": c0_exact,
            "typo_only": c0_typo,
            "other": c0_other,
            "damaged_pct": damaged_pct(c0_typo, lines_total),
        },
        "C1": {
            "exact": c1_exact,
            "typo_only": c1_typo,
            "other": c1_other,
            "damaged_pct": damaged_pct(c1_typo, lines_total),
        },
        "background_touched": background_touched,
        "good_lines_damaged": good_lines_damaged,
        "fidelite_changed_runs": fidelite_changed_runs,
        "fidelite_errors": fidelite_errors,
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    sys.exit(0)


def run_autotest():
    u2019 = chr(0x2019)
    tmp = tempfile.mkdtemp(prefix="autotest_")
    try:
        bin_dir = os.path.join(tmp, "bin")
        os.makedirs(bin_dir)
        texts_dir = os.path.join(tmp, "texts")
        os.makedirs(texts_dir)
        out_dir = os.path.join(tmp, "result")
        os.makedirs(out_dir)

        delegate_code = (
            "import re\nimport sys\n\n"
            "t = open(sys.argv[sys.argv.index(\"--file\") + 1], encoding=\"utf-8\").read()\n"
            "m = re.search(r'word \"(.+?)\" with \"(.+?)\"', t)\n"
            "body = t.split(\"=== TEXT ===\\n\", 1)[1]\n"
            "body = re.sub(r\"\\b\" + re.escape(m.group(1)) + r\"\\b\", m.group(2), body)\n"
            "body = body.replace(chr(0x2019), chr(0x27))\n"
            "print(\"```\\n\" + body + \"```\")\n"
        )
        with open(os.path.join(bin_dir, "delegate.py"), "w", encoding="utf-8", newline="\n") as f:
            f.write(delegate_code)

        fid_code = (
            "import sys\n\n"
            "o = open(sys.argv[1], encoding=\"utf-8\").read().split(\"\\n\")\n"
            "p = open(sys.argv[2], encoding=\"utf-8\").read().split(\"\\n\")\n"
            "n = 0\n"
            "for i in range(min(len(o), len(p))):\n"
            "    if p[i].replace(chr(0x27), chr(0x2019)) == o[i] and p[i] != o[i]:\n"
            "        p[i] = o[i]\n"
            "        n += 1\n"
            "if n:\n"
            "    open(sys.argv[2], \"w\", encoding=\"utf-8\").write(\"\\n\".join(p))\n"
            "sys.exit(1 if n else 0)\n"
        )
        fid_path = os.path.join(tmp, "fid.py")
        with open(fid_path, "w", encoding="utf-8", newline="\n") as f:
            f.write(fid_code)

        # Write text fixtures
        t00_content = "l" + u2019 + "aa one\nplain aa\nit" + u2019 + "s fine\n"
        with open(os.path.join(texts_dir, "t00.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(t00_content)

        t00_expected = "l" + u2019 + "bb one\nplain bb\nit" + u2019 + "s fine\n"
        with open(os.path.join(texts_dir, "t00.expected.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(t00_expected)

        t01_content = "aa here\nkeep this\nand this\n"
        with open(os.path.join(texts_dir, "t01.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(t01_content)

        t01_expected = "bb here\nkeep this\nand this\n"
        with open(os.path.join(texts_dir, "t01.expected.txt"), "w", encoding="utf-8", newline="\n") as f:
            f.write(t01_expected)

        truth = {
            "t00.txt": {"lang": "fr", "from": "aa", "to": "bb", "lines": 3},
            "t01.txt": {"lang": "en", "from": "aa", "to": "bb", "lines": 3},
        }
        with open(os.path.join(texts_dir, "truth.json"), "w", encoding="utf-8", newline="\n") as f:
            json.dump(truth, f)
            f.write("\n")

        models_path = os.path.join(tmp, "models.json")
        with open(models_path, "w", encoding="utf-8", newline="\n") as f:
            f.write("{}\n")

        result_path = os.path.join(out_dir, "RESULT.json")
        script = os.path.abspath(sys.argv[0])

        # Test 1: run
        run_args = [
            sys.executable, script, "run",
            "--texts", texts_dir,
            "--reps", "1",
            "--bin", bin_dir,
            "--models", models_path,
            "--fidelite", fid_path,
            "--out", result_path,
        ]
        proc1 = subprocess.run(run_args, capture_output=True, text=True)
        exit1 = proc1.returncode
        ok1 = False
        if exit1 == 0 and os.path.isfile(result_path):
            with open(result_path, "r", encoding="utf-8") as f:
                rdata = json.load(f)
            recs = rdata.get("records", [])
            if len(recs) == 2:
                r00 = [r for r in recs if r["text"] == "t00.txt"]
                r01 = [r for r in recs if r["text"] == "t01.txt"]
                if (r00 and not r00[0]["error"] and r00[0]["fidelite_exit"] == 1
                        and r01 and not r01[0]["error"] and r01[0]["fidelite_exit"] == 0):
                    c0_00 = os.path.join(out_dir, "out", "t00.r1.c0.txt")
                    c1_00 = os.path.join(out_dir, "out", "t00.r1.c1.txt")
                    if os.path.isfile(c0_00):
                        with open(c0_00, "r", encoding="utf-8") as f:
                            c0c = f.read()
                        if "l" + chr(0x27) + "bb one" in c0c:
                            if os.path.isfile(c1_00):
                                with open(c1_00, "r", encoding="utf-8") as f:
                                    c1c = f.read()
                                c1_lines = c1c.splitlines()
                                if len(c1_lines) >= 3 and c1_lines[2] == "it" + u2019 + "s fine":
                                    ok1 = True
        print("PASS" if ok1 else "FAIL", "test1: run exit", exit1, "expected 0, 2 records, fidelite 1/0")

        # Tests 2-4: report
        report_args = [sys.executable, script, "report", "--result", result_path, "--texts", texts_dir]
        proc2 = subprocess.run(report_args, capture_output=True, text=True)
        exit2 = proc2.returncode
        rep_ok = False
        rpt = {}
        if exit2 == 0:
            try:
                rpt = json.loads(proc2.stdout)
                rep_ok = True
            except json.JSONDecodeError:
                pass

        # Test 2
        t2 = False
        if rep_ok:
            if (rpt.get("runs") == 2 and rpt.get("errors") == 0
                    and rpt.get("structure_changed") == 0
                    and rpt.get("lines_total") == 6):
                c0 = rpt.get("C0", {})
                if (c0.get("exact") == 4 and c0.get("typo_only") == 2
                        and c0.get("other") == 0 and c0.get("damaged_pct") == 33.33):
                    t2 = True
        print("PASS" if t2 else "FAIL",
              "test2: report runs/errors/struct/lines_total and C0 values")

        # Test 3
        t3 = False
        if rep_ok:
            c1 = rpt.get("C1", {})
            if (c1.get("exact") == 5 and c1.get("typo_only") == 1
                    and c1.get("other") == 0 and c1.get("damaged_pct") == 16.67):
                t3 = True
        print("PASS" if t3 else "FAIL", "test3: C1 values exact=5 typo_only=1 damaged_pct=16.67")

        # Test 4
        t4 = False
        if rep_ok:
            if (rpt.get("background_touched") == 0
                    and rpt.get("good_lines_damaged") == 0
                    and rpt.get("fidelite_changed_runs") == 1
                    and rpt.get("fidelite_errors") == 0):
                t4 = True
        print("PASS" if t4 else "FAIL", "test4: background/good_lines/fidelite counters")

        # Test 5: error codes
        t5a = False
        proc5a = subprocess.run(
            [sys.executable, script, "run", "--texts", texts_dir, "--reps", "1",
             "--bin", bin_dir, "--models", models_path, "--fidelite", fid_path],
            capture_output=True, text=True,
        )
        if proc5a.returncode == 2:
            t5a = True

        t5b = False
        proc5b = subprocess.run(
            [sys.executable, script, "report", "--result", "/nonexistent_path.json", "--texts", texts_dir],
            capture_output=True, text=True,
        )
        if proc5b.returncode == 2:
            t5b = True

        t5 = t5a and t5b
        print("PASS" if t5 else "FAIL", "test5: missing --out exits 2, missing file exits 2")

        all_pass = ok1 and t2 and t3 and t4 and t5
        sys.exit(0 if all_pass else 1)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if "--autotest" in sys.argv:
        run_autotest()
        return

    parser = argparse.ArgumentParser(prog="run_b4.py")
    sub = parser.add_subparsers(dest="command")

    p_run = sub.add_parser("run")
    p_run.add_argument("--texts", required=True)
    p_run.add_argument("--reps", type=int, required=True)
    p_run.add_argument("--bin", required=True)
    p_run.add_argument("--models", required=True)
    p_run.add_argument("--fidelite", required=True)
    p_run.add_argument("--out", required=True)
    p_run.add_argument("--effort", default="medium")
    p_run.add_argument("--write-flag", default="--write")

    p_report = sub.add_parser("report")
    p_report.add_argument("--result", required=True)
    p_report.add_argument("--texts", required=True)

    args = parser.parse_args()

    if args.command is None:
        parser.print_usage(sys.stderr)
        sys.exit(2)

    if args.command == "run":
        cmd_run(args)
    elif args.command == "report":
        cmd_report(args)


if __name__ == "__main__":
    main()
