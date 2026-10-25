"""model_notes.py - keeps, per model and engine, what the vendor prescribes, what we measured and the pitfalls met."""

import os
import sys
import json
import copy
import re
import datetime
import statistics
import subprocess
import tempfile

USAGE = (
    "usage: model_notes.py check FILE | add-pitfall --file F --model M --engine E "
    "--symptom S --remedy R --proof P [--date YYYY-MM-DD] | show --file F --model M | "
    "merge --file F --from C | measure --file F --log L --model M --engine E [--date YYYY-MM-DD] "
    "| --notice | --autotest"
)

NOTICE = (
    "NAME      model_notes.py - keeps, per model and engine, what the vendor prescribes, what we measured and the pitfalls met.\n"
    "READS     the model notes file given by --file or to check: a JSON settings file kept apart from the code; the delegation log given to measure.\n"
    "WRITES    only the file given to add-pitfall, merge or measure, atomically; check and show write nothing.\n"
    "EXAMPLE   python3 model_notes.py add-pitfall --file notes.json --model m --engine e --symptom s --remedy r --proof p\n"
    "PITFALLS  2026-10-09 an entry without proof is refused: a pitfall nobody can replay is an opinion, not a note.\n"
    "          2026-10-09 a measure is read from the delegation log, never typed by hand: the log is its proof.\n"
)

_DATE_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}\Z")


def _is_date(value):
    if not isinstance(value, str):
        return False
    if _DATE_RE.match(value) is None:
        return False
    try:
        datetime.datetime.strptime(value, "%Y-%m-%d")
        return True
    except ValueError:
        return False


def _is_text(value):
    return isinstance(value, str) and value != ""


def _measured_errors(i, j, item):
    errors = []
    if not isinstance(item, dict):
        item = {}
    if not _is_date(item.get("date")):
        errors.append("models[%d].measured[%d].date must be a date YYYY-MM-DD" % (i, j))
    if not _is_text(item.get("what")):
        errors.append("models[%d].measured[%d].what must be a non-empty string" % (i, j))
    if not _is_text(item.get("value")):
        errors.append("models[%d].measured[%d].value must be a non-empty string" % (i, j))
    if not _is_text(item.get("proof")):
        errors.append("models[%d].measured[%d].proof must be a non-empty string" % (i, j))
    return errors


def _pitfall_errors(i, j, item):
    errors = []
    if not isinstance(item, dict):
        item = {}
    if not _is_date(item.get("date")):
        errors.append("models[%d].pitfalls[%d].date must be a date YYYY-MM-DD" % (i, j))
    if not _is_text(item.get("symptom")):
        errors.append("models[%d].pitfalls[%d].symptom must be a non-empty string" % (i, j))
    if not _is_text(item.get("remedy")):
        errors.append("models[%d].pitfalls[%d].remedy must be a non-empty string" % (i, j))
    if not _is_text(item.get("proof")):
        errors.append("models[%d].pitfalls[%d].proof must be a non-empty string" % (i, j))
    return errors


def validate(doc):
    """Return the list of error strings for the document, empty when it is valid."""
    errors = []
    if not isinstance(doc, dict):
        errors.append("schema_version must be 1")
        return errors
    if doc.get("schema_version") != "1":
        errors.append("schema_version must be 1")
    models = doc.get("models")
    if not isinstance(models, list):
        errors.append("models must be a list")
        return errors
    seen = set()
    for i, entry in enumerate(models):
        if not isinstance(entry, dict):
            errors.append("models[%d] must be an object" % i)
            continue
        model = entry.get("model")
        if not _is_text(model):
            errors.append("models[%d].model must be a non-empty string" % i)
        engine = entry.get("engine")
        if not _is_text(engine):
            errors.append("models[%d].engine must be a non-empty string" % i)
        if _is_text(model) and _is_text(engine):
            pair = (model, engine)
            if pair in seen:
                errors.append("models[%d] duplicates %s on %s" % (i, model, engine))
            else:
                seen.add(pair)
        if not isinstance(entry.get("prescribed"), dict):
            errors.append("models[%d].prescribed must be an object" % i)
        measured = entry.get("measured")
        if not isinstance(measured, list):
            errors.append("models[%d].measured must be a list" % i)
        else:
            for j, item in enumerate(measured):
                errors.extend(_measured_errors(i, j, item))
        pitfalls = entry.get("pitfalls")
        if not isinstance(pitfalls, list):
            errors.append("models[%d].pitfalls must be a list" % i)
        else:
            for j, item in enumerate(pitfalls):
                errors.extend(_pitfall_errors(i, j, item))
    return errors


