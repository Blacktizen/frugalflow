import sys
import subprocess
from datetime import datetime, timedelta


def fmt(number):
    """Format an integer with space thousand separators."""
    return format(number, ",").replace(",", " ")


def window(msgs):
    """Return the total context tokens from the last message usage dict."""
    if not msgs:
        return 0
    usage = msgs[-1].get("usage", {})
    total = 0
    for key in ("input_tokens", "cache_read_input_tokens", "cache_creation_input_tokens"):
        value = usage.get(key)
        if value is not None:
            total += value
    return total


def local_time(stamp, offset_minutes):
    """Convert a UTC ISO-8601 stamp to a local wall-clock string."""
    if not stamp:
        return ""
    try:
        parsed = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
        result = parsed + timedelta(minutes=offset_minutes)
        return result.strftime("%Y-%m-%dT%H:%M:%S")
    except (ValueError, TypeError):
        return ""


def parse_entry(entry):
    """Normalize a delegation log entry; return None if no timestamp is found."""
    if "horodatage" in entry:
        time_value = entry.get("horodatage")
        model_value = entry.get("modele")  # lang-ok: keys of the old delegation log
        if model_value is None:
            model_value = "unknown"
        tokens_in = entry.get("jetons_envoyes")  # lang-ok
        tokens_out = entry.get("jetons_recus")  # lang-ok
        is_ok = entry.get("statut") == "succes"
    elif "time" in entry:
        time_value = entry.get("time")
        model_value = entry.get("model_answered")
        if model_value is None:
            model_value = entry.get("model_asked")
        if model_value is None:
            model_value = "unknown"
        tokens_in = entry.get("tokens_in")
        tokens_out = entry.get("tokens_out")
        is_ok = entry.get("status") == "success"
    else:
        return None

    if time_value is None:
        return None

    if tokens_in is None:
        tokens_in = 0
    if tokens_out is None:
        tokens_out = 0

    return {
        "time": str(time_value)[:19],
        "model": model_value,
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "ok": is_ok,
    }


def delegated(entries, start, end):
    """Aggregate delegation entries whose time falls within [start, end]."""
    result = {
        "calls": 0,
        "ok": 0,
        "tokens_in": 0,
        "tokens_out": 0,
        "by_model": {},
    }
    for entry in entries:
        parsed = parse_entry(entry)
        if parsed is None:
            continue
        if not (start <= parsed["time"] <= end):
            continue
        result["calls"] += 1
        if parsed["ok"]:
            result["ok"] += 1
        result["tokens_in"] += parsed["tokens_in"]
        result["tokens_out"] += parsed["tokens_out"]
        model_key = parsed["model"]
        result["by_model"][model_key] = result["by_model"].get(model_key, 0) + 1
    return result


def report_lines(window_now, window_limit, written, reread, turns, deleg):
    """Build the three receipt lines as a list of strings."""
    if window_limit == 0:
        pct = 0.0
    else:
        pct = round(100 * window_now / window_limit, 1)
    line1 = "WINDOW " + fmt(window_now) + " of " + fmt(window_limit) + " (" + str(pct) + " %)"

    line2 = ("CLAUDE written " + fmt(written) + " | context reread "
             + fmt(reread) + " over " + str(turns) + " turns")

    models_str = ""
    for model_name in sorted(deleg["by_model"].keys()):
        models_str += " | " + model_name + " " + str(deleg["by_model"][model_name])

    denom = deleg["tokens_out"] + written
    if denom == 0:
        share = 0.0
    else:
        share = round(100 * deleg["tokens_out"] / denom, 1)

    line3 = ("DELEGATED " + str(deleg["calls"]) + " calls (" + str(deleg["ok"]) + " ok) "
             "| sent " + fmt(deleg["tokens_in"]) + " | received " + fmt(deleg["tokens_out"])
             + models_str + " | delegated share of written tokens " + str(share) + " %")

    return [line1, line2, line3]


NOTICE = (
    "NAME      share_rules.py - computes a session's current context window and the share of the work delegated during it, for the token receipt.\n"
    "READS     nothing: pure module; it gets the transcript messages, the delegation log entries and the session span already read.\n"
    "WRITES    nothing: report_lines() returns the WINDOW, CLAUDE and DELEGATED lines; exit 2 on an unknown option.\n"
    "EXAMPLE   python3 share_rules.py --autotest\n"
    "PITFALLS  2026-09-26 the receipt showed 71 181 tokens while the window held 216 000: it printed only what the assistant wrote, never the window nor the delegated part.\n"
    "          Transcript times are UTC, delegation logs are local time: compare only after local_time().\n"
)

USAGE = "usage: share_rules.py [--notice | --autotest]\n"


