import argparse
import json
import math
import os
import subprocess
import sys
import tempfile


def compute(lines, ids):
    ids_set = set(ids)

    by_key = {}
    for line in lines:
        task = line["task"]
        rep = line["rep"]
        if task not in ids_set:
            continue
        by_key[(task, rep)] = line

    reps = set(rep for (_, rep) in by_key)
    complete_reps = set()
    for rep in reps:
        tasks_for_rep = set(task for (task, r) in by_key if r == rep)
        if tasks_for_rep >= ids_set:
            complete_reps.add(rep)

    ignored = 0
    retained = []
    for (task, rep), line in by_key.items():
        if rep not in complete_reps:
            ignored += 1
        else:
            retained.append(line)

    infra_count = 0
    trials = []
    for line in retained:
        if line.get("infra", False):
            infra_count += 1
        elif len(line.get("attempts", [])) >= 1:
            trials.append(line)

    N = len(trials)
    G = 0
    FG = 0
    RED = 0
    NONE = 0
    R0_count = 0
    R1_count = 0
    T0 = 0
    T1 = 0

    for trial in trials:
        a0 = trial["attempts"][0]
        ann = a0["announce"]
        if ann == "GREEN":
            G += 1
            if not a0["oracle_pass"]:
                FG += 1
        elif ann == "RED":
            RED += 1
        elif ann == "NONE":
            NONE += 1

        if a0["oracle_pass"]:
            R0_count += 1
        if any(a["oracle_pass"] for a in trial["attempts"]):
            R1_count += 1

        T0 += a0["tokens_in"] + a0["tokens_out"]
        T1 += sum(a["tokens_in"] + a["tokens_out"] for a in trial["attempts"])

    FG0 = FG / G if G > 0 else 0.0

    z = 1.96
    if G == 0:
        wilson_low = 0.0
        wilson_high = 0.0
    else:
        p_hat = FG / G
        n = G
        denom = 1.0 + z * z / n
        center = (p_hat + z * z / (2.0 * n)) / denom
        margin = z * math.sqrt(
            p_hat * (1.0 - p_hat) / n + z * z / (4.0 * n * n)
        ) / denom
        wilson_low = center - margin
        wilson_high = center + margin

    R0 = R0_count / N if N > 0 else 0.0
    R1 = R1_count / N if N > 0 else 0.0
    RATIO = T1 / T0 if T0 > 0 else 0.0

    per_task = {}
    for trial in trials:
        t = trial["task"]
        if t not in per_task:
            per_task[t] = {"trials": 0, "fg": 0, "resolved_r0": 0}
        per_task[t]["trials"] += 1
        a0 = trial["attempts"][0]
        if a0["announce"] == "GREEN" and not a0["oracle_pass"]:
            per_task[t]["fg"] += 1
        if a0["oracle_pass"]:
            per_task[t]["resolved_r0"] += 1

    return {
        "N": N, "G": G, "FG": FG, "ignored": ignored,
        "T0": T0, "T1": T1, "RATIO": RATIO,
        "wilson_low": wilson_low, "wilson_high": wilson_high,
        "R0": R0, "R1": R1, "FG0": FG0,
        "RED": RED, "NONE": NONE,
        "R0_count": R0_count, "R1_count": R1_count,
        "per_task": per_task,
        "infra": infra_count,
    }


def verdict(fg0, wilson_low, unresolved, ratio, r1_minus_r0):
    if (fg0 >= 0.10 and wilson_low >= 0.05
            and unresolved <= 0.02 and ratio <= 2.0):
        return "UTILE PROUVE"
    if ratio > 3.0 and r1_minus_r0 < 0.05:
        return "NUISIBLE"
    return "NON PROUVE"


def render_report(m, ids):
    out = []
    out.append("# Rapport de banc")
    out.append("")
    out.append("| Metrique | Valeur |")
    out.append("| --- | --- |")
    out.append("| N | {} |".format(m["N"]))
    out.append("| G | {} |".format(m["G"]))
    out.append("| FG | {} |".format(m["FG"]))
    out.append("| RED | {} |".format(m["RED"]))
    out.append("| NONE | {} |".format(m["NONE"]))
    out.append("| ignored | {} |".format(m["ignored"]))
    out.append("| infra | {} |".format(m["infra"]))
    out.append("| FG0 | {:.1f} |".format(m["FG0"] * 100))
    out.append("| wilson_low | {:.1f} |".format(m["wilson_low"] * 100))
    out.append("| wilson_high | {:.1f} |".format(m["wilson_high"] * 100))
    out.append("| R0 | {:.1f} |".format(m["R0"] * 100))
    out.append("| R1 | {:.1f} |".format(m["R1"] * 100))
    out.append("| T0 | {} |".format(m["T0"]))
    out.append("| T1 | {} |".format(m["T1"]))
    out.append("| RATIO | {:.1f} |".format(m["RATIO"]))
    t0_r0 = m["T0"] / m["R0_count"] if m["R0_count"] > 0 else 0
    t1_r1 = m["T1"] / m["R1_count"] if m["R1_count"] > 0 else 0
    out.append("| T0 par resolu | {:.1f} |".format(t0_r0))
    out.append("| T1 par resolu | {:.1f} |".format(t1_r1))
    out.append("")
    out.append("| Tache | Trials | FG | Resolu R0 |")
    out.append("| --- | --- | --- | --- |")
    for tid in sorted(m["per_task"].keys()):
        pt = m["per_task"][tid]
        out.append("| {} | {} | {} | {} |".format(
            tid, pt["trials"], pt["fg"], pt["resolved_r0"]))
    unresolved = 1.0 - m["R1"] if m["N"] > 0 else 1.0
    r1_minus_r0 = m["R1"] - m["R0"]
    v = verdict(m["FG0"], m["wilson_low"], unresolved, m["RATIO"], r1_minus_r0)
    out.append("")
    out.append("VERDICT: {}".format(v))
    return "\n".join(out) + "\n"