def add_pitfall(doc, model, engine, symptom, remedy, proof, date):
    """Return a new document with the pitfall appended; raise ValueError if the result is invalid."""
    new_doc = copy.deepcopy(doc)
    if not isinstance(new_doc, dict):
        new_doc = {}
    models = new_doc.get("models")
    if not isinstance(models, list):
        models = []
        new_doc["models"] = models
    entry = None
    for existing in models:
        if isinstance(existing, dict) and existing.get("model") == model and existing.get("engine") == engine:
            entry = existing
            break
    if entry is None:
        entry = {"model": model, "engine": engine, "prescribed": {}, "measured": [], "pitfalls": []}
        models.append(entry)
    pitfalls = entry.get("pitfalls")
    if not isinstance(pitfalls, list):
        pitfalls = []
        entry["pitfalls"] = pitfalls
    pitfalls.append({"date": date, "symptom": symptom, "remedy": remedy, "proof": proof})
    errors = validate(new_doc)
    if errors:
        raise ValueError("; ".join(errors))
    return new_doc


def summarize_log(records, model):
    """Return the measure dict for the records asked to one model: pure, it changes nothing.

    records: the log lines retained for that model_asked. Keys: calls, succeeded, percent,
    median (a %.1f string, or n/a), other_model, first and last (the smallest and largest
    time strings of the records that carry one, or unknown).
    """
    calls = len(records)
    succeeded = 0
    speeds = []
    other_model = 0
    times = []
    for record in records:
        if not isinstance(record, dict):
            continue
        if record.get("status") == "success":
            succeeded += 1
            tokens_out = record.get("tokens_out")
            seconds = record.get("seconds")
            if (isinstance(tokens_out, (int, float)) and not isinstance(tokens_out, bool)
                    and isinstance(seconds, (int, float)) and not isinstance(seconds, bool)
                    and tokens_out > 0 and seconds > 0):
                speeds.append(tokens_out / seconds)
        answered = record.get("model_answered")
        if isinstance(answered, str) and answered != "" and answered != model:
            other_model += 1
        when = record.get("time")
        if isinstance(when, str) and when != "":
            times.append(when)
    percent = round(100 * succeeded / calls) if calls else 0
    median = ("%.1f" % statistics.median(speeds)) if speeds else "n/a"
    return {
        "calls": calls,
        "succeeded": succeeded,
        "percent": percent,
        "median": median,
        "other_model": other_model,
        "first": min(times) if times else "unknown",
        "last": max(times) if times else "unknown",
    }


def add_measure(doc, model, engine, what, value, proof, date):
    """Return a new document with the measure appended; raise ValueError if the result is invalid."""
    new_doc = copy.deepcopy(doc)
    if not isinstance(new_doc, dict):
        new_doc = {}
    models = new_doc.get("models")
    if not isinstance(models, list):
        models = []
        new_doc["models"] = models
    entry = None
    for existing in models:
        if isinstance(existing, dict) and existing.get("model") == model and existing.get("engine") == engine:
            entry = existing
            break
    if entry is None:
        entry = {"model": model, "engine": engine, "prescribed": {}, "measured": [], "pitfalls": []}
        models.append(entry)
    measured = entry.get("measured")
    if not isinstance(measured, list):
        measured = []
        entry["measured"] = measured
    measured.append({"date": date, "what": what, "value": value, "proof": proof})
    errors = validate(new_doc)
    if errors:
        raise ValueError("; ".join(errors))
    return new_doc


