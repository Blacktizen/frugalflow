"""bench_run.py - launches one bench execution (or every task/condition/rep) for a task under a condition, checks the result and appends one JSON line per execution."""

import os
import re
import sys
import json
import time
import shutil
import tempfile
import datetime
import subprocess
import signal

USAGE = (
    "usage: bench_run.py run --tasks TASKS_JSON --conditions COND_JSON --task ID --condition NAME "
    "--out RESULTS_JSONL [--rep N] [--timeout S] [--keep DIR] | run-all --tasks TASKS_JSON "
    "--conditions COND_JSON --out RESULTS_JSONL [--reps N] [--timeout S] [--keep DIR] [--only ID,ID] "
    "[--names NAME,NAME] | --notice | --autotest"
)

NOTICE = (
    "NAME      bench_run.py - launches one bench execution (or every task/condition/rep) for a task under a condition, checks the result and appends one JSON line per execution.\n"
    "READS     the task catalog given by --tasks ({\"schema_version\": \"1\", \"tasks\": [{\"id\", \"title\", \"kind\"}]}) and the task folders tasks/<id>/ beside it (task.md, setup/, prepare.py optional, check.py); the conditions file given by --conditions; the delegation log of each condition; the existing lines of --out when run-all resumes.\n"
    "WRITES    --out: one JSON line per execution, created folder by folder as needed; with --keep, the stdout and stderr copies under DIR/<task>-<condition>-<rep>/; each run folder is removed at the end.\n"
    "EXAMPLE   python3 bench_run.py run --tasks tasks.json --conditions conditions.json --task t01 --condition good --out results.jsonl --rep 1 --timeout 1800\n"
    "PITFALLS  2026-10-09 the cost is recomputed from the token counts and the condition prices, never taken from total_cost_usd: an orchestrator may bill at another model's rate, and a bench that trusts it compares prices, not work.\n"
    "          2026-10-09 run-all skips a (task, condition, rep) triplet already present in --out: a killed bench resumes where it stopped instead of paying twice.\n"
    "          2026-10-10 on timeout the whole process group is killed: an orchestrator's children no longer outlive the run.\n"
)

KEY_ORDER = [
    "time", "task", "kind", "condition", "rep", "solved", "check_rc", "command_rc", "error",
    "seconds", "input_tokens", "cache_creation_tokens", "cache_read_tokens", "output_tokens",
    "turns", "reported_cost_usd", "cost_usd", "delegated_calls", "delegated_tokens_in",
    "delegated_tokens_out",
]

_POSITIVE_INT_RE = re.compile(r"\A[0-9]+\Z")
_TIME_RE = re.compile(r"\A[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}\Z")

_PREP_TIMEOUT = 120
_CHECK_TIMEOUT = 120


def _positive_int(text):
    """Return the integer behind text when it is a positive int, else None."""
    if not isinstance(text, str) or _POSITIVE_INT_RE.match(text) is None:
        return None
    value = int(text)
    if value < 1:
        return None
    return value


def _parse_flags(args, required, optional):
    """Return the {name: value} dict of the --name VALUE flags, or None when the args are invalid."""
    keys = {}
    i = 0
    while i < len(args):
        token = args[i]
        if not token.startswith("--"):
            return None
        name = token[2:]
        if name not in required and name not in optional:
            return None
        if i + 1 >= len(args):
            return None
        keys[name] = args[i + 1]
        i += 2
    for name in required:
        if name not in keys:
            return None
    return keys


def _read_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def _substitute(text, replacements):
    """Replace the {run}, {workdir} and {task} markers in text."""
    for marker in ("{run}", "{workdir}", "{task}"):
        text = text.replace(marker, replacements[marker])
    return text


def _load_tasks(tasks_path):
    """Return {id: task entry} for the catalog, keeping nothing else."""
    doc = _read_json(tasks_path)
    tasks = {}
    order = []
    entries = doc.get("tasks") if isinstance(doc, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("id"), str):
                tasks[entry["id"]] = entry
                order.append(entry["id"])
    return tasks, order


def _load_conditions(conditions_path):
    """Return {name: condition entry} and the file order of the names."""
    doc = _read_json(conditions_path)
    conditions = {}
    order = []
    entries = doc.get("conditions") if isinstance(doc, dict) else None
    if isinstance(entries, list):
        for entry in entries:
            if isinstance(entry, dict) and isinstance(entry.get("name"), str):
                conditions[entry["name"]] = entry
                order.append(entry["name"])
    return conditions, order


