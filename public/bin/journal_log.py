import sys, os, json, time, atexit, hashlib, datetime, tempfile, shutil, subprocess, importlib.util

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import journal_rules
except ImportError:
    local_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "journal_rules.py")
    if os.path.exists(local_file):
        spec = importlib.util.spec_from_file_location("journal_rules", local_file)
        journal_rules = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(journal_rules)
    else:
        raise

_STATE = None
_PATH = None
_REGISTERED = False

def default_path():
    if "FRUGALFLOW_HOME" in os.environ:
        return os.path.join(os.environ["FRUGALFLOW_HOME"], "delegations.jsonl")
    else:
        return os.path.join(os.path.expanduser("~"), ".frugalflow", "delegations.jsonl")

def arm(path, role, model_asked, target, subject, chars=None, waiver=None):
    global _PATH, _STATE, _REGISTERED
    _PATH = path
    _STATE = journal_rules.new_state(role, model_asked, os.path.realpath(target) if isinstance(target, str) and target else None, subject)
    _STATE.update(chars=chars, waiver=waiver, _t0=time.monotonic())
    if not _REGISTERED:
        atexit.register(_write)
        _REGISTERED = True

def conclude(status, reason=None, tokens_in=None, tokens_out=None, model_answered=None):
    global _STATE
    if _STATE is None:
        return
    _STATE = journal_rules.conclude(_STATE, status, reason, tokens_in, tokens_out, model_answered)

