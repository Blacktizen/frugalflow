#!/usr/bin/env python3
import sys
import os
import json
import time
import re
import subprocess
import tempfile
import math


def main():
    argv = sys.argv[1:]
    if "--autotest" in argv:
        run_autotest()
        return
    if not argv:
        usage()
        sys.exit(2)
    cmd = argv[0]
    if cmd == "collect":
        do_collect(argv[1:])
    elif cmd == "report":
        do_report(argv[1:])
    else:
        usage()
        sys.exit(2)


def usage():
    sys.stderr.write(
        "usage: run_b1.py collect --corpus DIR --truth FILE --rules FILE "
        "--models FILE --bin DIR --out FILE\n"
        "       run_b1.py report --truth FILE --collected FILE\n"
        "       run_b1.py --autotest\n"
    )


def do_collect(args):
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--corpus", required=True)
    parser.add_argument("--truth", required=True)
    parser.add_argument("--rules", required=True)
    parser.add_argument("--models", required=True)
    parser.add_argument("--bin", required=True)
    parser.add_argument("--out", required=True)
    try:
        ns = parser.parse_args(args)
    except SystemExit:
        usage()
        sys.exit(2)
    corpus = os.path.abspath(ns.corpus)
    truth_path = os.path.abspath(ns.truth)
    rules = os.path.abspath(ns.rules)
    models = os.path.abspath(ns.models)
    bindir = os.path.abspath(ns.bin)
    out_path = os.path.abspath(ns.out)
    if not os.path.isdir(corpus):
        usage()
        sys.exit(2)
    if not os.path.isfile(truth_path):
        usage()
        sys.exit(2)
    if not os.path.isfile(rules):
        usage()
        sys.exit(2)
    if not os.path.isfile(models):
        usage()
        sys.exit(2)
    if not os.path.isdir(bindir):
        usage()
        sys.exit(2)
    with open(truth_path) as f:
        truth = json.load(f)
    corpus_files = set(
        x for x in os.listdir(corpus) if os.path.isfile(os.path.join(corpus, x))
    )
    filenames = sorted([f for f in truth if f in corpus_files])
    collected = {}
    for name in filenames:
        c2_lines, c2_secs = run_c2(bindir, corpus, rules, name)
        c1_lines, c1_status, c1_secs = run_c1(bindir, corpus, models, name)
        collected[name] = {
            "c1": {"lines": c1_lines, "status": c1_status, "secs": c1_secs},
            "c2": {"lines": c2_lines, "secs": c2_secs},
        }
    with open(out_path, "w") as f:
        json.dump(collected, f, indent=2)
    sys.exit(0)


def run_c2(bindir, corpus, rules, name):
    script = os.path.join(bindir, "anon_check.py")
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script, "--rules", rules, "--scan", name],
        cwd=corpus, capture_output=True, text=True,
    )
    secs = time.time() - t0
    lines = []
    for line in result.stdout.split("\n"):
        m = re.match(r"^(.+):(\d+):", line)
        if m:
            lines.append(int(m.group(2)))
    return lines, secs


def run_c1(bindir, corpus, models, name):
    script = os.path.join(bindir, "anon_review.py")
    tmpdir = tempfile.mkdtemp()
    report_path = os.path.join(tmpdir, "report.txt")
    env = os.environ.copy()
    env["FRUGALFLOW_HOME"] = tmpdir
    t0 = time.time()
    result = subprocess.run(
        [sys.executable, script, "--models", models, "--report", report_path, name],
        cwd=corpus, capture_output=True, text=True, env=env,
    )
    secs = time.time() - t0
    lines = []
    has_unread = False
    for line in result.stdout.split("\n"):
        m = re.match(r"^SUSPECT (.+):(\d+)", line)
        if m:
            lines.append(int(m.group(2)))
        if line.startswith("UNREAD"):
            has_unread = True
    if has_unread or result.returncode not in (0, 4):
        status = "unread"
    else:
        status = "ok"
    return lines, status, secs


def do_report(args):
    import argparse
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--truth", required=True)
    parser.add_argument("--collected", required=True)
    try:
        ns = parser.parse_args(args)
    except SystemExit:
        usage()
        sys.exit(2)
    truth_path = os.path.abspath(ns.truth)
    collected_path = os.path.abspath(ns.collected)
    if not os.path.isfile(truth_path):
        usage()
        sys.exit(2)
    if not os.path.isfile(collected_path):
        usage()
        sys.exit(2)
    with open(truth_path) as f:
        truth = json.load(f)
    with open(collected_path) as f:
        collected = json.load(f)
    result = compute_report(truth, collected)
    print(json.dumps(result, indent=2))
    sys.exit(0)


