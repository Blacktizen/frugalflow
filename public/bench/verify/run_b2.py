#!/usr/bin/env python3
"""run_b2.py - evaluate a verification-command judge."""

import argparse
import json
import os
import subprocess
import sys
import tempfile

OUT_PATH = "/w/tool.py"


def execute_on_candidate(cmd, candidate_path):
    """Run cmd via sh -c with FRUGALFLOW_CANDIDATE set to candidate_path."""
    env = os.environ.copy()
    env["FRUGALFLOW_CANDIDATE"] = candidate_path
    cwd = os.path.dirname(os.path.abspath(candidate_path))
    try:
        r = subprocess.run(
            ["sh", "-c", cmd],
            env=env,
            cwd=cwd,
            timeout=30,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return r.returncode
    except subprocess.TimeoutExpired:
        return 124


def load_json(path, label):
    if not os.path.isfile(path):
        print("Error: %s file not found: %s" % (label, path), file=sys.stderr)
        sys.exit(2)
    with open(path, "r") as f:
        return json.load(f)


def extract_command(text):
    """Extract first command from model stdout."""
    lines = text.split("\n")
    filtered = [l for l in lines if not l.startswith("```")]
    for l in filtered:
        stripped = l.strip()
        if stripped:
            while stripped.startswith("`"):
                stripped = stripped[1:]
            while stripped.endswith("`"):
                stripped = stripped[:-1]
            if stripped.startswith("$ "):
                stripped = stripped[2:]
            return stripped
    return None


def build_prompt_p1(desc):
    return (
        "A colleague just wrote the file tool.py. "
        "It is a small command-line tool: running python3 tool.py A B "
        "with two integers prints the result, and it " + desc + ". "
        "Reply with exactly ONE shell command, on one line, "
        "that checks the file is correct. "
        "In the command, write the file as \"$FRUGALFLOW_CANDIDATE\". "
        "Reply with the command only, no explanation."
    )


def build_prompt_p2(desc):
    base = build_prompt_p1(desc)
    base += (
        " The file also has a built-in self-test: "
        "python3 tool.py --autotest runs it and exits non-zero on failure."
    )
    return base


def call_model(bindir, prompt_text, models_file):
    """Call delegate.py with a temporary prompt file. Return stdout text or None."""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
        f.write(prompt_text)
        fpath = f.name
    try:
        r = subprocess.run(
            [
                sys.executable,
                os.path.join(bindir, "delegate.py"),
                "--role", "documents",
                "--file", fpath,
                "--models", models_file,
                "--effort", "medium",
                "--brief-waiver",
                "verification command prompt, not a code brief",
            ],
            timeout=300,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
        )
        if r.returncode != 0:
            return None
        return r.stdout.decode("utf-8")
    except subprocess.TimeoutExpired:
        return None
    finally:
        try:
            os.unlink(fpath)
        except OSError:
            pass


# ─── judge ───────────────────────────────────────────────────────────────────

def do_judge(args):
    commands = load_json(args.commands, "COMMANDS")
    candidates = load_json(args.candidates, "INDEX")

    sys.path.insert(0, args.bin)
    import verify_rules
    judge_fn = verify_rules.judge

    n_candidates = len(candidates)
    results = []

    for c in commands:
        cid = c.get("id")
        cmd = c.get("cmd")
        label = c.get("label")
        note = c.get("note")

        code, _cmd_ret, lines = judge_fn(cmd, OUT_PATH)
        refused = code == 3

        if label == "hollow":
            bad_pass = 0
            for cand in candidates:
                ec = execute_on_candidate(cmd, cand["bad_path"])
                if ec == 0:
                    bad_pass += 1
            vacuous = bad_pass == n_candidates
        else:
            bad_pass = None
            vacuous = None

        results.append({
            "id": cid,
            "label": label,
            "note": note,
            "cmd": cmd,
            "judge_code": code,
            "refused": refused,
            "bad_pass": bad_pass,
            "vacuous": vacuous,
        })

    out_data = {"n_candidates": n_candidates, "commands": results}
    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)
    sys.exit(0)


