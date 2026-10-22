"""bench_report.py - reads the bench results file and prints, per condition, the runs, the solved count, the cost and the token totals, as lines or as a Markdown report."""

import os
import sys
import json
import statistics
import subprocess
import tempfile
import shutil

USAGE = "usage: bench_report.py RESULTS_JSONL [--out REPORT_MD] | --notice | --autotest"

NOTICE = (
    "NAME      bench_report.py - reads the bench results file and prints, per condition, the runs, the solved count, the cost and the token totals, as lines or as a Markdown report.\n"
    "READS     the results JSONL file named on the command line: one JSON object per bench execution, as written by bench_run.py.\n"
    "WRITES    only the Markdown report given by --out, folders created as needed; without --out it writes nothing on disk.\n"
    "EXAMPLE   python3 bench_report.py results.jsonl --out reports/bench.md\n"
    "PITFALLS  2026-10-09 a null cost_usd is counted as an unpriced run, never as a zero: a silent zero makes an unpriced condition look cheap.\n"
    "          2026-10-09 conditions and tasks keep their order of first appearance in the file: a report that reorders them cannot be compared run to run.\n"
)


def _is_number(value):
    """Return True when value is a real number (bools are not)."""
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _number_or_zero(value):
    """Return value when it is a number, else 0: a null token count counts as 0."""
    return value if _is_number(value) else 0


def _name_or_empty(value):
    """Return value when it is a string, else the empty string."""
    return value if isinstance(value, str) else ""


def read_results(text):
    """Return (records, unreadable): the JSON objects of the text, and the count of lines that are neither empty nor a JSON object."""
    records = []
    unreadable = 0
    for line in text.splitlines():
        if line.strip() == "":
            continue
        try:
            item = json.loads(line)
        except ValueError:
            unreadable += 1
            continue
        if not isinstance(item, dict):
            unreadable += 1
            continue
        records.append(item)
    return records, unreadable


def summarize(records):
    """Return one dict per condition, in order of first appearance, with the keys name, runs, solved, success, cost, per_solved, median_seconds, input, output, delegated, unpriced."""
    order = []
    stats = {}
    for record in records:
        name = _name_or_empty(record.get("condition"))
        if name not in stats:
            order.append(name)
            stats[name] = {
                "runs": 0, "solved": 0, "cost": 0.0, "unpriced": 0,
                "seconds": [], "input": 0, "output": 0, "delegated": 0,
            }
        s = stats[name]
        s["runs"] += 1
        if record.get("solved") is True:
            s["solved"] += 1
        cost = record.get("cost_usd")
        if _is_number(cost):
            s["cost"] += cost
        else:
            s["unpriced"] += 1
        seconds = record.get("seconds")
        if _is_number(seconds):
            s["seconds"].append(seconds)
        s["input"] += (_number_or_zero(record.get("input_tokens"))
                       + _number_or_zero(record.get("cache_creation_tokens"))
                       + _number_or_zero(record.get("cache_read_tokens")))
        s["output"] += _number_or_zero(record.get("output_tokens"))
        s["delegated"] += _number_or_zero(record.get("delegated_tokens_out"))
    summaries = []
    for name in order:
        s = stats[name]
        runs = s["runs"]
        solved = s["solved"]
        summaries.append({
            "name": name,
            "runs": runs,
            "solved": solved,
            "success": round(100 * solved / runs),
            "cost": s["cost"],
            "per_solved": (s["cost"] / solved) if solved > 0 else "n/a",
            "median_seconds": statistics.median(s["seconds"]) if s["seconds"] else "n/a",
            "input": s["input"],
            "output": s["output"],
            "delegated": s["delegated"],
            "unpriced": s["unpriced"],
        })
    return summaries


def _condition_line(summary):
    """Return the CONDITION line for one condition summary."""
    per_solved = "n/a" if summary["per_solved"] == "n/a" else "%.6f" % summary["per_solved"]
    return ("CONDITION %s runs=%d solved=%d cost=%.6f per_solved=%s unpriced=%d"
            % (summary["name"], summary["runs"], summary["solved"],
               summary["cost"], per_solved, summary["unpriced"]))


