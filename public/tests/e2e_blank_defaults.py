#!/usr/bin/env python3
"""End-to-end test: blank defaults, public repo, no maintainer-specific values."""

import os
import re
import json
import subprocess
import sys
import tempfile
import shutil


HERE = os.path.dirname(os.path.abspath(__file__))
PUBLIC = os.path.dirname(HERE)
REPO = os.path.dirname(PUBLIC)
BIN = os.path.join(PUBLIC, "bin")
CONFIG = os.path.join(PUBLIC, "config")

NOTICE = (
    "NAME      e2e_blank_defaults.py - end-to-end test that the public repo "
    "holds no maintainer-specific value and that every default comes from a "
    "documented example file.\n"
    "READS     every text file of the repo folder; public/config/*.example.json; "
    "the tools in ../bin run with an empty home.\n"
    "WRITES    only in temporary folders, always removed. Exit 0 all steps pass, "
    "1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_blank_defaults.py\n"
    "PITFALLS  2026-10-25 code held defaults of one maintainer machine (an engine "
    "port, model names, limits); a stranger inherited them. Defaults now live in "
    "the example files only.\n"
)

_SUBSTRINGS_HALVES = [
    ("qw", "en"),
    ("deep", "seek"),
    ("3.8-", "27b"),
    ("flash", "-next"),
    ("iq3", "_xxs"),
    ("nin", "fer"),
    ("hyper", "ion"),
    ("100.", "69."),
    ("mode", "-eco"),
    ("av", "isy"),
    ("ma", "vy"),
    ("asg", "ard"),
    ("guarde", "fou-delegation"),
    ("/Use", "rs/"),
    (":80", "00"),
    (":80", "80"),
    ("2621", "44"),
    ("60", "000"),
]

_WORDS_HALVES = [
    ("strat", "a"),
    ("mich", "el"),
    ("sid", "ney"),
]


def join_halves(pairs):
    return [a + b for a, b in pairs]


SUBSTRINGS = join_halves(_SUBSTRINGS_HALVES)
WORDS = join_halves(_WORDS_HALVES)


def find_forbidden(text):
    t = text.replace("Blacktizen/frugalflow", "").lower()
    for s in SUBSTRINGS:
        if s in t:
            return True
    for w in WORDS:
        if re.search(r"\b" + re.escape(w) + r"\b", t):
            return True
    if "black" + "tizen" in t:
        return True
    if re.search(r"\b100\\*\.(?:6[4-9]|[7-9][0-9]|1[01][0-9]|12[0-7])\\*\.[0-9]+\\*\.[0-9]+", t):
        return True
    if re.search(r"\b(?:10|192\\*\.168)\\*\.[0-9]+\\*\.[0-9]+\\*\.[0-9]+", t):
        return True
    if re.search(r"\bn2[0-9]{2}\b", t) or re.search(r"guard-[0-9a-f]{6}", t):
        return True
    return False


ALLOWED_EXT = {".py", ".md", ".json", ".txt", ".yml", ".toml", ".sh", ".svg"}

IGNORE_FILES = {
    os.path.join("public", "data", "betterleaks_rules.json"),
    os.path.join("public", "data", "BETTERLEAKS_LICENSE"),
    os.path.join("public", "CREDITS.md"),
}


def base_env(home_dir):
    env = dict(os.environ)
    for key in list(env.keys()):
        if key.startswith("GIT_"):
            del env[key]
        elif key.startswith("FRUGALFLOW_"):
            del env[key]
        elif key.endswith("_API_KEY"):
            del env[key]
    env["HOME"] = home_dir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    return env


def read_text_file(path):
    with open(path, "r", encoding="utf-8", errors="ignore") as fh:
        return fh.read()


def test1():
    if not os.path.isdir(REPO):
        return False, "expected 0 forbidden files, REPO directory missing"
    offending = []
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in (".git", "__pycache__")]
        for fname in files:
            full = os.path.join(root, fname)
            rel = os.path.relpath(full, REPO)
            ext = os.path.splitext(fname)[1].lower()
            if ext not in ALLOWED_EXT:
                continue
            if rel in IGNORE_FILES:
                continue
            try:
                content = read_text_file(full)
            except OSError:
                continue
            if find_forbidden(content):
                offending.append(rel)
    count = len(offending)
    if count == 0:
        return True, "forbidden files found: 0"
    sample = offending[:5]
    return False, "forbidden files found: %d; first 5: %s" % (count, ", ".join(sample))