def _write():
    global _STATE
    if _STATE is None:
        return
    try:
        state = _STATE
        _STATE = None
        if "_t0" in state:
            state["seconds"] = round(time.monotonic() - state["_t0"], 1)
        sha = None
        target = state.get("target") if isinstance(state, dict) else None
        if target and os.path.isfile(target):
            with open(target, "rb") as f:
                sha = hashlib.sha256(f.read()).hexdigest()
        now = datetime.datetime.now().strftime("%Y-%m-%dT%H:%M:%S")
        directory = os.path.dirname(_PATH)
        if directory:
            os.makedirs(directory, exist_ok=True)
        line = journal_rules.to_line(state, now, sha)
        with open(_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception as exc:
        sys.stderr.write("LOG WARNING: " + str(exc) + "\n")

NOTICE = '''NAME      journal_log.py - writes one log line per delegation, even when the caller exits on an error, and sums a log up.
READS     --log, else FRUGALFLOW_HOME/delegations.jsonl, else ~/.frugalflow/delegations.jsonl; the delegated file, for its sha256.
WRITES    one JSON line appended at exit by arm() and conclude(); --summary prints the counts (0), or NO LOG (2).
EXAMPLE   python3 journal_log.py --summary
PITFALLS  2026-08-20 a delegation that stopped on an error left no line; the line is now written at exit, whatever the exit code.
'''

def run_autotest():
    D = tempfile.mkdtemp()
    try:
        dir_path = os.path.dirname(os.path.abspath(__file__))
        file_path = os.path.abspath(__file__)
        PRELUDE = f"""import sys, importlib.util, importlib.machinery
sys.path.insert(0, {dir_path!r})
_loader = importlib.machinery.SourceFileLoader('jl', {file_path!r})
_s = importlib.util.spec_from_loader(_loader.name, _loader)
J = importlib.util.module_from_spec(_s)
_loader.exec_module(J)
"""
        dest = os.path.join(D, "out.py")
        with open(dest, "wb") as f:
            f.write(b"abc")
        expected_sha = hashlib.sha256(b"abc").hexdigest()
        SUMMARY_LOG = '{"status": "success"}\n{"status": "failure"}\n{"status": "refused"}\nbroken\n'
        log1 = os.path.join(D, "log1.jsonl")
        log2 = os.path.join(D, "log2.jsonl")
        log3 = os.path.join(D, "log3.jsonl")

        results = []

        # Test 1
        code1 = "J.arm(%r, 'code', 'alpha-7b', %r, 'NATURE: creation')\nJ.conclude('success', None, 10, 20, 'alpha-7b')\n" % (log1, dest)
        proc = subprocess.run([sys.executable, "-c", PRELUDE + code1], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc1 = proc.returncode
        stderr1 = proc.stderr.strip()
        try:
            with open(log1, "r", encoding="utf-8") as f:
                lines1 = f.readlines()
            if len(lines1) != 1:
                ok1 = False
                desc1 = "count of lines = %d" % len(lines1)
            else:
                rec1 = json.loads(lines1[0])
                ok1 = (rc1 == 0 and rec1.get("status") == "success" and rec1.get("model_answered") == "alpha-7b" and rec1.get("tokens_out") == 20 and rec1.get("sha256") == expected_sha and rec1.get("role") == "code")
                desc1 = "status=%s, model_answered=%s, tokens_out=%s, sha256=%s, role=%s" % (rec1.get("status"), rec1.get("model_answered"), rec1.get("tokens_out"), rec1.get("sha256"), rec1.get("role"))
        except Exception as e:
            ok1 = False
            desc1 = "exception reading log: %s" % e
        if not ok1 and stderr1:
            desc1 += " | stderr: %s" % stderr1
        results.append(("test 1", ok1, "status=success, model_answered=alpha-7b, tokens_out=20, sha256 correct, role=code", desc1))

        # Test 2
        code2 = "J.arm(%r, 'code', 'alpha-7b', None, 'x')\nsys.exit(1)\n" % (log2,)
        proc = subprocess.run([sys.executable, "-c", PRELUDE + code2], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc2 = proc.returncode
        stderr2 = proc.stderr.strip()
        try:
            with open(log2, "r", encoding="utf-8") as f:
                lines2 = f.readlines()
            if len(lines2) != 1:
                ok2 = False
                desc2 = "count of lines = %d" % len(lines2)
            else:
                rec2 = json.loads(lines2[0])
                ok2 = (rc2 == 1 and rec2.get("status") == "failure" and rec2.get("reason") == "exit without conclusion")
                desc2 = "status=%s, reason=%s" % (rec2.get("status"), rec2.get("reason"))
        except Exception as e:
            ok2 = False
            desc2 = "exception reading log: %s" % e
        if not ok2 and stderr2:
            desc2 += " | stderr: %s" % stderr2
        results.append(("test 2", ok2, "status=failure, reason=exit without conclusion", desc2))

        # Test 3
        code3 = "J.arm(%r, 'code', 'alpha-7b', None, 'x')\nJ.conclude('success', None, 1, 2, 'beta-3b')\n" % (log3,)
        proc = subprocess.run([sys.executable, "-c", PRELUDE + code3], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc3 = proc.returncode
        stderr3 = proc.stderr.strip()
        try:
            with open(log3, "r", encoding="utf-8") as f:
                lines3 = f.readlines()
            if len(lines3) != 1:
                ok3 = False
                desc3 = "count of lines = %d" % len(lines3)
            else:
                rec3 = json.loads(lines3[0])
                ok3 = (rc3 == 0 and rec3.get("status") == "failure" and rec3.get("reason") == "answered by beta-3b instead of alpha-7b")
                desc3 = "status=%s, reason=%s" % (rec3.get("status"), rec3.get("reason"))
        except Exception as e:
            ok3 = False
            desc3 = "exception reading log: %s" % e
        if not ok3 and stderr3:
            desc3 += " | stderr: %s" % stderr3
        results.append(("test 3", ok3, "status=failure, reason=answered by beta-3b instead of alpha-7b", desc3))

        # Test 4
        wall_path = os.path.join(D, "wall")
        with open(wall_path, "w") as f:
            f.write("")
        log_path = os.path.join(D, "wall", "sub", "log.jsonl")
        code4 = "J.arm(%r, 'code', 'alpha-7b', None, 'x')\nJ.conclude('success')\n" % (log_path,)
        proc = subprocess.run([sys.executable, "-c", PRELUDE + code4], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc4 = proc.returncode
        stderr4 = proc.stderr
        ok4 = (rc4 == 0 and "LOG WARNING: " in stderr4 and "Traceback" not in stderr4 and not os.path.exists(log_path))
        desc4 = "rc=%d, LOG WARNING present=%s, Traceback absent=%s, log absent=%s" % (rc4, "LOG WARNING: " in stderr4, "Traceback" not in stderr4, not os.path.exists(log_path))
        if not ok4:
            desc4 += " | stderr: %s" % stderr4
        results.append(("test 4", ok4, "rc=0, LOG WARNING present, Traceback absent, no log file", desc4))

        # Test 5
        sum_path = os.path.join(D, "sum.jsonl")
        with open(sum_path, "w", encoding="utf-8") as f:
            f.write(SUMMARY_LOG)
        proc = subprocess.run([sys.executable, file_path, "--summary", "--log", sum_path], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc5a = proc.returncode
        out5a = proc.stdout.strip()
        expected_out5a = "RECORDS 3 | success 1 | failure 1 | refused 1 | other 0 | unreadable 1"
        ok5a = (rc5a == 0 and out5a == expected_out5a)
        absent_path = os.path.join(D, "absent.jsonl")
        proc = subprocess.run([sys.executable, file_path, "--summary", "--log", absent_path], capture_output=True, text=True, timeout=20, cwd=dir_path)
        rc5b = proc.returncode
        out5b = proc.stdout
        ok5b = (rc5b == 2 and out5b.startswith("NO LOG: "))
        ok5 = ok5a and ok5b
        desc5 = "summary1 rc=%d out='%s'; summary2 rc=%d out='%s'" % (rc5a, out5a, rc5b, out5b)
        results.append(("test 5", ok5, "summary OK, NO LOG OK", desc5))

        all_pass = True
        for name, passed, expected, got in results:
            if passed:
                print("PASS %s: %s" % (name, expected))
            else:
                print("FAIL %s: expected %s, got %s" % (name, expected, got))
                all_pass = False
        return 0 if all_pass else 1
    finally:
        shutil.rmtree(D, ignore_errors=True)

def main():
    args = sys.argv[1:]
    if "--notice" in args:
        sys.stdout.write(NOTICE)
        return 0
    if "--autotest" in args:
        return run_autotest()
    if "--summary" in args:
        path = None
        if "--log" in args:
            idx = args.index("--log")
            if idx + 1 < len(args):
                path = args[idx + 1]
            else:
                path = default_path()
        else:
            path = default_path()
        try:
            with open(path, "r", encoding="utf-8") as f:
                text = f.read()
        except Exception:
            sys.stdout.write("NO LOG: " + path)
            return 2
        records, bad = journal_rules.parse_lines(text)
        s = journal_rules.summarize(records)
        sys.stdout.write("RECORDS " + str(s["records"]) + " | success " + str(s["success"]) + " | failure " + str(s["failure"]) + " | refused " + str(s["refused"]) + " | other " + str(s["other"]) + " | unreadable " + str(bad) + "\n")
        return 0
    sys.stdout.write("usage: journal_log.py --summary [--log FILE] | --notice | --autotest")
    return 2

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "journal_log", sys.argv[1:])