# ─── report-judge ────────────────────────────────────────────────────────────

def do_report_judge(args):
    data = load_json(args.result, "RESULT")
    commands = data["commands"]
    n_candidates = data["n_candidates"]

    hollow = [c for c in commands if c["label"] == "hollow"]
    real = [c for c in commands if c["label"] == "real"]

    hollow_n = len(hollow)
    hollow_refused = sum(1 for c in hollow if c["refused"])
    real_n = len(real)
    real_refused = sum(1 for c in real if c["refused"])

    hollow_report = {
        "n": hollow_n,
        "refused": hollow_refused,
        "recall_pct": round(hollow_refused / hollow_n * 100, 1) if hollow_n else 0.0,
    }
    real_report = {
        "n": real_n,
        "refused": real_refused,
        "false_refusal_pct": round(real_refused / real_n * 100, 1) if real_n else 0.0,
    }

    hv = [c for c in hollow if c.get("vacuous")]
    hv_n = len(hv)
    hv_refused = sum(1 for c in hv if c["refused"])
    hollow_vacuous_report = {
        "n": hv_n,
        "refused": hv_refused,
        "recall_pct": round(hv_refused / hv_n * 100, 1) if hv_n else 0.0,
    }

    pairs_n = hollow_n * n_candidates
    c0_delivered = sum(c["bad_pass"] for c in hollow)
    c2_delivered = sum(c["bad_pass"] for c in hollow if not c["refused"])
    pairs_report = {
        "n": pairs_n,
        "c0_delivered": c0_delivered,
        "c0_pct": round(c0_delivered / pairs_n * 100, 1) if pairs_n else 0.0,
        "c2_delivered": c2_delivered,
        "c2_pct": round(c2_delivered / pairs_n * 100, 1) if pairs_n else 0.0,
    }

    missed_hollow_ids = [c["id"] for c in hollow if not c["refused"]]
    refused_real_ids = [c["id"] for c in real if c["refused"]]

    output = {
        "hollow": hollow_report,
        "real": real_report,
        "hollow_vacuous": hollow_vacuous_report,
        "pairs": pairs_report,
        "missed_hollow_ids": missed_hollow_ids,
        "refused_real_ids": refused_real_ids,
    }
    print(json.dumps(output, indent=2))
    sys.exit(0)


# ─── propose ─────────────────────────────────────────────────────────────────

