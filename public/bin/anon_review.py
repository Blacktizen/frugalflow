import datetime
import hashlib
import json
import os
import subprocess
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import anon_review_rules as rules

USAGE = 'usage: anon_review.py [--report FILE] [--models FILE] [--role NAME] [--effort LEVEL] [--trust LEVEL] [PATH ...] | --notice | --autotest'

NOTICE = '''NAME      anon_review.py - has the local model reread each file, one fresh call per file, and appends its suspicions of private details to a report; it proposes, it never guards.
READS     the files given, else every file under public/; models.json (--models, else FRUGALFLOW_HOME, else ~/.frugalflow); the model's answer through delegate.py.
WRITES    one line per file appended to --report, else FRUGALFLOW_HOME/anon_review.jsonl; exits 0 clean, 4 suspicions, 3 a file not reviewed, 2 on a bad argument.
EXAMPLE   python3 anon_review.py public/bin/tool.py
PITFALLS  2026-09-26 an unreachable model must never look like a clean file; any file not reviewed exits 3.
          2026-10-10 without --trust no review could reach a remote model: delegate.py stays private and refuses it.'''

STUB = '''import re
import sys
a = sys.argv
if "--role" not in a or "--models" not in a:
    sys.exit(2)
t = open(a[a.index("--file") + 1], encoding="utf-8").read()
m = re.search(r"=== BEGIN FILE (.*) ===", t)
if m and m.group(1).startswith("/"):
    sys.exit(3)
if "TRUSTME" in t:
    if "--trust" not in a or a[a.index("--trust") + 1] != "untrusted_third_party":
        sys.exit(3)
if "CRASH" in t:
    sys.exit(3)
if "GARBLE" in t:
    print("looks fine to me")
    sys.exit(0)
if "Ginette" in t:
    print('{"line": 1, "excerpt": "Ginette", "kind": "private_name", "why": "a first name"}')
    sys.exit(0)
print("NONE")
'''

MODELS = '{"models": [{"id": "m1", "name": "stub-model"}], "roles": [{"name": "documents", "model": "m1"}]}'


def home():
    return os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")


def root():
    return os.environ.get("ANON_REVIEW_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def delegate_path():
    return os.environ.get("ANON_REVIEW_DELEGATE") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "delegate.py")


def rel_name(path):
    # The model must never see the operator's absolute path: it would flag the user name inside it.
    p = os.path.abspath(path)
    for base in (os.path.dirname(root()), os.getcwd()):
        r = os.path.relpath(p, base)
        if not r.startswith(".."):
            return r
    return os.path.basename(p)


def model_name(models, role):
    try:
        with open(models, encoding="utf-8") as f:
            d = json.load(f)
        role_model = None
        for r in d["roles"]:
            if r["name"] == role:
                role_model = r["model"]
                break
        if role_model is None:
            return "unknown"
        for m in d["models"]:
            if m["id"] == role_model:
                return m["name"]
        return "unknown"
    except Exception:
        return "unknown"


def list_files(top):
    results = []
    for dirpath, dirnames, filenames in os.walk(top):
        dirnames[:] = [d for d in dirnames if d != "__pycache__" and not d.startswith(".")]
        for fn in filenames:
            if fn.endswith(".pyc") or fn.startswith("."):
                continue
            results.append(os.path.join(dirpath, fn))
    return sorted(results)


def review_one(path, role, models, effort, trust):
    with open(path, "rb") as f:
        raw = f.read()
    sha = hashlib.sha256(raw).hexdigest()
    text = raw.decode("utf-8", errors="replace")
    with tempfile.TemporaryDirectory() as t:
        task_path = os.path.join(t, "task.md")
        with open(task_path, "w", encoding="utf-8") as f:
            f.write(rules.build_prompt(rel_name(path), text))
        cmd = [sys.executable, delegate_path(), "--role", role, "--file", task_path, "--models", models, "--effort", effort]
        if trust is not None:
            cmd += ["--trust", trust]
        cmd += ["--brief-waiver", "anonymization review prompt, not a code brief"]
        try:
            proc = subprocess.run(cmd, capture_output=True, text=True)
        except OSError:
            return ("unread", [], 0, sha)
        if proc.returncode != 0:
            return ("unread", [], 0, sha)
        status, suspicions, unreadable = rules.parse_answer(proc.stdout)
        return (status, suspicions, unreadable, sha)


def append(report, entry):
    os.makedirs(os.path.dirname(os.path.abspath(report)), exist_ok=True)
    with open(report, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False, sort_keys=True) + "\n")