def wilson95(p_hat, n):
    if n == 0:
        return [0.0, 0.0]
    z = 1.96
    z2 = z * z
    center = p_hat + z2 / (2 * n)
    margin = z * math.sqrt(p_hat * (1 - p_hat) / n + z2 / (4 * n * n))
    denom = 1 + z2 / n
    lo = max(0.0, min(1.0, (center - margin) / denom))
    hi = max(0.0, min(1.0, (center + margin) / denom))
    return [round(lo * 100, 1), round(hi * 100, 1)]


def compute_report(truth, collected):
    leak_files = {k: v for k, v in truth.items() if v["leaks"]}
    decoy_files = {k: v for k, v in truth.items() if v.get("decoy")}
    n_leaks = len(leak_files)
    n_decoys = len(decoy_files)

    def all_leak_lines(entry):
        lines = []
        for leak in entry["leaks"]:
            lines.extend(leak["lines"])
        return lines

    def is_detected(name, alerts, status_ok=True):
        if not status_ok:
            return False
        leak_lines = all_leak_lines(truth[name])
        for l in alerts:
            for p in leak_lines:
                if abs(l - p) <= 1:
                    return True
        return False

    def get_alerts(name, cond):
        entry = collected.get(name, {})
        if cond == "c1":
            return (
                entry.get("c1", {}).get("lines", []),
                entry.get("c1", {}).get("status", "ok") == "ok",
            )
        if cond == "c2":
            return entry.get("c2", {}).get("lines", []), True
        return [], True

    def get_secs(name, cond):
        entry = collected.get(name, {})
        if cond == "c1":
            return entry.get("c1", {}).get("secs", 0)
        if cond == "c2":
            return entry.get("c2", {}).get("secs", 0)
        return 0

    def compute_condition(cond):
        detected = 0
        fp = 0
        secs_total = 0.0
        by_type = {}
        hard_det = 0
        hard_tot = 0
        for name in sorted(leak_files.keys()):
            alerts, status_ok = get_alerts(name, cond)
            secs_total += get_secs(name, cond)
            det = is_detected(name, alerts, status_ok)
            if det:
                detected += 1
            t = truth[name]["leaks"][0]["type"]
            if t not in by_type:
                by_type[t] = [0, 0]
            by_type[t][1] += 1
            if det:
                by_type[t][0] += 1
            if truth[name].get("hard"):
                hard_tot += 1
                if det:
                    hard_det += 1
        for name in sorted(decoy_files.keys()):
            alerts, _ = get_alerts(name, cond)
            secs_total += get_secs(name, cond)
            if len(alerts) > 0:
                fp += 1
        delivered = n_leaks - detected
        pct = round(delivered / n_leaks * 100, 1) if n_leaks > 0 else 0.0
        w95 = wilson95(delivered / n_leaks if n_leaks > 0 else 0.0, n_leaks)
        fp_pct = round(fp / n_decoys * 100, 1) if n_decoys > 0 else 0.0
        return {
            "n_leaks": n_leaks,
            "detected": detected,
            "delivered": delivered,
            "delivered_pct": pct,
            "delivered_wilson95": w95,
            "n_decoys": n_decoys,
            "fp": fp,
            "fp_pct": fp_pct,
            "secs": secs_total,
            "by_type": by_type,
            "hard": [hard_det, hard_tot],
        }

    c0_by_type = {}
    for name in sorted(leak_files.keys()):
        t = truth[name]["leaks"][0]["type"]
        if t not in c0_by_type:
            c0_by_type[t] = [0, 0]
        c0_by_type[t][1] += 1
    hard_tot_all = sum(1 for v in leak_files.values() if v.get("hard"))
    c0 = {
        "n_leaks": n_leaks,
        "detected": 0,
        "delivered": n_leaks,
        "delivered_pct": round(100.0, 1) if n_leaks > 0 else 0.0,
        "delivered_wilson95": wilson95(1.0, n_leaks),
        "n_decoys": n_decoys,
        "fp": 0,
        "fp_pct": 0.0,
        "secs": 0,
        "by_type": c0_by_type,
        "hard": [0, hard_tot_all],
    }

    c1 = compute_condition("c1")
    c2 = compute_condition("c2")

    c3_detected = 0
    c3_fp = 0
    c3_secs = 0.0
    c3_by_type = {}
    c3_hard_det = 0
    c3_hard_tot = 0
    for name in sorted(leak_files.keys()):
        a1, s1 = get_alerts(name, "c1")
        a2, _ = get_alerts(name, "c2")
        c3_secs += get_secs(name, "c1") + get_secs(name, "c2")
        det1 = is_detected(name, a1, s1)
        det2 = is_detected(name, a2, True)
        det = det1 or det2
        if det:
            c3_detected += 1
        t = truth[name]["leaks"][0]["type"]
        if t not in c3_by_type:
            c3_by_type[t] = [0, 0]
        c3_by_type[t][1] += 1
        if det:
            c3_by_type[t][0] += 1
        if truth[name].get("hard"):
            c3_hard_tot += 1
            if det:
                c3_hard_det += 1
    for name in sorted(decoy_files.keys()):
        a1, _ = get_alerts(name, "c1")
        a2, _ = get_alerts(name, "c2")
        c3_secs += get_secs(name, "c1") + get_secs(name, "c2")
        if len(a1) > 0 or len(a2) > 0:
            c3_fp += 1
    c3_del = n_leaks - c3_detected
    c3 = {
        "n_leaks": n_leaks,
        "detected": c3_detected,
        "delivered": c3_del,
        "delivered_pct": round(c3_del / n_leaks * 100, 1) if n_leaks > 0 else 0.0,
        "delivered_wilson95": wilson95(c3_del / n_leaks if n_leaks > 0 else 0.0, n_leaks),
        "n_decoys": n_decoys,
        "fp": c3_fp,
        "fp_pct": round(c3_fp / n_decoys * 100, 1) if n_decoys > 0 else 0.0,
        "secs": c3_secs,
        "by_type": c3_by_type,
        "hard": [c3_hard_det, c3_hard_tot],
    }

    return {"C0": c0, "C1": c1, "C2": c2, "C3": c3}