def do_propose(args):
    candidates = load_json(args.candidates, "INDEX")
    reps = args.reps
    models_file = args.models
    bindir = args.bin

    sys.path.insert(0, bindir)
    import verify_rules
    judge_fn = verify_rules.judge

    records = []

    for cand in candidates:
        for rep in range(1, reps + 1):
            for style in ("P1", "P2"):
                prompt = build_prompt_p1(cand["desc"]) if style == "P1" else build_prompt_p2(cand["desc"])

                # First model call
                stdout = call_model(bindir, prompt, models_file)
                if stdout is None:
                    records.append({
                        "task": cand["name"],
                        "style": style,
                        "rep": rep,
                        "c0_cmd": None,
                        "c0_exit": None,
                        "c0_delivered": False,
                        "c2_cmd": None,
                        "c2_rounds": None,
                        "c2_refused_final": None,
                        "c2_exit": None,
                        "c2_delivered": False,
                        "error": True,
                    })
                    continue

                c0_cmd = extract_command(stdout)
                bad_path = cand["bad_path"]

                if c0_cmd is None:
                    records.append({
                        "task": cand["name"],
                        "style": style,
                        "rep": rep,
                        "c0_cmd": None,
                        "c0_exit": None,
                        "c0_delivered": False,
                        "c2_cmd": None,
                        "c2_rounds": None,
                        "c2_refused_final": None,
                        "c2_exit": None,
                        "c2_delivered": False,
                        "error": True,
                    })
                    continue

                c0_exit = execute_on_candidate(c0_cmd, bad_path)
                c0_delivered = c0_exit == 0

                # C2 pipeline
                c2_rounds = 0
                c2_refused_final = False
                c2_cmd = None
                c2_exit = None
                c2_delivered = False

                code, accepted_cmd, lines = judge_fn(c0_cmd, OUT_PATH)

                if code != 3:
                    # Accepted on first pass
                    c2_cmd = accepted_cmd
                    c2_exit = execute_on_candidate(c2_cmd, bad_path)
                    c2_delivered = c2_exit == 0
                    c2_rounds = 0
                    c2_refused_final = False
                else:
                    # Refused; try up to 2 retries
                    current_cmd = c0_cmd
                    current_lines = lines
                    resolved = False
                    for attempt in range(1, 3):
                        c2_rounds = attempt
                        retry_prompt = (
                            prompt + "\n\nYour previous command was refused by the checker:\n"
                            + "\n".join(current_lines)
                            + "\nReply again with ONE shell command only."
                        )
                        stdout2 = call_model(bindir, retry_prompt, models_file)
                        if stdout2 is None:
                            c2_refused_final = True
                            break
                        new_cmd = extract_command(stdout2)
                        if new_cmd is None:
                            c2_refused_final = True
                            break
                        code2, accepted_cmd2, lines2 = judge_fn(new_cmd, OUT_PATH)
                        if code2 != 3:
                            c2_cmd = accepted_cmd2
                            c2_exit = execute_on_candidate(c2_cmd, bad_path)
                            c2_delivered = c2_exit == 0
                            c2_refused_final = False
                            resolved = True
                            break
                        else:
                            current_cmd = new_cmd
                            current_lines = lines2
                            if attempt == 2:
                                c2_refused_final = True
                                c2_cmd = None
                                c2_exit = None
                                c2_delivered = False

                records.append({
                    "task": cand["name"],
                    "style": style,
                    "rep": rep,
                    "c0_cmd": c0_cmd,
                    "c0_exit": c0_exit,
                    "c0_delivered": c0_delivered,
                    "c2_cmd": c2_cmd,
                    "c2_rounds": c2_rounds,
                    "c2_refused_final": c2_refused_final,
                    "c2_exit": c2_exit,
                    "c2_delivered": c2_delivered,
                    "error": False,
                })

    out_data = {"records": records}
    with open(args.out, "w") as f:
        json.dump(out_data, f, indent=2)
    sys.exit(0)


# ─── report-propose ──────────────────────────────────────────────────────────

def do_report_propose(args):
    data = load_json(args.result, "PROPOSED")
    records = data["records"]

    output = {}
    for style in ("P1", "P2"):
        styled = [r for r in records if r["style"] == style]
        n = len(styled)
        c0_delivered = sum(1 for r in styled if r.get("c0_delivered") is True)
        c2_delivered = sum(1 for r in styled if r.get("c2_delivered") is True)
        first_refused = sum(
            1 for r in styled
            if (r.get("c2_rounds") is not None and r.get("c2_rounds") > 0)
            or r.get("c2_refused_final") is True
        )
        errors = sum(1 for r in styled if r.get("error") is True)

        output[style] = {
            "n": n,
            "c0_delivered": c0_delivered,
            "c0_pct": round(c0_delivered / n * 100, 1) if n else 0.0,
            "c2_delivered": c2_delivered,
            "c2_pct": round(c2_delivered / n * 100, 1) if n else 0.0,
            "first_refused": first_refused,
            "errors": errors,
        }

    print(json.dumps(output, indent=2))
    sys.exit(0)


# ─── autotest ────────────────────────────────────────────────────────────────