def main():
    args = sys.argv[1:]

    if "--notice" in args:
        print(NOTICE)
        sys.exit(0)

    if "--autotest" in args:
        sys.exit(_autotest())

    report = os.path.join(home(), "anon_review.jsonl")
    models = os.path.join(home(), "models.json")
    role = "documents"
    effort = "medium"
    trust = None
    paths = []

    i = 0
    while i < len(args):
        a = args[i]
        if a == "--report":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            report = args[i]
        elif a == "--models":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            models = args[i]
        elif a == "--role":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            role = args[i]
        elif a == "--effort":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            effort = args[i]
        elif a == "--trust":
            i += 1
            if i >= len(args):
                print(USAGE)
                sys.exit(2)
            trust = args[i]
        elif a.startswith("--"):
            print(USAGE)
            sys.exit(2)
        else:
            paths.append(a)
        i += 1

    if not paths:
        paths = list_files(root())

    if not paths:
        print(USAGE)
        sys.exit(2)

    for p in paths:
        if not os.path.isfile(p):
            print("missing: " + p, file=sys.stderr)
            sys.exit(2)

    n = 0
    m = 0
    k = 0

    for p in paths:
        status, suspicions, unreadable, sha = review_one(p, role, models, effort, trust)
        n += 1
        if status == "unread":
            k += 1
            print("UNREAD " + p)
        elif status == "suspicions":
            m += len(suspicions)
            for s in suspicions:
                print("SUSPECT " + p + ":" + str(s["line"]) + " " + s["kind"])
        else:
            print("CLEAN " + p)

        entry = {
            "date": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
            "file": p,
            "sha256": sha,
            "model": model_name(models, role),
            "role": role,
            "status": status,
            "unreadable": unreadable,
            "suspicions": suspicions,
        }
        append(report, entry)

    print(f"REVIEWED {n} SUSPICIONS {m} UNREAD {k}")

    if k > 0:
        sys.exit(3)
    elif m > 0:
        sys.exit(4)
    else:
        sys.exit(0)


def _setup(d):
    with open(os.path.join(d, "stub.py"), "w", encoding="utf-8") as f:
        f.write(STUB)
    os.makedirs(os.path.join(d, "home"))
    with open(os.path.join(d, "home", "models.json"), "w", encoding="utf-8") as f:
        f.write(MODELS)
    os.makedirs(os.path.join(d, "tree"))
    with open(os.path.join(d, "tree", "a.py"), "w", encoding="utf-8") as f:
        f.write("x = 1\n")
    os.makedirs(os.path.join(d, "tree", "sub"))
    with open(os.path.join(d, "tree", "sub", "b.py"), "w", encoding="utf-8") as f:
        f.write("owner = 'Ginette'\n")
    os.makedirs(os.path.join(d, "tree", "__pycache__"))
    with open(os.path.join(d, "tree", "__pycache__", "c.pyc"), "w", encoding="utf-8") as f:
        f.write("zz")


def _run(d, args, env_extra=None):
    env = dict(os.environ)
    env["ANON_REVIEW_DELEGATE"] = os.path.join(d, "stub.py")
    env["FRUGALFLOW_HOME"] = os.path.join(d, "home")
    env["ANON_REVIEW_ROOT"] = os.path.join(d, "tree")
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + args,
        capture_output=True, text=True, env=env
    )
    return (proc.returncode, proc.stdout)


def _lines(d):
    path = os.path.join(d, "home", "anon_review.jsonl")
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def _t1(d):
    code, out = _run(d, [os.path.join(d, "tree", "a.py")])
    if not out:
        return "empty stdout"
    if code != 0:
        return f"exit {code}"
    if "CLEAN " not in out:
        return f"no CLEAN in stdout"
    lines = _lines(d)
    if len(lines) != 1:
        return f"lines {len(lines)} != 1"
    if lines[0]["status"] != "clean":
        return f"status {lines[0]['status']}"
    if lines[0]["model"] != "stub-model":
        return f"model {lines[0]['model']}"
    expected_sha = hashlib.sha256(b"x = 1\n").hexdigest()
    if lines[0]["sha256"] != expected_sha:
        return f"sha mismatch"
    return None


def _t2(d):
    code, out = _run(d, [os.path.join(d, "tree", "sub", "b.py")])
    if not out:
        return "empty stdout"
    if code != 4:
        return f"exit {code}"
    if ":1 private_name" not in out:
        return f"no ':1 private_name' in stdout"
    if "Ginette" in out:
        return f"Ginette leaked in stdout"
    lines = _lines(d)
    if not lines:
        return "no lines"
    if lines[0]["status"] != "suspicions":
        return f"status {lines[0]['status']}"
    if lines[0]["suspicions"][0]["excerpt"] != "Ginette":
        return f"excerpt {lines[0]['suspicions'][0]['excerpt']}"
    return None