def _markdown(results_path, records, unreadable, summaries):
    """Return the full Markdown report text for the results."""
    names = [s["name"] for s in summaries]
    lines = []
    lines.append("# Bench results")
    lines.append("")
    lines.append("Source: %s, %d runs, %d unreadable lines"
                 % (os.path.basename(results_path), len(records), unreadable))
    lines.append("")
    lines.append("| condition | runs | solved | success | cost USD | cost per solved task USD "
                 "| median seconds | orchestrator input tokens | orchestrator output tokens "
                 "| delegated output tokens | unpriced runs |")
    lines.append("|" + "---|" * 11)
    for s in summaries:
        per_solved = "n/a" if s["per_solved"] == "n/a" else "%.6f" % s["per_solved"]
        median_seconds = "n/a" if s["median_seconds"] == "n/a" else "%.1f" % s["median_seconds"]
        lines.append("| %s | %d | %d | %d%% | %.6f | %s | %s | %d | %d | %d | %d |"
                     % (s["name"], s["runs"], s["solved"], s["success"], s["cost"],
                        per_solved, median_seconds, s["input"], s["output"],
                        s["delegated"], s["unpriced"]))
    lines.append("")
    lines.append("## Per task")
    lines.append("")
    task_order = []
    task_cells = {}
    for record in records:
        task = _name_or_empty(record.get("task"))
        condition = _name_or_empty(record.get("condition"))
        if task not in task_cells:
            task_order.append(task)
            task_cells[task] = {}
        cell = task_cells[task].setdefault(condition, [0, 0])
        cell[0] += 1
        if record.get("solved") is True:
            cell[1] += 1
    lines.append("| task | " + " | ".join(names) + " |")
    lines.append("|" + "---|" * (len(names) + 1))
    for task in task_order:
        cells = []
        for name in names:
            cell = task_cells[task].get(name)
            cells.append("%d/%d" % (cell[1], cell[0]) if cell is not None else "-")
        lines.append("| %s | %s |" % (task, " | ".join(cells)))
    return "\n".join(lines) + "\n"


def _parse_args(argv):
    """Return (results_path, out_path) for the positional file and the optional --out VALUE, or None when the args are invalid."""
    results_path = None
    out_path = None
    i = 0
    while i < len(argv):
        token = argv[i]
        if token == "--out":
            if i + 1 >= len(argv):
                return None
            out_path = argv[i + 1]
            i += 2
        elif token.startswith("--"):
            return None
        elif results_path is not None:
            return None
        else:
            results_path = token
            i += 1
    if results_path is None:
        return None
    return results_path, out_path


def _run(args):
    return subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        stdin=subprocess.DEVNULL, capture_output=True, text=True,
    )


