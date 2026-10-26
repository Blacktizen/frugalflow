import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

PYTEST_TIMEOUT = 120


def parse_summary(output):
    lines = [ln.strip() for ln in output.splitlines() if ln.strip()]
    for line in reversed(lines):
        if re.search(r"\d+ (passed|failed|error)", line):
            passed = re.search(r"(\d+) passed", line)
            failed = re.search(r"(\d+) failed", line)
            errors = re.search(r"(\d+) errors?", line)
            return (
                int(passed.group(1)) if passed else 0,
                int(failed.group(1)) if failed else 0,
                int(errors.group(1)) if errors else 0,
            )
    return None


def run_tests(project, modules):
    result = {}
    for module in modules:
        rel = os.path.join("tests", "test_%s.py" % module)
        if not os.path.isfile(os.path.join(project, rel)):
            result[module] = {
                "passed": 0,
                "failed": 0,
                "total": 0,
                "ok": False,
                "note": "missing test file",
            }
            continue
        env = dict(os.environ)
        env["PYTHONPATH"] = project
        env["PYTHONDONTWRITEBYTECODE"] = "1"
        cmd = [sys.executable, "-m", "pytest", rel, "-q", "--tb=no", "-p", "no:cacheprovider"]
        try:
            proc = subprocess.run(
                cmd, cwd=project, env=env, capture_output=True, text=True, timeout=PYTEST_TIMEOUT
            )
        except subprocess.TimeoutExpired:
            result[module] = {
                "passed": 0,
                "failed": 0,
                "total": 0,
                "ok": False,
                "note": "timeout",
            }
            continue
        counts = parse_summary((proc.stdout or "") + "\n" + (proc.stderr or ""))
        if counts is None:
            result[module] = {
                "passed": 0,
                "failed": 0,
                "total": 0,
                "ok": False,
                "note": "no pytest summary",
            }
            continue
        passed, failed, errors = counts
        total = passed + failed + errors
        result[module] = {
            "passed": passed,
            "failed": failed,
            "total": total,
            "ok": total > 0 and failed == 0 and errors == 0,
        }
    return result


def usage_int(usage, key):
    value = usage.get(key, 0)
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    return 0


def run_tokens(path):
    result_usage = None
    result_turns = 0
    seen_ids = set()
    usages = []
    with open(path, "r", encoding="utf-8") as handle:
        for raw in handle:
            raw = raw.strip()
            if not raw:
                continue
            try:
                obj = json.loads(raw)
            except ValueError:
                continue
            if not isinstance(obj, dict):
                continue
            kind = obj.get("type")
            if kind == "result" and isinstance(obj.get("usage"), dict):
                result_usage = obj["usage"]
                turns = obj.get("num_turns")
                result_turns = turns if isinstance(turns, int) and not isinstance(turns, bool) else 0
            elif kind == "assistant":
                message = obj.get("message")
                if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
                    continue
                mid = message.get("id")
                key = mid if mid is not None else "anon-%d" % len(usages)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                usages.append(message["usage"])
    if result_usage is not None:
        usage = result_usage
        source = "result"
        turns = result_turns
    else:
        usage = {}
        for key in (
            "input_tokens",
            "cache_creation_input_tokens",
            "cache_read_input_tokens",
            "output_tokens",
        ):
            usage[key] = sum(usage_int(u, key) for u in usages)
        source = "assistant"
        turns = len(usages)
    fresh = usage_int(usage, "input_tokens")
    cache_creation = usage_int(usage, "cache_creation_input_tokens")
    cache_read = usage_int(usage, "cache_read_input_tokens")
    output = usage_int(usage, "output_tokens")
    total_input = fresh + cache_creation + cache_read
    return {
        "input": total_input,
        "fresh_input": fresh,
        "cache_creation": cache_creation,
        "cache_read": cache_read,
        "output": output,
        "total": total_input + output,
        "turns": turns,
        "source": source,
    }


def write_file(path, content):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write(content)


def run_measure(args):
    proc = subprocess.run(
        [sys.executable, "-I", os.path.abspath(__file__)] + args,
        capture_output=True,
        text=True,
        timeout=300,
    )
    return proc.stdout