def _t3(d):
    code1, out1 = _run(d, [])
    if not out1:
        return "first run empty stdout"
    if code1 != 4:
        return f"first exit {code1}"
    lines1 = _lines(d)
    code2, out2 = _run(d, [])
    if not out2:
        return "second run empty stdout"
    if code2 != 4:
        return f"second exit {code2}"
    lines2 = _lines(d)
    if len(lines2) != 4:
        return f"lines {len(lines2)} != 4"
    for l in lines2:
        if l["file"].endswith(".pyc"):
            return f"pyc file {l['file']} in report"
    for i in range(2):
        if lines2[i] != lines1[i]:
            return f"line {i} differs between runs"
    return None


def _t4(d):
    with open(os.path.join(d, "tree", "c.py"), "w", encoding="utf-8") as f:
        f.write("CRASH\n")
    with open(os.path.join(d, "tree", "g.py"), "w", encoding="utf-8") as f:
        f.write("GARBLE\n")
    code, out = _run(d, [os.path.join(d, "tree", "a.py"), os.path.join(d, "tree", "c.py")])
    if not out:
        return "first run empty stdout"
    if code != 3:
        return f"first exit {code}"
    if "UNREAD " not in out:
        return f"no UNREAD in stdout"
    code2, out2 = _run(d, [os.path.join(d, "tree", "g.py")])
    if not out2:
        return "second run empty stdout"
    if code2 != 3:
        return f"second exit {code2}"
    code3, out3 = _run(d, [os.path.join(d, "tree", "a.py")], env_extra={"ANON_REVIEW_DELEGATE": os.path.join(d, "absent.py")})
    if not out3:
        return "third run empty stdout"
    if code3 != 3:
        return f"third exit {code3}"
    return None


def _t5(d):
    code, out = _run(d, ["--notice"])
    if not out:
        return "notice empty stdout"
    if code != 0:
        return f"notice exit {code}"
    if not out.startswith("NAME      anon_review.py"):
        return f"notice starts with {out[:30]!r}"
    code2, out2 = _run(d, [os.path.join(d, "nope.py")])
    if code2 != 2:
        return f"missing exit {code2}"
    lines = _lines(d)
    if lines:
        return f"lines not empty after missing: {len(lines)}"
    code3, out3 = _run(d, ["--report"])
    if code3 != 2:
        return f"--report exit {code3}"
    rjsonl = os.path.join(d, "r.jsonl")
    code4, out4 = _run(d, ["--report", rjsonl, os.path.join(d, "tree", "a.py")])
    if not out4:
        return "report run empty stdout"
    if code4 != 0:
        return f"report exit {code4}"
    if not os.path.isfile(rjsonl):
        return "r.jsonl not created"
    with open(rjsonl, encoding="utf-8") as f:
        rlines = [line for line in f if line.strip()]
    if len(rlines) != 1:
        return f"r.jsonl has {len(rlines)} lines != 1"
    return None


def _t6(d):
    p = os.path.join(d, "tree", "t.py")
    with open(p, "w", encoding="utf-8") as f:
        f.write("TRUSTME\n")
    code, out = _run(d, ["--trust", "untrusted_third_party", p])
    if not out:
        return "first run empty stdout"
    if code != 0:
        return f"first exit {code}"
    code2, out2 = _run(d, [p])
    if not out2:
        return "second run empty stdout"
    if code2 != 3:
        return f"second exit {code2}"
    code3, out3 = _run(d, ["--trust"])
    if code3 != 2:
        return f"--trust-only exit {code3}"
    return None


def _autotest():
    tests = [
        ("clean file exits 0", _t1),
        ("suspicion exits 4 hides excerpt", _t2),
        ("walk appends without rewriting", _t3),
        ("unreachable model exits 3", _t4),
        ("notice missing report-arg", _t5),
        ("trust reaches delegate", _t6),
    ]
    all_pass = True
    for idx, (desc, fn) in enumerate(tests, 1):
        with tempfile.TemporaryDirectory() as d:
            _setup(d)
            err = fn(d)
        if err is None:
            print(f"PASS {idx}")
        else:
            print(f"FAIL {idx} expected: {desc} got: {err}")
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "anon_review", sys.argv[1:])