def merge_documents(doc, contribution):
    """Return (new_doc, counts, conflict_lines): the merge of a validated contribution into a validated document.

    An entry whose (model, engine) pair is absent is appended whole; a pair already present
    receives each pitfall and each measure of the contribution that it does not already hold,
    and each prescribed key it does not hold. A prescribed key held with another value is kept
    and reported in conflict_lines. counts keys: pitfalls, measured, new_entries, prescribed.
    """
    new_doc = copy.deepcopy(doc)
    models = new_doc.get("models")
    if not isinstance(models, list):
        models = []
        new_doc["models"] = models
    counts = {"pitfalls": 0, "measured": 0, "new_entries": 0, "prescribed": 0}
    conflict_lines = []
    for entry in contribution.get("models", []):
        model = entry.get("model")
        engine = entry.get("engine")
        target = None
        for existing in models:
            if isinstance(existing, dict) and existing.get("model") == model and existing.get("engine") == engine:
                target = existing
                break
        if target is None:
            models.append(copy.deepcopy(entry))
            counts["new_entries"] += 1
            continue
        for key in ("pitfalls", "measured"):
            held = target.get(key)
            if not isinstance(held, list):
                held = []
                target[key] = held
            offered = entry.get(key)
            if not isinstance(offered, list):
                offered = []
            for item in offered:
                if item not in held:
                    held.append(copy.deepcopy(item))
                    counts[key] += 1
        target_prescribed = target.get("prescribed")
        if not isinstance(target_prescribed, dict):
            target_prescribed = {}
            target["prescribed"] = target_prescribed
        offered_prescribed = entry.get("prescribed")
        if not isinstance(offered_prescribed, dict):
            offered_prescribed = {}
        for key, value in offered_prescribed.items():
            if key not in target_prescribed:
                target_prescribed[key] = copy.deepcopy(value)
                counts["prescribed"] += 1
            elif target_prescribed[key] != value:
                conflict_lines.append(
                    "CONFLICT " + str(model) + " " + str(engine) + " prescribed." + key
                    + " kept " + json.dumps(target_prescribed[key]) + " offered " + json.dumps(value))
    return new_doc, counts, conflict_lines


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _read_log_records(path):
    """Return the list of JSON objects held by the JSON lines file; blank and non-object lines are skipped."""
    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line == "":
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if isinstance(record, dict):
                records.append(record)
    return records