def run_autotest():
    tmpdir = tempfile.mkdtemp()
    bindir = os.path.join(tmpdir, "bin")
    corpus = os.path.join(tmpdir, "corpus")
    os.makedirs(bindir)
    os.makedirs(corpus)

    anon_check_src = (
        "import sys\n"
        "name = sys.argv[sys.argv.index('--scan') + 1]\n"
        "t = open(name).read().split('\\n')\n"
        "hits = [i + 1 for i, x in enumerate(t) if 'LEAK' in x]\n"
        "for h in hits:\n"
        "    print(name + ':' + str(h) + ': anonymizable person')\n"
        "if hits:\n"
        "    print('FOUND')\n"
        "    sys.exit(12)\n"
        "print('CLEAN 1 files')\n"
    )
    with open(os.path.join(bindir, "anon_check.py"), "w") as f:
        f.write(anon_check_src)

    anon_review_src = (
        "import sys\n"
        "name = sys.argv[-1]\n"
        "t = open(name).read().split('\\n')\n"
        "if any('UNREADME' in x for x in t):\n"
        "    print('UNREAD ' + name)\n"
        "    sys.exit(3)\n"
        "hits = [i + 1 for i, x in enumerate(t) if 'LEAKB' in x]\n"
        "for h in hits:\n"
        "    print('SUSPECT ' + name + ':' + str(h) + ' private_name')\n"
        "print('REVIEWED 1')\n"
        "sys.exit(4 if hits else 0)\n"
    )
    with open(os.path.join(bindir, "anon_review.py"), "w") as f:
        f.write(anon_review_src)

    file_contents = {
        "a1.txt": "x\nLEAK secret\nLEAKB y\n",
        "a2.txt": "x\nx\nx\nLEAK z\n",
        "a3.txt": "x\nx\nx\n",
        "a4.txt": "LEAK d\n",
        "a5.txt": "UNREADME LEAK\n",
    }
    for fname, content in file_contents.items():
        with open(os.path.join(corpus, fname), "w") as f:
            f.write(content)

    truth_data = {
        "a1.txt": {
            "leaks": [{"id": "u1", "type": "email", "form": "plain", "lines": [2]}],
            "hard": False,
            "decoy": False,
        },
        "a2.txt": {
            "leaks": [{"id": "u2", "type": "email", "form": "plain", "lines": [4]}],
            "hard": True,
            "decoy": False,
        },
        "a3.txt": {"leaks": [], "hard": False, "decoy": True},
        "a4.txt": {"leaks": [], "hard": False, "decoy": True},
        "a5.txt": {
            "leaks": [{"id": "u3", "type": "api_key", "form": "plain", "lines": [1]}],
            "hard": False,
            "decoy": False,
        },
    }
    with open(os.path.join(tmpdir, "truth.json"), "w") as f:
        json.dump(truth_data, f)

    with open(os.path.join(tmpdir, "rules.json"), "w") as f:
        f.write("{}")
    with open(os.path.join(tmpdir, "models.json"), "w") as f:
        f.write("{}")

    script_path = os.path.abspath(__file__)
    collected_path = os.path.join(tmpdir, "collected.json")

    r_collect = subprocess.run(
        [
            sys.executable, script_path, "collect",
            "--corpus", corpus,
            "--truth", os.path.join(tmpdir, "truth.json"),
            "--rules", "rules.json",
            "--models", "models.json",
            "--bin", bindir,
            "--out", "collected.json",
        ],
        cwd=tmpdir,
        capture_output=True,
        text=True,
    )

    all_pass = True

    def check(test_num, passed, expected, got):
        nonlocal all_pass
        status = "PASS" if passed else "FAIL"
        if not passed:
            all_pass = False
        print(f"{status} test{test_num} expected={expected} got={got}")

    # Test 1
    if r_collect.returncode == 0 and os.path.isfile(collected_path):
        with open(collected_path) as f:
            collected = json.load(f)
        ok1 = (
            len(collected) == 5
            and collected.get("a5.txt", {}).get("c1", {}).get("status") == "unread"
            and collected.get("a1.txt", {}).get("c1", {}).get("lines") == [3]
            and collected.get("a2.txt", {}).get("c2", {}).get("lines") == [4]
        )
        check(1, ok1, "5 entries, a5 c1 unread, a1 c1 [3], a2 c2 [4]",
              f"{len(collected)} entries, a5 status={collected.get('a5.txt',{}).get('c1',{}).get('status')}, a1 c1={collected.get('a1.txt',{}).get('c1',{}).get('lines')}, a2 c2={collected.get('a2.txt',{}).get('c2',{}).get('lines')}")
    else:
        check(1, False, "exit 0 with 5 entries", f"exit {r_collect.returncode}")

    # Run report
    r_report = subprocess.run(
        [
            sys.executable, script_path, "report",
            "--truth", os.path.join(tmpdir, "truth.json"),
            "--collected", collected_path,
        ],
        cwd=tmpdir,
        capture_output=True,
        text=True,
    )
    report = json.loads(r_report.stdout) if r_report.returncode == 0 else {}

    # Test 2: C2
    c2 = report.get("C2", {})
    ok2 = (
        c2.get("detected") == 3
        and c2.get("delivered") == 0
        and c2.get("delivered_pct") == 0.0
        and c2.get("fp") == 1
        and c2.get("n_decoys") == 2
        and c2.get("by_type", {}).get("email") == [2, 2]
        and c2.get("by_type", {}).get("api_key") == [1, 1]
    )
    check(2, ok2,
          "C2 detected=3 delivered=0 delivered_pct=0.0 fp=1 n_decoys=2 by_type={email:[2,2],api_key:[1,1]}",
          f"C2 detected={c2.get('detected')} delivered={c2.get('delivered')} delivered_pct={c2.get('delivered_pct')} fp={c2.get('fp')} n_decoys={c2.get('n_decoys')} by_type={c2.get('by_type')}")

    # Test 3: C1
    c1 = report.get("C1", {})
    ok3 = (
        c1.get("detected") == 1
        and c1.get("delivered") == 2
        and c1.get("fp") == 0
        and c1.get("by_type", {}).get("email") == [1, 2]
        and c1.get("by_type", {}).get("api_key") == [0, 1]
        and c1.get("hard") == [0, 1]
    )
    check(3, ok3,
          "C1 detected=1 delivered=2 fp=0 by_type={email:[1,2],api_key:[0,1]} hard=[0,1]",
          f"C1 detected={c1.get('detected')} delivered={c1.get('delivered')} fp={c1.get('fp')} by_type={c1.get('by_type')} hard={c1.get('hard')}")

    # Test 4: C0 and C3
    c0 = report.get("C0", {})
    c3 = report.get("C3", {})
    ok4 = (
        c0.get("detected") == 0
        and c0.get("delivered") == 3
        and c0.get("delivered_pct") == 100.0
        and c3.get("detected") == 3
        and c3.get("fp") == 1
        and c3.get("hard") == [1, 1]
    )
    check(4, ok4,
          "C0 detected=0 delivered=3 pct=100.0; C3 detected=3 fp=1 hard=[1,1]",
          f"C0 detected={c0.get('detected')} delivered={c0.get('delivered')} pct={c0.get('delivered_pct')}; C3 detected={c3.get('detected')} fp={c3.get('fp')} hard={c3.get('hard')}")

    # Test 5: error exits
    r_err1 = subprocess.run(
        [
            sys.executable, script_path, "report",
            "--truth", os.path.join(tmpdir, "truth.json"),
            "--collected", os.path.join(tmpdir, "nonexistent.json"),
        ],
        cwd=tmpdir, capture_output=True, text=True,
    )
    r_err2 = subprocess.run(
        [
            sys.executable, script_path, "collect",
            "--corpus", corpus,
            "--truth", os.path.join(tmpdir, "truth.json"),
            "--rules", "rules.json",
            "--models", "models.json",
            "--bin", bindir,
        ],
        cwd=tmpdir, capture_output=True, text=True,
    )
    ok5 = r_err1.returncode == 2 and r_err2.returncode == 2
    check(5, ok5,
          "missing --collected -> 2; missing --out -> 2",
          f"--collected absent -> {r_err1.returncode}; --out absent -> {r_err2.returncode}")

    sys.exit(0 if all_pass else 1)


if __name__ == "__main__":
    main()