def test2():
    example_path = os.path.join(CONFIG, "engines.example.json")
    if not os.path.isfile(example_path):
        return False, "expected engines.example.json in CONFIG, file missing"
    raw = read_text_file(example_path)
    if not raw.strip():
        return False, "expected engines.example.json non-empty, got empty"
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return False, "expected valid JSON in engines.example.json"
    for key in ("ollama", "lmstudio"):
        if key not in data or not isinstance(data[key], dict) or "url" not in data[key]:
            return False, "missing key %s.url in engines.example.json" % key

    fixture1 = '{"ollama": {"url": "http://127.0.0.1:41001"}, "lmstudio": {"url": "http://127.0.0.1:41002"}}'
    fixture2 = "import env_detect; print(env_detect.OLLAMA_URL, env_detect.LMSTUDIO_URL)"

    tmp_dir = tempfile.mkdtemp()
    try:
        ex2 = os.path.join(tmp_dir, "ex2")
        os.makedirs(ex2)
        with open(os.path.join(ex2, "engines.example.json"), "w", encoding="utf-8") as fh:
            fh.write(fixture1)
        home_dir = os.path.join(tmp_dir, "home2")
        os.makedirs(home_dir)
        env = base_env(home_dir)
        env["FRUGALFLOW_EXAMPLES"] = ex2
        env["PYTHONPATH"] = BIN
        proc = subprocess.run(
            [sys.executable, "-c", fixture2],
            env=env,
            capture_output=True,
            text=True,
        )
        expected = "http://127.0.0.1:41001 http://127.0.0.1:41002\n"
        got = proc.stdout
        if got == expected:
            return True, "expected '%s', got '%s'" % (expected.strip(), got.strip())
        return False, "expected '%s', got '%s'" % (expected.strip(), got.strip())
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test3():
    example_guard = os.path.join(CONFIG, "guard.example.json")
    if not os.path.isfile(example_guard):
        return False, "guard.example.json missing in CONFIG"
    example_text = read_text_file(example_guard)
    if not example_text.strip():
        return False, "guard.example.json is empty"

    tmp_dir = tempfile.mkdtemp()
    try:
        home3 = os.path.join(tmp_dir, "home3")
        os.makedirs(home3)
        guard_fixture = '{"code_extensions": [".py"], "delegation_logs": ["log.jsonl"], "audit_log": "audit.jsonl"}'
        with open(os.path.join(home3, "guard.json"), "w", encoding="utf-8") as fh:
            fh.write(guard_fixture)
        with open(os.path.join(home3, "log.jsonl"), "w", encoding="utf-8") as fh:
            fh.write("")

        big_lines = "".join("line\n" for _ in range(120))
        with open(os.path.join(home3, "big.txt"), "w", encoding="utf-8") as fh:
            fh.write(big_lines)

        content_10 = "x = 1\n" * 10
        probe_path = os.path.join(home3, "probe.py")
        big_path = os.path.join(home3, "big.txt")

        cases = [
            {
                "name": "3a",
                "set_keys": {"line_threshold": 7},
                "stdin": json.dumps({"tool_name": "Write", "tool_input": {"file_path": probe_path, "content": content_10}}),
                "expect_deny": True,
            },
            {
                "name": "3b",
                "set_keys": {"line_threshold": 50},
                "stdin": json.dumps({"tool_name": "Write", "tool_input": {"file_path": probe_path, "content": content_10}}),
                "expect_deny": False,
            },
            {
                "name": "3c",
                "set_keys": {"intake_max_lines": 100},
                "stdin": json.dumps({"tool_name": "Read", "tool_input": {"file_path": big_path}, "cwd": home3}),
                "expect_deny": True,
            },
            {
                "name": "3d",
                "set_keys": {"intake_max_lines": 1000},
                "stdin": json.dumps({"tool_name": "Read", "tool_input": {"file_path": big_path}, "cwd": home3}),
                "expect_deny": False,
            },
        ]

        for idx, case in enumerate(cases):
            ex3 = os.path.join(tmp_dir, "ex3_%d" % idx)
            os.makedirs(ex3)
            shutil.copy2(example_guard, os.path.join(ex3, "guard.example.json"))
            ex_guard_path = os.path.join(ex3, "guard.example.json")
            guard_data = json.loads(read_text_file(ex_guard_path))
            for k, v in case["set_keys"].items():
                guard_data[k] = v
            with open(ex_guard_path, "w", encoding="utf-8") as fh:
                json.dump(guard_data, fh)

            env = base_env(home3)
            env["FRUGALFLOW_HOME"] = home3
            env["FRUGALFLOW_EXAMPLES"] = ex3

            proc = subprocess.run(
                [sys.executable, os.path.join(BIN, "guard_hook.py"), "--hook"],
                env=env,
                input=case["stdin"],
                capture_output=True,
                text=True,
            )
            out = proc.stdout
            if proc.returncode != 0:
                return False, "%s expected exit 0, got %d" % (case["name"], proc.returncode)
            if case["expect_deny"]:
                if not out:
                    return False, "%s expected a deny, got empty output" % case["name"]
                if "permissionDecision" in out and "deny" in out:
                    continue
                return False, "%s expected deny, got: %s" % (case["name"], out[:120])
            else:
                if "deny" not in out:
                    continue
                return False, "%s expected no deny, got: %s" % (case["name"], out[:120])

        return True, "all 4 guard hook cases OK"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test4():
    tmp_dir = tempfile.mkdtemp()
    try:
        home4 = os.path.join(tmp_dir, "home4")
        os.makedirs(home4)

        ff_dir = os.path.join(home4, "ff")
        cl_dir = os.path.join(home4, "cl")

        cmd = [
            sys.executable,
            os.path.join(BIN, "frugalflow.py"),
            "init",
            "--home", ff_dir,
            "--claude-dir", cl_dir,
            "--ollama-url", "http://127.0.0.1:1",
            "--lmstudio-url", "http://127.0.0.1:1",
        ]
        env = base_env(home4)
        proc = subprocess.run(cmd, env=env, capture_output=True, text=True)
        if proc.returncode != 0:
            return False, "expected exit 0 from init, got %d" % proc.returncode

        if not os.path.isdir(ff_dir):
            return False, "expected %s created by init, missing" % ff_dir

        expected_files = {"models.json", "model_notes.json", "anonymization.json", "preferences.json", "guard.json"}
        actual_files = {f for f in os.listdir(ff_dir) if f.endswith(".json")}
        if actual_files != expected_files:
            return False, "expected json files %s, got %s" % (sorted(expected_files), sorted(actual_files))

        for name, example_name in [
            ("models.json", "models.example.json"),
            ("model_notes.json", "model_notes.example.json"),
            ("anonymization.json", "anonymization.example.json"),
        ]:
            got_text = read_text_file(os.path.join(ff_dir, name))
            exp_text = read_text_file(os.path.join(CONFIG, example_name))
            if not got_text:
                return False, "%s is empty" % name
            if got_text != exp_text:
                return False, "%s does not match %s" % (name, example_name)

        pref = json.loads(read_text_file(os.path.join(ff_dir, "preferences.json")))
        pref.pop("switch", None)
        pref_exp = json.loads(read_text_file(os.path.join(CONFIG, "preferences.example.json")))
        if pref != pref_exp:
            return False, "preferences.json (minus switch) does not match preferences.example.json"

        guard = json.loads(read_text_file(os.path.join(ff_dir, "guard.json")))
        guard.pop("fix_hint", None)
        guard_exp = json.loads(read_text_file(os.path.join(CONFIG, "guard.example.json")))
        guard_exp.pop("fix_hint", None)
        if guard != guard_exp:
            return False, "guard.json (minus fix_hint) does not match guard.example.json"

        return True, "all init output files match examples"
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)