def _autotest():
    tmp = tempfile.mkdtemp(prefix="bench_report_autotest_")
    lines = []
    failures = 0

    def record(n, ok, expected, got):
        nonlocal failures
        if ok:
            lines.append("PASS %d: %s" % (n, expected))
        else:
            failures += 1
            lines.append("FAIL %d: expected %s, got %s" % (n, expected, got))

    fixture = (
        '{"task": "t01", "condition": "alone", "solved": true, "seconds": 10, "cost_usd": 0.01, '
        '"input_tokens": 100, "cache_creation_tokens": 20, "cache_read_tokens": 300, '
        '"output_tokens": 10, "delegated_tokens_out": 0}\n'
        '{"task": "t02", "condition": "alone", "solved": false, "seconds": 20, "cost_usd": 0.02, '
        '"input_tokens": 200, "cache_creation_tokens": null, "cache_read_tokens": 0, '
        '"output_tokens": 30, "delegated_tokens_out": 0}\n'
        "this line is not json\n"
        '{"task": "t01", "condition": "frugal", "solved": true, "seconds": 30, "cost_usd": 0.003, '
        '"input_tokens": 50, "cache_creation_tokens": 0, "cache_read_tokens": 0, '
        '"output_tokens": 5, "delegated_tokens_out": 500}\n'
        '{"task": "t01", "condition": "frugal", "solved": true, "seconds": 40, "cost_usd": null, '
        '"input_tokens": null, "cache_creation_tokens": null, "cache_read_tokens": null, '
        '"output_tokens": null, "delegated_tokens_out": 100}\n'
    )
    results_path = os.path.join(tmp, "results.jsonl")
    with open(results_path, "w", encoding="utf-8") as f:
        f.write(fixture)

    expected_lines = [
        "CONDITION alone runs=2 solved=1 cost=0.030000 per_solved=0.030000 unpriced=0",
        "CONDITION frugal runs=2 solved=2 cost=0.003000 per_solved=0.001500 unpriced=1",
    ]
    expected_md = [
        "Source: results.jsonl, 4 runs, 1 unreadable lines",
        "| condition | runs | solved | success | cost USD | cost per solved task USD "
        "| median seconds | orchestrator input tokens | orchestrator output tokens "
        "| delegated output tokens | unpriced runs |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
        "| alone | 2 | 1 | 50% | 0.030000 | 0.030000 | 15.0 | 620 | 40 | 0 | 0 |",
        "| frugal | 2 | 2 | 100% | 0.003000 | 0.001500 | 35.0 | 50 | 5 | 600 | 1 |",
        "| task | alone | frugal |",
        "|---|---|---|",
        "| t01 | 1/1 | 2/2 |",
        "| t02 | 0/1 | - |",
    ]

    # Test 1: without --out, rc=0 and exactly the two CONDITION lines.
    r = _run([results_path])
    ok = r.returncode == 0 and r.stdout.splitlines() == expected_lines
    record(1, ok, "rc=0 and the two CONDITION lines",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout))

    # Test 2: with --out in a new folder, rc=0, WROTE, and the Markdown holds every expected line.
    report_path = os.path.join(tmp, "new", "deep", "r.md")
    r = _run([results_path, "--out", report_path])
    md_ok = False
    if os.path.isfile(report_path):
        with open(report_path, "r", encoding="utf-8") as f:
            md = f.read()
        md_lines = md.splitlines()
        md_ok = (md_lines[0] == "# Bench results" and "## Per task" in md_lines
                 and all(line in md_lines for line in expected_md))
    ok = (r.returncode == 0 and md_ok
          and "WROTE " + report_path in r.stdout.splitlines())
    record(2, ok, "rc=0, WROTE and a Markdown holding every expected line",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout)
           + " md_ok=" + str(md_ok))

    # Test 3: an absent results file -> NO RESULTS, rc=1, no Markdown written.
    absent_path = os.path.join(tmp, "no_such.jsonl")
    absent_report = os.path.join(tmp, "absent_report.md")
    r = _run([absent_path, "--out", absent_report])
    ok = (r.returncode == 1 and r.stdout.strip() == "NO RESULTS " + absent_path
          and not os.path.exists(absent_report))
    record(3, ok, "rc=1 NO RESULTS " + absent_path + " and no report file",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
           + " created=" + str(os.path.exists(absent_report)))

    # Test 4: a file with no readable line -> NO RESULTS, rc=1.
    empty_path = os.path.join(tmp, "empty.jsonl")
    with open(empty_path, "w", encoding="utf-8") as f:
        f.write("\nnot json at all\n42\n")
    r = _run([empty_path])
    ok = r.returncode == 1 and r.stdout.strip() == "NO RESULTS " + empty_path
    record(4, ok, "rc=1 NO RESULTS on a file with no readable line",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

    # Test 5: --out without a value -> USAGE, rc=2.
    r = _run([results_path, "--out"])
    ok = r.returncode == 2 and r.stdout.strip().startswith("usage: bench_report.py")
    record(5, ok, "rc=2 USAGE for --out without a value",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()[:40]))

    # Test 6: an unknown option -> USAGE, rc=2.
    r = _run([results_path, "--bogus"])
    ok = r.returncode == 2 and r.stdout.strip().startswith("usage: bench_report.py")
    record(6, ok, "rc=2 USAGE for an unknown option",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()[:40]))

    # Test 7: no file at all -> USAGE, rc=2.
    r = _run([])
    ok = r.returncode == 2 and r.stdout.strip().startswith("usage: bench_report.py")
    record(7, ok, "rc=2 USAGE with no file",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()[:40]))

    # Test 8: --notice -> rc=0 with the five sections.
    r = _run(["--notice"])
    ok = (r.returncode == 0 and r.stdout.startswith("NAME      bench_report.py")
          and all(section in r.stdout for section in
                  ("READS", "WRITES", "EXAMPLE", "PITFALLS")))
    record(8, ok, "rc=0 --notice with the five sections",
           "rc=" + str(r.returncode) + " out=" + repr(r.stdout[:40]))

    shutil.rmtree(tmp)
    for line in lines:
        sys.stdout.write(line + "\n")
    return 1 if failures else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(argv) == 1 and argv[0] == "--autotest":
        return _autotest()
    parsed = _parse_args(argv)
    if parsed is None:
        sys.stdout.write(USAGE + "\n")
        return 2
    results_path, out_path = parsed
    try:
        with open(results_path, "r", encoding="utf-8") as f:
            text = f.read()
    except OSError:
        sys.stdout.write("NO RESULTS " + results_path + "\n")
        return 1
    records, unreadable = read_results(text)
    if not records:
        sys.stdout.write("NO RESULTS " + results_path + "\n")
        return 1
    summaries = summarize(records)
    for summary in summaries:
        sys.stdout.write(_condition_line(summary) + "\n")
    if out_path is not None:
        folder = os.path.dirname(out_path)
        if folder:
            os.makedirs(folder, exist_ok=True)
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(_markdown(results_path, records, unreadable, summaries))
        sys.stdout.write("WROTE " + out_path + "\n")
    return 0


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bench_report", sys.argv[1:])