def _write_json(path, doc):
    directory = os.path.dirname(os.path.abspath(path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=directory, prefix=".model_notes_", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(doc, f, indent=2)
            f.write("\n")
        os.replace(tmp_path, path)
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def _cmd_check(args):
    if len(args) != 1:
        sys.stdout.write(USAGE + "\n")
        return 2
    path = args[0]
    try:
        doc = _read_json(path)
    except (OSError, ValueError) as error:
        sys.stdout.write("ERROR cannot read " + path + ": " + str(error) + "\n")
        return 1
    errors = validate(doc)
    if not errors:
        sys.stdout.write("VALID " + path + "\n")
        return 0
    for message in errors:
        sys.stdout.write("ERROR " + message + "\n")
    return 1


def _cmd_add_pitfall(args):
    names = ("file", "model", "engine", "symptom", "remedy", "proof", "date")
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            sys.stdout.write(USAGE + "\n")
            return 2
        name = token[2:]
        if name not in names or i + 1 >= len(args):
            sys.stdout.write(USAGE + "\n")
            return 2
        keys[name] = args[i + 1]
        i += 2
    for required in ("file", "model", "engine", "symptom", "remedy", "proof"):
        if required not in keys:
            sys.stdout.write(USAGE + "\n")
            return 2
    file_path = keys["file"]
    date = keys.get("date")
    if date is None:
        date = datetime.date.today().isoformat()
    if os.path.exists(file_path):
        try:
            doc = _read_json(file_path)
        except (OSError, ValueError) as error:
            sys.stdout.write("REFUSED cannot read " + file_path + ": " + str(error) + "\n")
            return 1
        errors = validate(doc)
        if errors:
            sys.stdout.write("REFUSED " + "; ".join(errors) + "\n")
            return 1
    else:
        doc = {"schema_version": "1", "models": []}
    try:
        new_doc = add_pitfall(doc, keys["model"], keys["engine"], keys["symptom"], keys["remedy"], keys["proof"], date)
    except ValueError as error:
        sys.stdout.write("REFUSED " + str(error) + "\n")
        return 1
    _write_json(file_path, new_doc)
    sys.stdout.write("ADDED " + keys["model"] + " " + keys["engine"] + " " + date + "\n")
    return 0


def _cmd_show(args):
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token in ("--file", "--model") and i + 1 < len(args):
            keys[token[2:]] = args[i + 1]
            i += 2
        else:
            sys.stdout.write(USAGE + "\n")
            return 2
    if "file" not in keys or "model" not in keys:
        sys.stdout.write(USAGE + "\n")
        return 2
    file_path = keys["file"]
    model = keys["model"]
    try:
        doc = _read_json(file_path)
    except (OSError, ValueError) as error:
        sys.stdout.write("ERROR cannot read " + file_path + ": " + str(error) + "\n")
        return 1
    count = 0
    models = doc.get("models") if isinstance(doc, dict) else None
    if isinstance(models, list):
        for entry in models:
            if not isinstance(entry, dict) or entry.get("model") != model:
                continue
            engine = entry.get("engine")
            if not isinstance(engine, str):
                engine = ""
            pitfalls = entry.get("pitfalls")
            if not isinstance(pitfalls, list):
                continue
            for pitfall in pitfalls:
                if not isinstance(pitfall, dict):
                    continue
                date = pitfall.get("date")
                symptom = pitfall.get("symptom")
                remedy = pitfall.get("remedy")
                if not isinstance(date, str):
                    date = ""
                if not isinstance(symptom, str):
                    symptom = ""
                if not isinstance(remedy, str):
                    remedy = ""
                sys.stdout.write("PITFALL " + date + " " + engine + " " + symptom + " => " + remedy + "\n")
                count += 1
    if count == 0:
        sys.stdout.write("NONE " + model + "\n")
    return 0


def _cmd_merge(args):
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if token in ("--file", "--from") and i + 1 < len(args):
            keys[token[2:]] = args[i + 1]
            i += 2
        else:
            sys.stdout.write(USAGE + "\n")
            return 2
    if "file" not in keys or "from" not in keys:
        sys.stdout.write(USAGE + "\n")
        return 2
    file_path = keys["file"]
    contribution_path = keys["from"]
    try:
        contribution = _read_json(contribution_path)
    except (OSError, ValueError) as error:
        message = "cannot read " + contribution_path + ": " + str(error)
        sys.stdout.write("REFUSED " + contribution_path + ": " + message + "\n")
        sys.stdout.write("ERROR " + message + "\n")
        return 1
    errors = validate(contribution)
    if errors:
        sys.stdout.write("REFUSED " + contribution_path + ": " + errors[0] + "\n")
        for message in errors:
            sys.stdout.write("ERROR " + message + "\n")
        return 1
    if os.path.exists(file_path):
        try:
            doc = _read_json(file_path)
        except (OSError, ValueError) as error:
            sys.stdout.write("REFUSED " + file_path + ": cannot read " + file_path + ": " + str(error) + "\n")
            return 1
        errors = validate(doc)
        if errors:
            sys.stdout.write("REFUSED " + file_path + ": " + errors[0] + "\n")
            return 1
    else:
        doc = {"schema_version": "1", "models": []}
    new_doc, counts, conflict_lines = merge_documents(doc, contribution)
    if not any(counts.values()):
        sys.stdout.write("UNCHANGED " + file_path + "\n")
        return 0
    errors = validate(new_doc)
    if errors:
        for message in errors:
            sys.stdout.write("ERROR " + message + "\n")
        return 1
    _write_json(file_path, new_doc)
    sys.stdout.write("MERGED " + str(counts["pitfalls"]) + " pitfalls, " + str(counts["measured"])
                     + " measures, " + str(counts["new_entries"]) + " new entries from " + contribution_path + "\n")
    for line in conflict_lines:
        sys.stdout.write(line + "\n")
    return 0


def _cmd_measure(args):
    names = ("file", "log", "model", "engine", "date")
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            sys.stdout.write(USAGE + "\n")
            return 2
        name = token[2:]
        if name not in names or i + 1 >= len(args):
            sys.stdout.write(USAGE + "\n")
            return 2
        keys[name] = args[i + 1]
        i += 2
    for required in ("file", "log", "model", "engine"):
        if required not in keys:
            sys.stdout.write(USAGE + "\n")
            return 2
    file_path = keys["file"]
    log_path = keys["log"]
    model = keys["model"]
    engine = keys["engine"]
    try:
        records = _read_log_records(log_path)
    except (OSError, UnicodeDecodeError):
        sys.stdout.write("REFUSED cannot read " + log_path + "\n")
        return 1
    retained = [r for r in records if r.get("model_asked") == model]
    if not retained:
        sys.stdout.write("REFUSED no delegation of " + model + " in " + log_path + "\n")
        return 1
    if os.path.exists(file_path):
        try:
            doc = _read_json(file_path)
        except (OSError, ValueError) as error:
            sys.stdout.write("REFUSED cannot read " + file_path + ": " + str(error) + "\n")
            return 1
        errors = validate(doc)
        if errors:
            sys.stdout.write("REFUSED " + "; ".join(errors) + "\n")
            return 1
    else:
        doc = {"schema_version": "1", "models": []}
    date = keys.get("date")
    if date is None:
        date = datetime.date.today().isoformat()
    summary = summarize_log(retained, model)
    value = ("%d calls, %d succeeded (%d%%), median %s output tokens/s, %d answered by another model"
             % (summary["calls"], summary["succeeded"], summary["percent"],
                summary["median"], summary["other_model"]))
    proof = os.path.basename(log_path) + " from " + summary["first"] + " to " + summary["last"]
    try:
        new_doc = add_measure(doc, model, engine, "delegations in the log", value, proof, date)
    except ValueError as error:
        sys.stdout.write("REFUSED " + str(error) + "\n")
        return 1
    _write_json(file_path, new_doc)
    sys.stdout.write("MEASURED " + model + " " + engine + " " + date + " " + value + "\n")
    if summary["other_model"] > 0:
        sys.stdout.write("WARNING " + str(summary["other_model"])
                         + " answer(s) came from another model than " + model + "\n")
    return 0


FIXTURE_VALID ='{"schema_version": "1", "models": [{"model": "model-a", "engine": "engine-a", "prescribed": {"temperature": 1.0, "top_p": 0.95}, "measured": [{"date": "2026-09-17", "what": "throughput with a long window", "value": "slow", "proof": "timed run"}], "pitfalls": [{"date": "2026-09-19", "symptom": "typographic quotes eaten", "remedy": "send the prompt in a file", "proof": "delegation log"}]}]}'

FIXTURE_BAD = '{"schema_version": "1", "models": [{"model": "m1", "engine": "e1", "prescribed": {}, "measured": [], "pitfalls": [{"date": "2026-02-30", "symptom": "s", "remedy": "r", "proof": "p"}, {"date": "2026-03-01", "symptom": "s", "remedy": "r", "proof": ""}]}, {"model": "m1", "engine": "e1", "prescribed": {}, "measured": [], "pitfalls": []}]}'

PIT_A = {"date": "2026-09-19", "symptom": "s-a", "remedy": "r-a", "proof": "p-a"}
PIT_B = {"date": "2026-10-01", "symptom": "s-b", "remedy": "r-b", "proof": "p-b"}
MES_B = {"date": "2026-10-02", "what": "w-b", "value": "v-b", "proof": "p-b"}

FIXTURE_MERGE_TARGET = json.dumps({"schema_version": "1", "models": [
    {"model": "m1", "engine": "e1", "prescribed": {"temperature": 1.0}, "measured": [], "pitfalls": [PIT_A]}]})

FIXTURE_MERGE_CONTRIB = json.dumps({"schema_version": "1", "models": [
    {"model": "m1", "engine": "e1", "prescribed": {"temperature": 0.7, "top_p": 0.9},
     "measured": [MES_B], "pitfalls": [PIT_A, PIT_B]},
    {"model": "m2", "engine": "e2", "prescribed": {}, "measured": [], "pitfalls": [PIT_B]}]})

FIXTURE_MERGE_NO_PROOF = json.dumps({"schema_version": "1", "models": [
    {"model": "m1", "engine": "e1", "prescribed": {}, "measured": [],
     "pitfalls": [{"date": "2026-10-03", "symptom": "s-c", "remedy": "r-c", "proof": ""}]}]})

FIXTURE_LOG = (
    '{"time": "2026-09-01T08:00:00", "model_asked": "m9", "model_answered": "m9", "tokens_out": 999, "seconds": 1, "status": "success"}\n'
    '{"time": "2026-10-01T10:00:00", "model_asked": "m1", "model_answered": "m1", "tokens_out": 100, "seconds": 10, "status": "success"}\n'
    'not json at all\n'
    '{"time": "2026-10-02T10:00:00", "model_asked": "m1", "model_answered": "m1", "tokens_out": 300, "seconds": 10, "status": "success"}\n'
    '{"time": "2026-10-02T11:00:00", "model_asked": "m1", "model_answered": "m1", "tokens_out": 50, "seconds": 0, "status": "success"}\n'
    '{"time": "2026-10-02T12:00:00", "model_asked": "m1", "model_answered": null, "tokens_out": null, "seconds": 3, "status": "failure"}\n'
    '{"time": "2026-10-03T09:00:00", "model_asked": "m1", "model_answered": "m2", "tokens_out": 5, "seconds": 1, "status": "refused"}\n'
    '{"time": "2026-09-02T08:00:00", "model_asked": "m9", "model_answered": "m9", "tokens_out": 1, "seconds": 1, "status": "failure"}\n'
)

MEASURE_VALUE = "5 calls, 3 succeeded (60%), median 20.0 output tokens/s, 1 answered by another model"
MEASURE_ENTRY = {"date": "2026-10-09", "what": "delegations in the log", "value": MEASURE_VALUE,
                 "proof": "delegations.jsonl from 2026-10-01T10:00:00 to 2026-10-03T09:00:00"}


def _autotest():
    self = os.path.abspath(__file__)

    def run(args):
        return subprocess.run([sys.executable, self] + args, capture_output=True, text=True)

    failures = 0
    lines = []

    def record(number, ok, expected, obtained):
        nonlocal failures
        status = "PASS" if ok else "FAIL"
        lines.append("%s %d: expected %s | got %s" % (status, number, expected, obtained))
        if not ok:
            failures += 1

    with tempfile.TemporaryDirectory() as tmp:
        valid_path = os.path.join(tmp, "valid.json")
        bad_path = os.path.join(tmp, "bad.json")
        made_path = os.path.join(tmp, "made.json")
        with open(valid_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_VALID)
        with open(bad_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_BAD)

        # Test 1: check valid.json exits 0 with VALID
        r = run(["check", valid_path])
        record(1, r.returncode == 0 and r.stdout.strip() == "VALID " + valid_path,
               "rc=0 and VALID " + valid_path, "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 2: check bad.json exits 1 with the three ERROR lines
        r = run(["check", bad_path])
        want = [
            "ERROR models[0].pitfalls[0].date must be a date YYYY-MM-DD",
            "ERROR models[0].pitfalls[1].proof must be a non-empty string",
            "ERROR models[1] duplicates m1 on e1",
        ]
        got = r.stdout.strip().splitlines()
        record(2, r.returncode == 1 and got == want,
               "rc=1 and the three ERROR lines", "rc=" + str(r.returncode) + " out=" + repr(got))

        # Test 3: first add-pitfall on an absent file creates it, one pitfall, check 0
        r = run(["add-pitfall", "--file", made_path, "--model", "model-a", "--engine", "engine-a",
                 "--symptom", "a", "--remedy", "b", "--proof", "c", "--date", "2026-10-01"])
        ok3 = r.returncode == 0 and r.stdout.strip() == "ADDED model-a engine-a 2026-10-01"
        if ok3:
            with open(made_path, "r", encoding="utf-8") as f:
                made = json.load(f)
            models = made.get("models", [])
            ok3 = len(models) == 1 and len(models[0].get("pitfalls", [])) == 1
        if ok3:
            ok3 = run(["check", made_path]).returncode == 0
        record(3, ok3, "rc=0 ADDED model-a engine-a 2026-10-01, one pitfall, check 0",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 4: two more adds -> 2 pitfalls on engine-a then 1 on the other engine, dates in order
        r2 = run(["add-pitfall", "--file", made_path, "--model", "model-a", "--engine", "engine-a",
                  "--symptom", "d", "--remedy", "e", "--proof", "f", "--date", "2026-10-02"])
        r3 = run(["add-pitfall", "--file", made_path, "--model", "model-a", "--engine", "other",
                  "--symptom", "g", "--remedy", "h", "--proof", "i", "--date", "2026-10-03"])
        ok4 = r2.returncode == 0 and r3.returncode == 0
        dates = []
        if ok4:
            with open(made_path, "r", encoding="utf-8") as f:
                made = json.load(f)
            models = made.get("models", [])
            eng_a = [m for m in models if m.get("engine") == "engine-a"]
            others = [m for m in models if m.get("engine") == "other"]
            ok4 = (len(eng_a) == 1 and len(eng_a[0].get("pitfalls", [])) == 2
                   and len(others) == 1 and len(others[0].get("pitfalls", [])) == 1)
            if ok4:
                for m in models:
                    for p in m.get("pitfalls", []):
                        dates.append(p.get("date"))
                ok4 = dates == ["2026-10-01", "2026-10-02", "2026-10-03"]
        if ok4:
            ok4 = run(["check", made_path]).returncode == 0
        record(4, ok4, "rc=0, 2 pitfalls on engine-a then 1 on other, dates in order, check 0",
               "rc2=" + str(r2.returncode) + " rc3=" + str(r3.returncode) + " dates=" + repr(dates))

        # Test 5: add-pitfall with an empty proof refuses, file byte-for-byte unchanged
        w_path = os.path.join(tmp, "w.json")
        with open(w_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_VALID)
        with open(w_path, "rb") as f:
            before = f.read()
        r = run(["add-pitfall", "--file", w_path, "--model", "model-a", "--engine", "engine-a",
                 "--symptom", "x", "--remedy", "y", "--proof", "", "--date", "2026-10-01"])
        with open(w_path, "rb") as f:
            after = f.read()
        record(5, r.returncode == 1 and "REFUSED" in r.stdout and before == after,
               "rc=1 REFUSED and file unchanged", "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " unchanged=" + str(before == after))

        # Test 6: add-pitfall on bad.json refuses, byte-for-byte unchanged
        with open(bad_path, "rb") as f:
            before = f.read()
        r = run(["add-pitfall", "--file", bad_path, "--model", "m1", "--engine", "e1",
                 "--symptom", "x", "--remedy", "y", "--proof", "p", "--date", "2026-10-01"])
        with open(bad_path, "rb") as f:
            after = f.read()
        record(6, r.returncode == 1 and "REFUSED" in r.stdout and before == after,
               "rc=1 REFUSED and bad.json unchanged", "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " unchanged=" + str(before == after))

        # Test 7: show prints the PITFALL line and NONE for an absent model
        r = run(["show", "--file", valid_path, "--model", "model-a"])
        want_show = "PITFALL 2026-09-19 engine-a typographic quotes eaten => send the prompt in a file"
        ok7 = r.returncode == 0 and r.stdout.strip() == want_show
        r_absent = run(["show", "--file", valid_path, "--model", "absent-model"])
        ok7 = ok7 and r_absent.returncode == 0 and r_absent.stdout.strip() == "NONE absent-model"
        record(7, ok7, "rc=0 PITFALL line and NONE absent-model",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " rc_absent=" + str(r_absent.returncode) + " out_absent=" + repr(r_absent.stdout.strip()))

        # Test 8: unknown option exits 2
        r = run(["--unknown-option"])
        record(8, r.returncode == 2, "rc=2 for an unknown option",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()))

        # Test 9: --notice exits 0 and starts with the NAME line
        r = run(["--notice"])
        ok9 = r.returncode == 0 and r.stdout.startswith("NAME      model_notes.py") and "PITFALLS  2026-10-09" in r.stdout
        record(9, ok9, "rc=0 and notice starts with NAME and carries its date",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout[:60]))

        # Test 10: merge a contribution: new entry appended, pitfall and measure added,
        # prescribed conflict kept, then the same contribution replayed -> UNCHANGED, bytes equal
        merge_path = os.path.join(tmp, "merge_target.json")
        contrib_path = os.path.join(tmp, "contribution.json")
        with open(merge_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_MERGE_TARGET)
        with open(contrib_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_MERGE_CONTRIB)
        r = run(["merge", "--file", merge_path, "--from", contrib_path])
        want_merge = [
            "MERGED 1 pitfalls, 1 measures, 1 new entries from " + contrib_path,
            "CONFLICT m1 e1 prescribed.temperature kept 1.0 offered 0.7",
        ]
        got_merge = r.stdout.strip().splitlines()
        ok10 = r.returncode == 0 and got_merge == want_merge
        if ok10:
            with open(merge_path, "r", encoding="utf-8") as f:
                merged = json.load(f)
            models = merged.get("models", [])
            ok10 = (len(models) == 2
                    and models[0].get("model") == "m1" and models[0].get("pitfalls") == [PIT_A, PIT_B]
                    and models[0].get("measured") == [MES_B]
                    and models[0].get("prescribed") == {"temperature": 1.0, "top_p": 0.9}
                    and models[1].get("model") == "m2" and models[1].get("engine") == "e2"
                    and models[1].get("pitfalls") == [PIT_B])
        if ok10:
            ok10 = run(["check", merge_path]).returncode == 0
        with open(merge_path, "rb") as f:
            before = f.read()
        r_replay = run(["merge", "--file", merge_path, "--from", contrib_path])
        with open(merge_path, "rb") as f:
            after = f.read()
        ok10 = (ok10 and r_replay.returncode == 0
                and r_replay.stdout.strip() == "UNCHANGED " + merge_path and before == after)
        record(10, ok10,
               "rc=0 MERGED 1 pitfalls, 1 measures, 1 new entries + CONFLICT line, merged file as expected, "
               "replay rc=0 UNCHANGED and bytes equal",
               "rc=" + str(r.returncode) + " out=" + repr(got_merge)
               + " rc_replay=" + str(r_replay.returncode) + " out_replay=" + repr(r_replay.stdout.strip())
               + " unchanged=" + str(before == after))

        # Test 11: merge a contribution holding a pitfall without proof: rc=1, REFUSED, file unchanged
        bad_contrib_path = os.path.join(tmp, "contribution_no_proof.json")
        with open(bad_contrib_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_MERGE_NO_PROOF)
        with open(merge_path, "rb") as f:
            before = f.read()
        r = run(["merge", "--file", merge_path, "--from", bad_contrib_path])
        got_refused = r.stdout.strip().splitlines()
        ok11 = (r.returncode == 1 and len(got_refused) >= 2
                and got_refused[0] == "REFUSED " + bad_contrib_path + ": models[0].pitfalls[0].proof must be a non-empty string"
                and "proof must be a non-empty string" in r.stdout
                and got_refused[1] == "ERROR models[0].pitfalls[0].proof must be a non-empty string")
        with open(merge_path, "rb") as f:
            after = f.read()
        ok11 = ok11 and before == after
        record(11, ok11, "rc=1 REFUSED with the proof error and file unchanged",
               "rc=" + str(r.returncode) + " out=" + repr(got_refused)
               + " unchanged=" + str(before == after))

        # Test 12: measure on the delegation log, notes file absent: rc=0, the two exact lines,
        # the file created valid, the measured entry exact
        log_path = os.path.join(tmp, "delegations.jsonl")
        measure_path = os.path.join(tmp, "measured_notes.json")
        with open(log_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_LOG)
        r = run(["measure", "--file", measure_path, "--log", log_path,
                 "--model", "m1", "--engine", "e1", "--date", "2026-10-09"])
        want_measure = [
            "MEASURED m1 e1 2026-10-09 " + MEASURE_VALUE,
            "WARNING 1 answer(s) came from another model than m1",
        ]
        got_measure = r.stdout.strip().splitlines()
        ok12 = r.returncode == 0 and got_measure == want_measure
        if ok12:
            with open(measure_path, "r", encoding="utf-8") as f:
                measured_doc = json.load(f)
            models = measured_doc.get("models", [])
            ok12 = (len(models) == 1 and models[0].get("model") == "m1" and models[0].get("engine") == "e1"
                    and models[0].get("measured") == [MEASURE_ENTRY])
        if ok12:
            ok12 = run(["check", measure_path]).returncode == 0
        record(12, ok12,
               "rc=0 MEASURED m1 e1 2026-10-09 " + MEASURE_VALUE + " + WARNING line, file created valid, "
               "measured entry exact",
               "rc=" + str(r.returncode) + " out=" + repr(got_measure))

        # Test 13: measure a model absent from the log: rc=1, exact REFUSED line, notes not created
        absent_path = os.path.join(tmp, "absent_notes.json")
        r = run(["measure", "--file", absent_path, "--log", log_path,
                 "--model", "absent-model", "--engine", "e1", "--date", "2026-10-09"])
        want_absent = "REFUSED no delegation of absent-model in " + log_path
        ok13 = (r.returncode == 1 and r.stdout.strip() == want_absent
                and not os.path.exists(absent_path))
        record(13, ok13, "rc=1 " + want_absent + " and no notes file",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " created=" + str(os.path.exists(absent_path)))

        # Test 14: measure without --log exits 2 with USAGE
        r = run(["measure", "--file", measure_path, "--model", "m1", "--engine", "e1"])
        ok14 = r.returncode == 2 and r.stdout.strip().startswith("usage: model_notes.py")
        record(14, ok14, "rc=2 USAGE for a measure without --log",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip()[:40]))

        # Test 15: measure on bad.json refuses, byte-for-byte unchanged; an unreadable log refuses rc=1
        with open(bad_path, "rb") as f:
            before = f.read()
        r = run(["measure", "--file", bad_path, "--log", log_path,
                 "--model", "m1", "--engine", "e1", "--date", "2026-10-09"])
        with open(bad_path, "rb") as f:
            after = f.read()
        ok15 = r.returncode == 1 and "REFUSED" in r.stdout and before == after
        missing_log = os.path.join(tmp, "no_such_log.jsonl")
        r_log = run(["measure", "--file", measure_path, "--log", missing_log,
                     "--model", "m1", "--engine", "e1"])
        ok15 = (ok15 and r_log.returncode == 1
                and r_log.stdout.strip() == "REFUSED cannot read " + missing_log)
        record(15, ok15, "rc=1 REFUSED on bad.json unchanged, and rc=1 REFUSED cannot read on an absent log",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " unchanged=" + str(before == after)
               + " rc_log=" + str(r_log.returncode) + " out_log=" + repr(r_log.stdout.strip()))

    for line in lines:
        sys.stdout.write(line + "\n")
    return 1 if failures else 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(argv) == 1 and argv[0] == "--autotest":
        return _autotest()
    if not argv:
        sys.stdout.write(USAGE + "\n")
        return 2
    command = argv[0]
    if command == "check":
        return _cmd_check(argv[1:])
    if command == "add-pitfall":
        return _cmd_add_pitfall(argv[1:])
    if command == "show":
        return _cmd_show(argv[1:])
    if command == "merge":
        return _cmd_merge(argv[1:])
    if command == "measure":
        return _cmd_measure(argv[1:])
    sys.stdout.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "model_notes", sys.argv[1:])