def check(name, expected, got):
    expected_text = json.dumps(expected, sort_keys=True)
    got_text = json.dumps(got, sort_keys=True)
    if got == expected:
        print("PASS %s expected=%s got=%s" % (name, expected_text, got_text))
        return True
    print("FAIL %s expected=%s got=%s" % (name, expected_text, got_text))
    return False


def autotest():
    base = tempfile.mkdtemp(prefix="measure_autotest_")
    ok_all = True
    try:
        project = os.path.join(base, "proj")
        os.makedirs(os.path.join(project, "kata"))
        os.makedirs(os.path.join(project, "tests"))
        write_file(os.path.join(project, "kata", "__init__.py"), "")
        write_file(os.path.join(project, "kata", "ok.py"), "def f():\n    return 1\n")
        write_file(
            os.path.join(project, "tests", "test_ok.py"),
            "import os\n"
            "import sys\n"
            "\n"
            "sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))\n"
            "\n"
            "from kata.ok import f\n"
            "\n"
            "\n"
            "def test_ok():\n"
            "    assert f() == 1\n",
        )
        write_file(
            os.path.join(project, "tests", "test_ko.py"),
            "def test_ko():\n    assert False\n",
        )
        got = json.loads(run_measure(["tests", project, "ok,ko,zz"]))
        expected = {"ok_ok": True, "ko_ok": False, "zz_ok": False, "zz_note": True}
        observed = {
            "ok_ok": got.get("ok", {}).get("ok"),
            "ko_ok": got.get("ko", {}).get("ok"),
            "zz_ok": got.get("zz", {}).get("ok"),
            "zz_note": "note" in got.get("zz", {}),
        }
        ok_all = check("tests", expected, observed) and ok_all

        assistant_lines = [
            {
                "type": "assistant",
                "message": {
                    "id": "a1",
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_read_input_tokens": 100,
                    },
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "a1",
                    "usage": {
                        "input_tokens": 10,
                        "output_tokens": 5,
                        "cache_read_input_tokens": 100,
                    },
                },
            },
            {
                "type": "assistant",
                "message": {
                    "id": "a2",
                    "usage": {"input_tokens": 1, "output_tokens": 2},
                },
            },
        ]

        stream1 = os.path.join(base, "stream1.jsonl")
        with open(stream1, "w", encoding="utf-8") as handle:
            for line in assistant_lines:
                handle.write(json.dumps(line) + "\n")
        got = json.loads(run_measure(["tokens", stream1]))
        expected = {
            "input": 111,
            "fresh_input": 11,
            "cache_creation": 0,
            "cache_read": 100,
            "output": 7,
            "total": 118,
            "turns": 2,
            "source": "assistant",
        }
        ok_all = check("tokens_assistant", expected, got) and ok_all

        stream2 = os.path.join(base, "stream2.jsonl")
        with open(stream2, "w", encoding="utf-8") as handle:
            for line in assistant_lines:
                handle.write(json.dumps(line) + "\n")
            handle.write("not a json line\n")
            handle.write(
                json.dumps(
                    {
                        "type": "result",
                        "usage": {"input_tokens": 7, "output_tokens": 3},
                        "num_turns": 4,
                    }
                )
                + "\n"
            )
        got = json.loads(run_measure(["tokens", stream2]))
        expected = {
            "input": 7,
            "fresh_input": 7,
            "cache_creation": 0,
            "cache_read": 0,
            "output": 3,
            "total": 10,
            "turns": 4,
            "source": "result",
        }
        ok_all = check("tokens_result", expected, got) and ok_all
    finally:
        shutil.rmtree(base, ignore_errors=True)
    return 0 if ok_all else 1


def main(argv):
    if len(argv) >= 2 and argv[1] == "--autotest":
        return autotest()
    if len(argv) >= 4 and argv[1] == "tests":
        modules = [m for m in argv[3].split(",") if m]
        print(json.dumps(run_tests(argv[2], modules)))
        return 0
    if len(argv) >= 3 and argv[1] == "tokens":
        print(json.dumps(run_tokens(argv[2])))
        return 0
    print("usage: measure.py tests PROJECT MODULE1,MODULE2 | tokens FLUX.jsonl | --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