def _task_dir(tasks_path, task_id):
    return os.path.join(os.path.dirname(os.path.abspath(tasks_path)), "tasks", task_id)


def _task_folder_complete(task_dir):
    return (os.path.isdir(task_dir)
            and os.path.isfile(os.path.join(task_dir, "task.md"))
            and os.path.isdir(os.path.join(task_dir, "setup"))
            and os.path.isfile(os.path.join(task_dir, "check.py")))


def _is_number(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _last_json_object_line(stdout_text):
    """Return the last stdout line that reads as a JSON object, or None."""
    found = None
    for line in stdout_text.splitlines():
        line = line.strip()
        if line == "":
            continue
        try:
            parsed = json.loads(line)
        except ValueError:
            continue
        if isinstance(parsed, dict):
            found = parsed
    return found


def _token_count(usage, field):
    if not isinstance(usage, dict):
        return 0
    value = usage.get(field)
    if _is_number(value):
        return value
    return 0


def _delegation_stats(path):
    """Return (calls, tokens_in, tokens_out) for the JSON-lines log: non-object lines are skipped,
    token fields that are not numbers are not summed."""
    calls = 0
    tokens_in = 0
    tokens_out = 0
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line == "":
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            calls += 1
            if _is_number(record.get("tokens_in")):
                tokens_in += record["tokens_in"]
            if _is_number(record.get("tokens_out")):
                tokens_out += record["tokens_out"]
    return calls, tokens_in, tokens_out


def _append_out(out_path, record):
    directory = os.path.dirname(os.path.abspath(out_path))
    if directory:
        os.makedirs(directory, exist_ok=True)
    with open(out_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record) + "\n")