def run_autotest():
    import shutil
    tmpdir = tempfile.mkdtemp()
    bindir = os.path.join(tmpdir, "bin")
    os.makedirs(bindir)

    # Fixtures
    with open(os.path.join(bindir, "verify_rules.py"), "w") as f:
        f.write(
            "def judge(cmd, out, waiver=None):\n"
            "    if \"WEAK\" in cmd:\n"
            "        return (3, cmd, [\"VERIFY WEAK: stub\", \"  To fix: stub\"])\n"
            "    return (0, cmd, [])\n"
        )

    with open(os.path.join(bindir, "delegate.py"), "w") as f:
        f.write(
            "import sys\n"
            "t = open(sys.argv[sys.argv.index(\"--file\") + 1]).read()\n"
            "if \"refused by the checker\" in t or \"self-test\" in t:\n"
            "    print('python3 \"$FRUGALFLOW_CANDIDATE\" --autotest')\n"
            "else:\n"
            "    print(\"`true WEAK`\")\n"
        )

    cand_content = (
        "import sys\n"
        "sys.exit(1 if \"--autotest\" in sys.argv else 0)\n"
    )
    c1_path = os.path.join(tmpdir, "c1.py")
    c2_path = os.path.join(tmpdir, "c2.py")
    with open(c1_path, "w") as f:
        f.write(cand_content)
    with open(c2_path, "w") as f:
        f.write(cand_content)

    index_path = os.path.join(tmpdir, "INDEX.json")
    with open(index_path, "w") as f:
        json.dump([
            {"name": "c1", "good_path": c1_path, "bad_path": c1_path, "desc": "adds"},
            {"name": "c2", "good_path": c2_path, "bad_path": c2_path, "desc": "adds"},
        ], f)

    commands_path = os.path.join(tmpdir, "COMMANDS.json")
    with open(commands_path, "w") as f:
        json.dump([
            {"id": "h1", "cmd": "true WEAK", "label": "hollow", "note": "x"},
            {"id": "h2", "cmd": "true", "label": "hollow", "note": "x"},
            {"id": "r1", "cmd": "python3 \"$FRUGALFLOW_CANDIDATE\" --autotest", "label": "real", "note": "x"},
        ], f)

    models_path = os.path.join(tmpdir, "MODELS.json")
    with open(models_path, "w") as f:
        json.dump({}, f)

    result_path = os.path.join(tmpdir, "RESULT.json")
    proposed_path = os.path.join(tmpdir, "PROPOSED.json")

    script = os.path.abspath(__file__)
    pass_count = 0
    fail_count = 0

    def run(args_list, expect_code):
        r = subprocess.run(
            [sys.executable, script] + args_list,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=120,
        )
        return r.returncode, r.stdout.decode("utf-8")

    def check(test_num, passed, expected, got):
        nonlocal pass_count, fail_count
        status = "PASS" if passed else "FAIL"
        print("%s T%d expected=%s got=%s" % (status, test_num, expected, got))
        if passed:
            pass_count += 1
        else:
            fail_count += 1

    # T1: judge
    code, out = run(
        ["judge", "--commands", commands_path, "--candidates", index_path,
         "--bin", bindir, "--out", result_path], 0)
    ok = code == 0
    if ok:
        data = json.load(open(result_path))
        cmds = {c["id"]: c for c in data["commands"]}
        ok = (len(data["commands"]) == 3
              and cmds["h1"]["refused"] is True and cmds["h1"]["bad_pass"] == 2
              and cmds["h2"]["refused"] is False and cmds["h2"]["bad_pass"] == 2
              and cmds["r1"]["refused"] is False and cmds["r1"]["bad_pass"] is None)
    check(1, ok, "exit0,3cmds,h1 refused bad2,h2 notrefused bad2,r1 notrefused null", code)

    # T2: report-judge
    code, out = run(["report-judge", "--result", result_path], 0)
    ok = code == 0
    if ok:
        rpt = json.loads(out)
        ok = (rpt["hollow"]["n"] == 2 and rpt["hollow"]["refused"] == 1
              and rpt["hollow"]["recall_pct"] == 50.0
              and rpt["real"]["n"] == 1 and rpt["real"]["refused"] == 0
              and rpt["real"]["false_refusal_pct"] == 0.0
              and rpt["pairs"]["n"] == 4 and rpt["pairs"]["c0_delivered"] == 4
              and rpt["pairs"]["c0_pct"] == 100.0
              and rpt["pairs"]["c2_delivered"] == 2 and rpt["pairs"]["c2_pct"] == 50.0
              and rpt["missed_hollow_ids"] == ["h2"])
    check(2, ok, "exit0,hollow50%,real0%,pairs4/100/2/50,missed[h2]", code)

    # T3: propose --reps 2
    code, out = run(
        ["propose", "--candidates", index_path, "--bin", bindir,
         "--models", models_path, "--reps", "2", "--out", proposed_path], 0)
    ok = code == 0
    if ok:
        pdata = json.load(open(proposed_path))
        recs = pdata["records"]
        ok = len(recs) == 8
        if ok:
            p1 = [r for r in recs if r["style"] == "P1"]
            p2 = [r for r in recs if r["style"] == "P2"]
            ok = (all(r["c0_delivered"] is True for r in p1)
                  and all(r["c2_rounds"] == 1 for r in p1)
                  and all(r["c2_delivered"] is False for r in p1)
                  and all(r["c0_delivered"] is False for r in p2)
                  and all(r["c2_rounds"] == 0 for r in p2))
    check(3, ok, "exit0,8recs,P1 delivered+rounds1+notdelivered,P2 notdelivered+rounds0", code)

    # T4: report-propose
    code, out = run(["report-propose", "--result", proposed_path], 0)
    ok = code == 0
    if ok:
        rpt = json.loads(out)
        ok = (rpt["P1"]["n"] == 4 and rpt["P1"]["c0_delivered"] == 4
              and rpt["P1"]["c0_pct"] == 100.0
              and rpt["P1"]["c2_delivered"] == 0 and rpt["P1"]["c2_pct"] == 0.0
              and rpt["P1"]["first_refused"] == 4 and rpt["P1"]["errors"] == 0
              and rpt["P2"]["n"] == 4 and rpt["P2"]["c0_delivered"] == 0
              and rpt["P2"]["c0_pct"] == 0.0 and rpt["P2"]["first_refused"] == 0)
    check(4, ok, "exit0,P1 n4 100% c2_0 4refused 0err,P2 n4 0% 0refused", code)

    # T5: error codes
    code, _ = run(
        ["judge", "--commands", commands_path, "--candidates", index_path, "--bin", bindir], 2)
    ok5a = code == 2
    code, _ = run(["report-judge", "--result", os.path.join(tmpdir, "MISSING.json")], 2)
    ok5b = code == 2
    ok = ok5a and ok5b
    check(5, ok, "missing-out->2,missing-file->2", "%d,%d" % (ok5a, ok5b))

    shutil.rmtree(tmpdir, ignore_errors=True)

    if fail_count > 0:
        sys.exit(1)
    sys.exit(0)