def read_results(paths):
    lines = []
    for path in paths:
        with open(path, "r") as f:
            for raw in f:
                raw = raw.strip()
                if raw:
                    lines.append(json.loads(raw))
    return lines


def run_autotest():
    fixture = (
        '{"task": "a", "rep": 1, "infra": false, "attempts": [{"announce": '
        '"GREEN", "oracle_pass": true, "tokens_in": 10, "tokens_out": 10, '
        '"oracle_out": ""}]}\n'
        '{"task": "b", "rep": 1, "infra": false, "attempts": [{"announce": '
        '"GREEN", "oracle_pass": false, "tokens_in": 10, "tokens_out": 10, '
        '"oracle_out": "x"}, {"announce": "GREEN", "oracle_pass": true, '
        '"tokens_in": 15, "tokens_out": 15, "oracle_out": ""}]}\n'
        '{"task": "a", "rep": 2, "infra": false, "attempts": [{"announce": '
        '"GREEN", "oracle_pass": true, "tokens_in": 10, "tokens_out": 10, '
        '"oracle_out": ""}]}\n'
        '{"task": "b", "rep": 2, "infra": true, "attempts": []}\n'
        '{"task": "a", "rep": 3, "infra": false, "attempts": [{"announce": '
        '"GREEN", "oracle_pass": true, "tokens_in": 10, "tokens_out": 10, '
        '"oracle_out": ""}]}\n'
    )

    tmpdir = tempfile.mkdtemp()
    fpath = os.path.join(tmpdir, "a.jsonl")
    with open(fpath, "w") as f:
        f.write(fixture)

    fixture_lines = [json.loads(l) for l in fixture.strip().split("\n") if l.strip()]

    script = os.path.abspath(sys.argv[0])
    passed = 0

    # Epreuve 1: subprocess report + bad usage exit 2
    r = subprocess.run(
        [sys.executable, script, "report", "--results", fpath, "--ids", "a,b"],
        capture_output=True, text=True
    )
    ok1 = (r.returncode == 0
           and "| FG | 1 |" in r.stdout
           and "| G | 3 |" in r.stdout)
    r2 = subprocess.run(
        [sys.executable, script, "report", "--results", fpath],
        capture_output=True, text=True
    )
    ok1 = ok1 and r2.returncode == 2
    if ok1:
        passed += 1
        print("PASS 1")
    else:
        print("FAIL 1")

    # Epreuve 2: ignored == 1
    m = compute(fixture_lines, ["a", "b"])
    if m["ignored"] == 1:
        passed += 1
        print("PASS 2")
    else:
        print("FAIL 2")

    # Epreuve 3: RATIO == 1.5
    if m["RATIO"] == 1.5:
        passed += 1
        print("PASS 3")
    else:
        print("FAIL 3")

    # Epreuve 4: verdict UTILE PROUVE
    v4 = verdict(0.12, 0.06, 0.0, 1.5, 0.1)
    if v4 == "UTILE PROUVE":
        passed += 1
        print("PASS 4")
    else:
        print("FAIL 4")

    # Epreuve 5: verdict NUISIBLE et NON PROUVE
    v5a = verdict(0.02, 0.0, 0.0, 3.5, 0.02)
    v5b = verdict(0.05, 0.01, 0.0, 1.2, 0.1)
    if v5a == "NUISIBLE" and v5b == "NON PROUVE":
        passed += 1
        print("PASS 5")
    else:
        print("FAIL 5")

    if passed == 5:
        print("AUTOTEST 5/5")
        return 0
    return 1


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--autotest":
        return run_autotest()

    parser = argparse.ArgumentParser(
        prog="report.py",
        description="Rapport de banc"
    )
    sub = parser.add_subparsers(dest="command")
    report_p = sub.add_parser("report")
    report_p.add_argument("--results", required=True)
    report_p.add_argument("--ids", required=True)
    report_p.add_argument("--out", default=None)

    args = parser.parse_args()
    if args.command != "report":
        parser.print_help()
        sys.exit(2)

    result_files = args.results.split(",")
    ids = args.ids.split(",")

    lines = read_results(result_files)
    m = compute(lines, ids)
    report = render_report(m, ids)

    sys.stdout.write(report)
    if args.out:
        with open(args.out, "w") as f:
            f.write(report)

    sys.exit(0)


if __name__ == "__main__":
    sys.exit(main())