def autotest():
    """Run the five acceptance tests; return 0 on success, 1 on failure."""
    import os

    msgs = [
        {"usage": {"input_tokens": 5, "cache_read_input_tokens": 1000, "cache_creation_input_tokens": 20}},
        {"usage": {"input_tokens": 2, "cache_read_input_tokens": 215000, "cache_creation_input_tokens": 998}},
    ]
    entries = [
        {"horodatage": "2026-09-26T19:38:13", "modele": "qwen", "jetons_envoyes": 26503, "jetons_recus": 4067, "statut": "succes"},  # lang-ok
        {"time": "2026-09-26T19:10:00", "model_answered": "qwen3.8-27b", "tokens_in": 1000, "tokens_out": 500, "status": "failure"},
        {"horodatage": "2026-09-26T08:00:00", "modele": "qwen", "jetons_envoyes": 999, "jetons_recus": 999, "statut": "succes"},  # lang-ok
        {"modele": "qwen", "jetons_envoyes": 7},  # lang-ok
    ]
    deleg_expected = {"calls": 2, "ok": 1, "tokens_in": 27503, "tokens_out": 4567, "by_model": {"qwen": 1, "qwen3.8-27b": 1}}

    all_passed = True

    # Test 1: window
    expected1 = (216000, 0)
    got1 = (window(msgs), window([]))
    if got1 == expected1:
        print("PASS test1 window: expected=" + str(expected1) + " got=" + str(got1))
    else:
        print("FAIL test1 window: expected=" + str(expected1) + " got=" + str(got1))
        all_passed = False

    # Test 2: local_time
    expected2 = ("2026-09-26T19:38:13", "", "")
    got2 = (local_time("2026-09-26T17:38:13.512Z", 120), local_time("", 120), local_time("bad", 120))
    if got2 == expected2:
        print("PASS test2 local_time: expected=" + str(expected2) + " got=" + str(got2))
    else:
        print("FAIL test2 local_time: expected=" + str(expected2) + " got=" + str(got2))
        all_passed = False

    # Test 3: parse_entry
    expected3 = {
        "entry0": {"time": "2026-09-26T19:38:13", "model": "qwen", "tokens_in": 26503, "tokens_out": 4067, "ok": True},
        "entry1_ok": False,
        "entry1_model": "qwen3.8-27b",
        "entry3": None,
    }
    got3 = {
        "entry0": parse_entry(entries[0]),
        "entry1_ok": parse_entry(entries[1])["ok"],
        "entry1_model": parse_entry(entries[1])["model"],
        "entry3": parse_entry(entries[3]),
    }
    if got3 == expected3:
        print("PASS test3 parse_entry: expected=" + str(expected3) + " got=" + str(got3))
    else:
        print("FAIL test3 parse_entry: expected=" + str(expected3) + " got=" + str(got3))
        all_passed = False

    # Test 4: delegated
    expected4 = deleg_expected
    got4 = delegated(entries, "2026-09-26T19:00:00", "2026-09-26T20:00:00")
    if got4 == expected4:
        print("PASS test4 delegated: expected=" + str(expected4) + " got=" + str(got4))
    else:
        print("FAIL test4 delegated: expected=" + str(expected4) + " got=" + str(got4))
        all_passed = False

    # Test 5: report_lines + subprocess
    expected5_lines = [
        "WINDOW 216 000 of 300 000 (72.0 %)",
        "CLAUDE written 71 181 | context reread 16 007 811 over 104 turns",
        "DELEGATED 2 calls (1 ok) | sent 27 503 | received 4 567 | qwen 1 | qwen3.8-27b 1 | delegated share of written tokens 6.0 %",
    ]
    got5_lines = report_lines(216000, 300000, 71181, 16007811, 104, deleg_expected)

    subprocess_ok = True
    proc_notice = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True,
    )
    if proc_notice.returncode != 0 or not proc_notice.stdout.startswith("NAME      share_rules.py"):
        subprocess_ok = False

    proc_bogus = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--bogus"],
        capture_output=True, text=True,
    )
    if proc_bogus.returncode != 2 or proc_bogus.stdout != USAGE:
        subprocess_ok = False

    if got5_lines == expected5_lines and subprocess_ok:
        print("PASS test5 report_lines+subprocess: expected=" + str(expected5_lines) + " got=" + str(got5_lines))
    else:
        print("FAIL test5 report_lines+subprocess: expected=" + str(expected5_lines) + " got=" + str(got5_lines) + " subprocess_ok=" + str(subprocess_ok))
        all_passed = False

    return 0 if all_passed else 1


def main():
    if len(sys.argv) != 2:
        sys.stdout.write(USAGE)
        sys.exit(2)
    arg = sys.argv[1]
    if arg == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif arg == "--autotest":
        sys.exit(autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "share_rules", sys.argv[1:])