# ─── main ────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(prog="run_b2.py", description="Judge evaluation")
    parser.add_argument("--autotest", action="store_true")
    sub = parser.add_subparsers(dest="command")

    p_judge = sub.add_parser("judge")
    p_judge.add_argument("--commands", required=True)
    p_judge.add_argument("--candidates", required=True)
    p_judge.add_argument("--bin", required=True)
    p_judge.add_argument("--out", required=True)

    p_rj = sub.add_parser("report-judge")
    p_rj.add_argument("--result", required=True)

    p_prop = sub.add_parser("propose")
    p_prop.add_argument("--candidates", required=True)
    p_prop.add_argument("--bin", required=True)
    p_prop.add_argument("--models", required=True)
    p_prop.add_argument("--reps", type=int, required=True)
    p_prop.add_argument("--out", required=True)

    p_rp = sub.add_parser("report-propose")
    p_rp.add_argument("--result", required=True)

    args = parser.parse_args()

    if args.autotest:
        run_autotest()
        return

    if args.command is None:
        parser.print_usage(sys.stderr)
        sys.exit(2)

    if args.command == "judge":
        do_judge(args)
    elif args.command == "report-judge":
        do_report_judge(args)
    elif args.command == "propose":
        do_propose(args)
    elif args.command == "report-propose":
        do_report_propose(args)
    else:
        parser.print_usage(sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