def test5():
    schema_path = os.path.join(PUBLIC, "SCHEMA_JSON.md")
    if not os.path.isfile(schema_path):
        return False, "expected SCHEMA_JSON.md in PUBLIC, missing"
    schema_text = read_text_file(schema_path)
    if not schema_text:
        return False, "SCHEMA_JSON.md is empty"

    example_files = [
        f for f in os.listdir(CONFIG)
        if f.endswith(".example.json")
    ]
    if not example_files:
        return False, "no *.example.json files found in CONFIG"
    for fname in example_files:
        if fname not in schema_text:
            return False, "%s not cited in SCHEMA_JSON.md" % fname

    proc_bogus = subprocess.run(
        [sys.executable, os.path.join(HERE, "e2e_blank_defaults.py"), "--bogus"],
        capture_output=True,
        text=True,
    )
    if proc_bogus.returncode != 2:
        return False, "expected exit 2 for --bogus, got %d" % proc_bogus.returncode

    proc_notice = subprocess.run(
        [sys.executable, os.path.join(HERE, "e2e_blank_defaults.py"), "--notice"],
        capture_output=True,
        text=True,
    )
    if proc_notice.returncode != 0:
        return False, "expected exit 0 for --notice, got %d" % proc_notice.returncode

    return True, "documentation and exit codes verified"


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv and argv != ["--notice"]:
        sys.stdout.write("usage: e2e_blank_defaults.py [--notice]\n")
        return 2

    results = []
    fail_count = 0

    ok, msg = test1()
    status = "PASS" if ok else "FAIL"
    if not ok:
        fail_count += 1
    results.append("%s e1: %s" % (status, msg))

    ok, msg = test2()
    status = "PASS" if ok else "FAIL"
    if not ok:
        fail_count += 1
    results.append("%s e2: %s" % (status, msg))

    ok, msg = test3()
    status = "PASS" if ok else "FAIL"
    if not ok:
        fail_count += 1
    results.append("%s e3: %s" % (status, msg))

    ok, msg = test4()
    status = "PASS" if ok else "FAIL"
    if not ok:
        fail_count += 1
    results.append("%s e4: %s" % (status, msg))

    ok, msg = test5()
    status = "PASS" if ok else "FAIL"
    if not ok:
        fail_count += 1
    results.append("%s e5: %s" % (status, msg))

    for line in results:
        sys.stdout.write(line + "\n")

    if fail_count == 0:
        sys.stdout.write("E2E BLANK DEFAULTS OK\n")
        return 0
    else:
        sys.stdout.write("E2E BLANK DEFAULTS FAILED %d\n" % fail_count)
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