def _existing_triplets(out_path):
    """Return the set of (task, condition, rep) triplets already written in out_path."""
    triplets = set()
    if not os.path.isfile(out_path):
        return triplets
    with open(out_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line == "":
                continue
            try:
                record = json.loads(line)
            except ValueError:
                continue
            if not isinstance(record, dict):
                continue
            triplets.add((record.get("task"), record.get("condition"), record.get("rep")))
    return triplets


def _run_one(tasks_path, conditions_path, task_id, condition_name, rep, timeout, keep_dir, out_path):
    """Do one execution: print the RESULT or REFUSED line, append the out line when the run happened.
    Return "done", "refused" or "skipped"."""
    tasks, _ = _load_tasks(tasks_path)
    conditions, _ = _load_conditions(conditions_path)
    if condition_name not in conditions:
        sys.stdout.write("REFUSED unknown condition " + str(condition_name) + "\n")
        return "refused"
    if task_id not in tasks or not _task_folder_complete(_task_dir(tasks_path, task_id)):
        sys.stdout.write("REFUSED unknown task " + str(task_id) + "\n")
        return "refused"

    condition = conditions[condition_name]
    task_dir = _task_dir(tasks_path, task_id)
    run_dir = tempfile.mkdtemp(prefix="bench_run_")
    try:
        work_dir = os.path.join(run_dir, "work")
        shutil.copytree(os.path.join(task_dir, "setup"), work_dir)
        shutil.copy2(os.path.join(task_dir, "task.md"), os.path.join(run_dir, "task.md"))

        prepare_path = os.path.join(task_dir, "prepare.py")
        if os.path.isfile(prepare_path):
            try:
                prep = subprocess.run([sys.executable, "-I", "-S", prepare_path],
                                      cwd=work_dir, stdin=subprocess.DEVNULL,
                                      capture_output=True, text=True, timeout=_PREP_TIMEOUT)
            except subprocess.TimeoutExpired:
                prep = None
            if prep is None or prep.returncode != 0:
                sys.stdout.write("REFUSED prepare failed for " + str(task_id) + "\n")
                return "refused"

        replacements = {
            "{run}": run_dir,
            "{workdir}": work_dir,
            "{task}": os.path.join(run_dir, "task.md"),
        }

        context_file = condition.get("context_file")
        if isinstance(context_file, str) and context_file != "":
            source = os.path.join(os.path.dirname(os.path.abspath(conditions_path)), context_file)
            shutil.copy2(source, os.path.join(work_dir, "CLAUDE.md"))

        delegation_log = condition.get("delegation_log")
        delegation_path = None
        if isinstance(delegation_log, str) and delegation_log != "":
            delegation_path = _substitute(delegation_log, replacements)
            parent = os.path.dirname(delegation_path)
            if parent:
                os.makedirs(parent, exist_ok=True)

        command = condition.get("command")
        argv = []
        if isinstance(command, list):
            for item in command:
                argv.append(_substitute(str(item), replacements))

        env = os.environ.copy()
        condition_env = condition.get("env")
        if isinstance(condition_env, dict):
            for name, value in condition_env.items():
                env[name] = _substitute(str(value), replacements)

        started = time.time()
        timed_out = False
        stdout_text = ""
        stderr_text = ""
        command_rc = 0
        proc = subprocess.Popen(argv, cwd=work_dir, stdin=subprocess.DEVNULL,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                text=True, env=env, start_new_session=True)
        try:
            proc_out, proc_err = proc.communicate(timeout=timeout)
            stdout_text = proc_out if isinstance(proc_out, str) else ""
            stderr_text = proc_err if isinstance(proc_err, str) else ""
            command_rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
            try:
                os.killpg(proc.pid, signal.SIGKILL)
            except ProcessLookupError:
                pass
            proc_out, proc_err = proc.communicate()
            stdout_text = proc_out if isinstance(proc_out, str) else ""
            stderr_text = proc_err if isinstance(proc_err, str) else ""
            command_rc = -1
        seconds = round(time.time() - started, 1)

        error = None
        if timed_out:
            error = "timeout"

        result = _last_json_object_line(stdout_text)
        input_tokens = None
        cache_creation_tokens = None
        cache_read_tokens = None
        output_tokens = None
        turns = None
        reported_cost_usd = None
        cost_usd = None
        if result is not None:
            usage = result.get("usage")
            input_tokens = _token_count(usage, "input_tokens")
            cache_creation_tokens = _token_count(usage, "cache_creation_input_tokens")
            cache_read_tokens = _token_count(usage, "cache_read_input_tokens")
            output_tokens = _token_count(usage, "output_tokens")
            if _is_number(result.get("num_turns")):
                turns = result["num_turns"]
            if _is_number(result.get("total_cost_usd")):
                reported_cost_usd = result["total_cost_usd"]
            prices = condition.get("prices")
            if not isinstance(prices, dict):
                prices = {}
            price_in = prices.get("input") if _is_number(prices.get("input")) else 0
            price_cached = prices.get("cached_input") if _is_number(prices.get("cached_input")) else 0
            price_out = prices.get("output") if _is_number(prices.get("output")) else 0
            cost_usd = round(
                (input_tokens * price_in + cache_creation_tokens * price_in
                 + cache_read_tokens * price_cached + output_tokens * price_out) / 1000000.0, 6)
            if result.get("is_error"):
                error = "orchestrator reported an error"
        elif error is None:
            error = "no JSON result"

        check_path = os.path.join(task_dir, "check.py")
        try:
            check = subprocess.run([sys.executable, "-I", "-S", check_path],
                                   cwd=work_dir, stdin=subprocess.DEVNULL,
                                   capture_output=True, text=True, timeout=_CHECK_TIMEOUT)
            check_rc = check.returncode
        except subprocess.TimeoutExpired:
            check_rc = -1
        solved = check_rc == 0

        if delegation_path is not None and os.path.isfile(delegation_path):
            delegated_calls, delegated_tokens_in, delegated_tokens_out = _delegation_stats(delegation_path)
        else:
            delegated_calls, delegated_tokens_in, delegated_tokens_out = 0, 0, 0

        if isinstance(keep_dir, str) and keep_dir != "":
            kept = os.path.join(keep_dir, str(task_id) + "-" + str(condition_name) + "-" + str(rep))
            os.makedirs(kept, exist_ok=True)
            with open(os.path.join(kept, "stdout.txt"), "w", encoding="utf-8") as f:
                f.write(stdout_text)
            with open(os.path.join(kept, "stderr.txt"), "w", encoding="utf-8") as f:
                f.write(stderr_text)

        record = {
            "time": datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
            "task": task_id,
            "kind": tasks[task_id].get("kind"),
            "condition": condition_name,
            "rep": rep,
            "solved": solved,
            "check_rc": check_rc,
            "command_rc": command_rc,
            "error": error,
            "seconds": seconds,
            "input_tokens": input_tokens,
            "cache_creation_tokens": cache_creation_tokens,
            "cache_read_tokens": cache_read_tokens,
            "output_tokens": output_tokens,
            "turns": turns,
            "reported_cost_usd": reported_cost_usd,
            "cost_usd": cost_usd,
            "delegated_calls": delegated_calls,
            "delegated_tokens_in": delegated_tokens_in,
            "delegated_tokens_out": delegated_tokens_out,
        }
        _append_out(out_path, record)

        cost_text = ("%.6f" % cost_usd) if cost_usd is not None else "n/a"
        sys.stdout.write("RESULT " + str(task_id) + " " + str(condition_name) + " " + str(rep)
                         + " solved=" + ("true" if solved else "false")
                         + " cost=" + cost_text + " seconds=" + ("%.1f" % seconds) + "\n")
        return "done"
    finally:
        shutil.rmtree(run_dir, ignore_errors=True)


def _cmd_run(args):
    keys = _parse_flags(args, ("tasks", "conditions", "task", "condition", "out"),
                        ("rep", "timeout", "keep"))
    if keys is None:
        sys.stdout.write(USAGE + "\n")
        return 2
    rep = 1
    if "rep" in keys:
        rep = _positive_int(keys["rep"])
        if rep is None:
            sys.stdout.write(USAGE + "\n")
            return 2
    timeout = 1800
    if "timeout" in keys:
        timeout = _positive_int(keys["timeout"])
        if timeout is None:
            sys.stdout.write(USAGE + "\n")
            return 2
    outcome = _run_one(keys["tasks"], keys["conditions"], keys["task"], keys["condition"],
                       rep, timeout, keys.get("keep"), keys["out"])
    return 1 if outcome == "refused" else 0


def _cmd_run_all(args):
    keys = _parse_flags(args, ("tasks", "conditions", "out"),
                        ("reps", "timeout", "keep", "only", "names"))
    if keys is None:
        sys.stdout.write(USAGE + "\n")
        return 2
    reps = 1
    if "reps" in keys:
        reps = _positive_int(keys["reps"])
        if reps is None:
            sys.stdout.write(USAGE + "\n")
            return 2
    timeout = 1800
    if "timeout" in keys:
        timeout = _positive_int(keys["timeout"])
        if timeout is None:
            sys.stdout.write(USAGE + "\n")
            return 2
    only = None
    if "only" in keys:
        only = set(part for part in keys["only"].split(",") if part != "")
    names = None
    if "names" in keys:
        names = set(part for part in keys["names"].split(",") if part != "")

    tasks, task_order = _load_tasks(keys["tasks"])
    conditions, condition_order = _load_conditions(keys["conditions"])
    done = 0
    skipped = 0
    refused = 0
    for task_id in task_order:
        if only is not None and task_id not in only:
            continue
        for condition_name in condition_order:
            if names is not None and condition_name not in names:
                continue
            for rep in range(1, reps + 1):
                if (task_id, condition_name, rep) in _existing_triplets(keys["out"]):
                    skipped += 1
                    continue
                outcome = _run_one(keys["tasks"], keys["conditions"], task_id, condition_name,
                                   rep, timeout, keys.get("keep"), keys["out"])
                if outcome == "refused":
                    refused += 1
                else:
                    done += 1
    sys.stdout.write("DONE " + str(done) + " runs, " + str(skipped) + " skipped, "
                     + str(refused) + " refused\n")
    return 1 if refused else 0


FIXTURE_TASKS = json.dumps({"schema_version": "1", "tasks": [
    {"id": "t01", "title": "write the answer", "kind": "code"},
    {"id": "t02", "title": "read the logs", "kind": "logs"},
    {"id": "t03", "title": "prepare breaks", "kind": "code"}]})

FIXTURE_CHECK = (
    "import sys\n"
    "try:\n"
    "    data = open('answer.txt', 'r', encoding='utf-8').read()\n"
    "except OSError:\n"
    "    sys.exit(1)\n"
    "sys.exit(0 if '42' in data else 1)\n"
)

FIXTURE_GOOD = (
    "import json, os\n"
    "with open('answer.txt', 'w', encoding='utf-8') as f:\n"
    "    f.write('42\\n')\n"
    "log = os.environ.get('FF_LOG')\n"
    "if log:\n"
    "    parent = os.path.dirname(log)\n"
    "    if parent:\n"
    "        os.makedirs(parent, exist_ok=True)\n"
    "    with open(log, 'a', encoding='utf-8') as f:\n"
    "        f.write('{\"tokens_in\": 100, \"tokens_out\": 40}\\n')\n"
    "        f.write('{\"tokens_in\": 50, \"tokens_out\": null}\\n')\n"
    "print('working')\n"
    "print(json.dumps({\"type\": \"result\", \"is_error\": False, \"num_turns\": 4, \"total_cost_usd\": 9.99,\n"
    "    \"usage\": {\"input_tokens\": 1000, \"cache_creation_input_tokens\": 200,\n"
    "              \"cache_read_input_tokens\": 3000, \"output_tokens\": 500}}))\n"
)

FIXTURE_BAD = (
    "import os\n"
    "print('context=yes' if os.path.exists('CLAUDE.md') else 'context=no')\n"
)

FIXTURE_SLOW = (
    "import time\n"
    "time.sleep(30)\n"
)

FIXTURE_DETACHED = (
    "import os, subprocess, sys, time\n"
    "subprocess.Popen([sys.executable, \"-c\", \"import os, time; time.sleep(4); "
    "open(os.environ['MARK'], 'w').write('alive')\"])\n"
    "time.sleep(30)\n"
)

FIXTURE_PREPARE = (
    "import sys\n"
    "sys.exit(3)\n"
)

FIXTURE_CONDITIONS = json.dumps({"schema_version": "1", "conditions": [
    {"name": "good", "command": ["python3", "good.py"],
     "env": {"FF_LOG": "{run}/ff/delegations.jsonl"},
     "delegation_log": "{run}/ff/delegations.jsonl",
     "prices": {"input": 0.5, "cached_input": 0.1, "output": 2.0}},
    {"name": "bad", "command": ["python3", "bad.py"], "context_file": "ctx.md",
     "prices": {"input": 0.5, "cached_input": 0.1, "output": 2.0}},
    {"name": "slow", "command": ["python3", "slow.py"],
     "prices": {"input": 0.5, "cached_input": 0.1, "output": 2.0}}]})


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
        tasks_path = os.path.join(tmp, "tasks.json")
        conditions_path = os.path.join(tmp, "conditions.json")
        out_path = os.path.join(tmp, "results.jsonl")
        keep_path = os.path.join(tmp, "keep")
        with open(tasks_path, "w", encoding="utf-8") as f:
            f.write(FIXTURE_TASKS)
        conditions_doc = json.loads(FIXTURE_CONDITIONS)
        conditions_doc["conditions"].append({
            "name": "detached",
            "command": ["python3", "detached.py"],
            "env": {"MARK": os.path.join(tmp, "marker.txt")},
            "prices": {"input": 0.5, "cached_input": 0.1, "output": 2.0}})
        with open(conditions_path, "w", encoding="utf-8") as f:
            f.write(json.dumps(conditions_doc))
        with open(os.path.join(tmp, "ctx.md"), "w", encoding="utf-8") as f:
            f.write("context discipline notes\n")
        for task_id in ("t01", "t02", "t03"):
            task_dir = os.path.join(tmp, "tasks", task_id)
            os.makedirs(os.path.join(task_dir, "setup"))
            with open(os.path.join(task_dir, "task.md"), "w", encoding="utf-8") as f:
                f.write("Put 42 in answer.txt.\n")
            with open(os.path.join(task_dir, "setup", "readme.txt"), "w", encoding="utf-8") as f:
                f.write("start\n")
            with open(os.path.join(task_dir, "setup", "good.py"), "w", encoding="utf-8") as f:
                f.write(FIXTURE_GOOD)
            with open(os.path.join(task_dir, "setup", "bad.py"), "w", encoding="utf-8") as f:
                f.write(FIXTURE_BAD)
            with open(os.path.join(task_dir, "setup", "slow.py"), "w", encoding="utf-8") as f:
                f.write(FIXTURE_SLOW)
            with open(os.path.join(task_dir, "setup", "detached.py"), "w", encoding="utf-8") as f:
                f.write(FIXTURE_DETACHED)
            with open(os.path.join(task_dir, "check.py"), "w", encoding="utf-8") as f:
                f.write(FIXTURE_CHECK)
        with open(os.path.join(tmp, "tasks", "t03", "prepare.py"), "w", encoding="utf-8") as f:
            f.write(FIXTURE_PREPARE)

        def out_records():
            records = []
            if os.path.isfile(out_path):
                with open(out_path, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line != "":
                            records.append(json.loads(line))
            return records

        # Test 1: run t01 under good: rc 0, the RESULT line, one out line with the 20 exact keys and values
        r = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                 "--task", "t01", "--condition", "good", "--out", out_path])
        ok1 = r.returncode == 0 and re.match(
            r"\ARESULT t01 good 1 solved=true cost=0\.001900 seconds=[0-9]+\.[0-9]\Z",
            r.stdout.strip()) is not None
        records = out_records()
        if ok1:
            ok1 = len(records) == 1
        if ok1:
            rec = records[0]
            ok1 = (list(rec.keys()) == KEY_ORDER
                   and _TIME_RE.match(str(rec.get("time"))) is not None
                   and rec.get("task") == "t01" and rec.get("kind") == "code"
                   and rec.get("condition") == "good" and rec.get("rep") == 1
                   and rec.get("solved") is True and rec.get("check_rc") == 0
                   and rec.get("command_rc") == 0 and rec.get("error") is None
                   and _is_number(rec.get("seconds"))
                   and rec.get("input_tokens") == 1000 and rec.get("cache_creation_tokens") == 200
                   and rec.get("cache_read_tokens") == 3000 and rec.get("output_tokens") == 500
                   and rec.get("turns") == 4 and rec.get("reported_cost_usd") == 9.99
                   and rec.get("cost_usd") == 0.0019
                   and rec.get("delegated_calls") == 2 and rec.get("delegated_tokens_in") == 150
                   and rec.get("delegated_tokens_out") == 40)
        record(1, ok1,
               "rc=0 RESULT t01 good 1 solved=true cost=0.001900, one out line with the 20 keys "
               "(turns 4, reported 9.99, cost 0.0019, delegated 2/150/40)",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " records=" + repr(records))

        # Test 2: run t01 under bad with --keep: rc 0, solved false, null tokens, no JSON result, stdout copy
        r = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                 "--task", "t01", "--condition", "bad", "--out", out_path, "--keep", keep_path])
        ok2 = r.returncode == 0 and re.match(
            r"\ARESULT t01 bad 1 solved=false cost=n/a seconds=[0-9]+\.[0-9]\Z",
            r.stdout.strip()) is not None
        records = out_records()
        if ok2:
            ok2 = len(records) == 2
        if ok2:
            rec = records[1]
            ok2 = (rec.get("task") == "t01" and rec.get("condition") == "bad"
                   and rec.get("solved") is False and rec.get("check_rc") == 1
                   and rec.get("command_rc") == 0 and rec.get("error") == "no JSON result"
                   and rec.get("input_tokens") is None and rec.get("cache_creation_tokens") is None
                   and rec.get("cache_read_tokens") is None and rec.get("output_tokens") is None
                   and rec.get("turns") is None and rec.get("reported_cost_usd") is None
                   and rec.get("cost_usd") is None
                   and rec.get("delegated_calls") == 0 and rec.get("delegated_tokens_in") == 0
                   and rec.get("delegated_tokens_out") == 0)
        if ok2:
            kept_path = os.path.join(keep_path, "t01-bad-1", "stdout.txt")
            try:
                with open(kept_path, "r", encoding="utf-8") as f:
                    ok2 = "context=yes" in f.read()
            except OSError:
                ok2 = False
        record(2, ok2,
               "rc=0 solved=false cost=n/a, out line with null tokens and error no JSON result, "
               "kept stdout contains context=yes",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout.strip())
               + " records=" + repr(records[1:] if len(records) > 1 else records))

        # Test 3: run t01 under slow with --timeout 2: rc 0 in under 15 s, command_rc -1, error timeout
        started = time.time()
        r = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                 "--task", "t01", "--condition", "slow", "--out", out_path, "--timeout", "2"])
        elapsed = time.time() - started
        records = out_records()
        ok3 = r.returncode == 0 and elapsed < 15 and len(records) == 3
        if ok3:
            rec = records[2]
            ok3 = (rec.get("command_rc") == -1 and rec.get("error") == "timeout"
                   and rec.get("solved") is False)
        record(3, ok3, "rc=0 in under 15 s, command_rc -1, error timeout",
               "rc=" + str(r.returncode) + " elapsed=" + ("%.1f" % elapsed)
               + " records=" + repr(records[2:] if len(records) > 2 else records))

        # Test 4: refusals (unknown condition, unknown task, prepare exit 3) leave --out untouched;
        # --rep 0 exits 2; run-all --only t01,t02 --names good,bad resumes and prints DONE
        before = open(out_path, "rb").read() if os.path.isfile(out_path) else b""
        r_cond = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                      "--task", "t01", "--condition", "nope", "--out", out_path])
        r_task = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                      "--task", "t99", "--condition", "good", "--out", out_path])
        r_prep = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                      "--task", "t03", "--condition", "good", "--out", out_path])
        r_rep = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                     "--task", "t01", "--condition", "good", "--out", out_path, "--rep", "0"])
        after = open(out_path, "rb").read() if os.path.isfile(out_path) else b""
        ok4 = (r_cond.returncode == 1 and r_cond.stdout.strip() == "REFUSED unknown condition nope"
               and r_task.returncode == 1 and r_task.stdout.strip() == "REFUSED unknown task t99"
               and r_prep.returncode == 1 and r_prep.stdout.strip() == "REFUSED prepare failed for t03"
               and r_rep.returncode == 2 and r_rep.stdout.strip().startswith("usage: bench_run.py")
               and before == after)
        r_all = run(["run-all", "--tasks", tasks_path, "--conditions", conditions_path,
                     "--out", out_path, "--only", "t01,t02", "--names", "good,bad"])
        ok4 = ok4 and r_all.returncode == 0
        if ok4:
            all_lines = r_all.stdout.strip().splitlines()
            ok4 = all_lines[-1] == "DONE 2 runs, 2 skipped, 0 refused"
        if ok4:
            records = out_records()
            pairs = [(rec.get("task"), rec.get("condition")) for rec in records
                     if rec.get("condition") in ("good", "bad")]
            ok4 = (len(pairs) == 4
                   and pairs.count(("t01", "good")) == 1 and pairs.count(("t01", "bad")) == 1
                   and pairs.count(("t02", "good")) == 1 and pairs.count(("t02", "bad")) == 1)
        record(4, ok4,
               "rc=1 REFUSED unknown condition / unknown task / prepare failed with --out unchanged, "
               "rc=2 USAGE for --rep 0, run-all rc=0 DONE 2 runs, 2 skipped, 0 refused and 4 out lines",
               "rc_cond=" + str(r_cond.returncode) + " " + repr(r_cond.stdout.strip())
               + " rc_task=" + str(r_task.returncode) + " " + repr(r_task.stdout.strip())
               + " rc_prep=" + str(r_prep.returncode) + " " + repr(r_prep.stdout.strip())
               + " rc_rep=" + str(r_rep.returncode)
               + " unchanged=" + str(before == after)
               + " rc_all=" + str(r_all.returncode) + " " + repr(r_all.stdout.strip().splitlines()[-1:]))

        # Test 5: --notice exits 0 with the NAME line and the dated PITFALLS line
        r = run(["--notice"])
        ok5 = (r.returncode == 0 and r.stdout.startswith("NAME      bench_run.py")
               and "PITFALLS  2026-10-09" in r.stdout)
        record(5, ok5, "rc=0 notice starting with NAME and carrying PITFALLS 2026-10-09",
               "rc=" + str(r.returncode) + " out=" + repr(r.stdout[:60]))

        # Test 6: on timeout the whole process group is killed: the detached child that would
        # write the marker file 4 s later is killed too, so 6 s after the run the marker is absent
        mark_path = os.path.join(tmp, "marker.txt")
        started = time.time()
        r = run(["run", "--tasks", tasks_path, "--conditions", conditions_path,
                 "--task", "t01", "--condition", "detached", "--out", out_path, "--timeout", "1"])
        elapsed = time.time() - started
        records = out_records()
        time.sleep(6)
        ok6 = (r.returncode == 0 and elapsed < 15 and not os.path.exists(mark_path)
               and len(records) >= 4
               and records[-1].get("command_rc") == -1
               and records[-1].get("error") == "timeout")
        record(6, ok6,
               "rc=0 command_rc -1 error timeout and no marker file 6 s after the run",
               "rc=" + str(r.returncode) + " elapsed=" + ("%.1f" % elapsed)
               + " marker=" + str(os.path.exists(mark_path))
               + " records=" + repr(records[3:] if len(records) > 3 else records))

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
    if command == "run":
        return _cmd_run(argv[1:])
    if command == "run-all":
        return _cmd_run_all(argv[1:])
    sys.stdout.write(USAGE + "\n")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "bench_run", sys.argv[1:])
