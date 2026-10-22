import sys, os, json, tempfile, shutil, subprocess
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import usage_rules, ledger_rules, journal_rules, session_share
try:
    import ceilings
except Exception:
    ceilings = None

HOME_DIR = os.environ.get("FRUGALFLOW_HOME")
if HOME_DIR is None:
    HOME_DIR = os.path.join(os.path.expanduser("~"), ".frugalflow")

USAGE = "usage: usage_report.py --session FILE [--threshold X] | --hook [--threshold X] | --delegations [--log FILE] [--models FILE] | --notice | --autotest"

NOTICE = """NAME      usage_report.py - prints a session's token receipt from its transcript, as a hook message too, and sums the delegation log.
READS     --session or the hook's transcript_path; --log and --models, else FRUGALFLOW_HOME or ~/.frugalflow.; preferences.json in that home for the switch (--hook)
WRITES    nothing: the receipt, then WINDOW, CLAUDE and DELEGATED from session_share.py (0), one systemMessage JSON line for a hook (always 0), the delegation report (0); a missing file gives 2.
EXAMPLE   python3 usage_report.py --session ~/.claude/projects/x/session.jsonl
PITFALLS  2026-09-23 the model was asked to announce its own tokens; a receipt printed by a hook cannot be skipped or rounded.
          A hook must never block the assistant: --hook always exits 0.
          2026-10-05 the hook stays quiet when the switch is off or silent: preferences.json in FRUGALFLOW_HOME, else ~/.frugalflow."""

def _read_prefs(home):
    try:
        with open(os.path.join(home, "preferences.json"), encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return None
    if not isinstance(doc, dict):
        return None
    return doc

def _switch(doc):
    if ceilings is None:
        return (True, "active")
    try:
        return ceilings.switch_state(doc if doc is not None else {})
    except Exception:
        return (True, "active")

def load_transcript(path):
    lines = []
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            try:
                lines.append(json.loads(line))
            except ValueError:
                lines.append(None)
    return lines

def run_capture(args, input_text=None):
    proc = subprocess.run([sys.executable, os.path.abspath(__file__)] + args,
                          input=input_text,
                          capture_output=True,
                          text=True,
                          timeout=20)
    lines = proc.stdout.strip().splitlines()
    return proc.returncode, lines

def autotest():
    ok = True
    D = tempfile.mkdtemp()
    try:
        U1 = {"input_tokens": 10, "cache_read_input_tokens": 1000, "output_tokens": 90}
        U2 = {"input_tokens": 5, "cache_read_input_tokens": 2000, "cache_creation_input_tokens": 300, "output_tokens": 30}
        TH = {"type": "thinking", "thinking": "plan the work"}
        TU1 = {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}}
        TU2 = {"type": "tool_use", "name": "Read", "input": {"file_path": "a.py"}}
        TX = {"type": "text", "text": "Done, all green."}
        LINES = [
            {"type": "assistant", "requestId": "r1", "message": {"id": "m1", "usage": U1, "content": [TH]}},
            {"type": "assistant", "requestId": "r1", "message": {"id": "m1", "usage": U1, "content": [TU1]}},
            {"type": "assistant", "requestId": "r1", "message": {"id": "m1", "usage": U1, "content": [TU2]}},
            {"type": "assistant", "requestId": "r2", "message": {"id": "m2", "usage": U2, "content": [TX]}},
            {"type": "assistant", "requestId": "r2", "message": {"id": "m2", "usage": U2, "content": []}},
            {"type": "assistant", "message": {"usage": {"output_tokens": 5}, "content": [{"type": "text", "text": "ok"}]}},
        ]
        RECEIPT = "Tokens: 125 written (conversation 28.0 %, threshold 5.0 %) | context reread 3 000 | 3 turns | 2.0 calls per turn | OVER THRESHOLD"
        LOG = '{"model_asked": "alpha-7b", "model_answered": "alpha-7b", "status": "success", "tokens_in": 20000, "tokens_out": 10000}\n{"model_asked": "beta-pro", "model_answered": "beta-pro", "status": "success", "tokens_in": 1, "tokens_out": 1}\n'
        MODELS = {"models": [{"id": "r", "name": "alpha-7b", "location": "local", "paid": False}, {"id": "c", "name": "beta-pro", "location": "remote", "paid": True}, {"id": "me", "name": "session", "location": "in_session", "paid": True, "price_in": 3, "price_out": 15}]}

        transcript_path = os.path.join(D, "t.jsonl")
        with open(transcript_path, 'w', encoding='utf-8') as f:
            for obj in LINES:
                f.write(json.dumps(obj) + "\n")
            f.write("not json\n")
        log_path = os.path.join(D, "log.jsonl")
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write(LOG)
        models_path = os.path.join(D, "models.json")
        with open(models_path, 'w', encoding='utf-8') as f:
            f.write(json.dumps(MODELS))
        absent_path = os.path.join(D, "absent.jsonl")

        # Test 1
        code, lines = run_capture(["--session", transcript_path])
        expected = [RECEIPT, "OUTPUT conversation 35 | work 66 | thinking 24"]
        if code == 0 and lines[:2] == expected and len(lines) == 5 and lines[2].startswith("WINDOW ") \
                and lines[3].startswith("CLAUDE written 125 ") and lines[4].startswith("DELEGATED 0 calls"):
            print("PASS test 1")
        else:
            print(f"FAIL test 1: want code=0 lines={expected}, got code={code} lines={lines}")
            ok = False

        # Test 2
        input_data = json.dumps({"transcript_path": transcript_path})
        code, lines = run_capture(["--hook"], input_text=input_data)
        expected = [json.dumps({"systemMessage": RECEIPT})]
        if code == 0 and lines == expected:
            print("PASS test 2")
        else:
            print(f"FAIL test 2: want code=0 lines={expected}, got code={code} lines={lines}")
            ok = False

        # Test 3
        test3_ok = True
        details = []
        input_data = "garbage"
        code, lines = run_capture(["--hook"], input_text=input_data)
        expected = [json.dumps({"systemMessage": "Tokens: receipt unavailable (no transcript_path)"})]
        if code != 0 or lines != expected:
            test3_ok = False
            details.append(f"case1 want code=0 lines={expected}, got code={code} lines={lines}")

        input_data = json.dumps({"transcript_path": absent_path})
        code, lines = run_capture(["--hook"], input_text=input_data)
        expected = [json.dumps({"systemMessage": "Tokens: receipt unavailable (transcript unreadable)"})]
        if code != 0 or lines != expected:
            test3_ok = False
            details.append(f"case2 want code=0 lines={expected}, got code={code} lines={lines}")

        if test3_ok:
            print("PASS test 3")
        else:
            print(f"FAIL test 3: {details}")
            ok = False

        # Test 4
        code, lines = run_capture(["--delegations", "--log", log_path, "--models", models_path])
        expected = ["DELEGATIONS 2 | success 2 | free 1 | paid 1 | unknown 0 | escalation rate 50.0 %",
                    "FREE WORK tokens in 20000, out 10000",
                    "COUNTERFACTUAL on the session model: 0.21"]
        if code == 0 and lines == expected:
            print("PASS test 4")
        else:
            print(f"FAIL test 4: want code=0 lines={expected}, got code={code} lines={lines}")
            ok = False

        # Test 5
        test5_ok = True
        details = []
        code, lines = run_capture(["--session", absent_path])
        expected = ["NO TRANSCRIPT: " + absent_path]
        if code != 2 or lines != expected:
            test5_ok = False
            details.append(f"session: want code=2 lines={expected}, got code={code} lines={lines}")

        code, lines = run_capture(["--delegations", "--log", absent_path])
        expected = ["NO LOG: " + absent_path]
        if code != 2 or lines != expected:
            test5_ok = False
            details.append(f"delegations: want code=2 lines={expected}, got code={code} lines={lines}")

        code, lines = run_capture([])
        expected = [USAGE]
        if code != 2 or lines != expected:
            test5_ok = False
            details.append(f"without argument: want code=2 lines={expected}, got code={code} lines={lines}")

        if test5_ok:
            print("PASS test 5")
        else:
            print(f"FAIL test 5: {details}")
            ok = False

        # Test 6
        test6_ok = True
        details = []
        input_data = json.dumps({"transcript_path": transcript_path})
        for label, prefs in [
            ("switch off", '{"switch": {"enabled": false, "mode": "active"}}'),
            ("silent mode", '{"switch": {"enabled": true, "mode": "silent"}}'),
        ]:
            home = os.path.join(D, "home_" + label.replace(" ", "_"))
            os.makedirs(home, exist_ok=True)
            with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
                f.write(prefs)
            env = dict(os.environ)
            env["FRUGALFLOW_HOME"] = home
            proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--hook"],
                                  input=input_data, capture_output=True, text=True,
                                  env=env, timeout=20)
            if proc.returncode != 0 or proc.stdout != "":
                test6_ok = False
                details.append(f"{label}: want code=0 lines=[], got code={proc.returncode} lines={proc.stdout.strip().splitlines()}")
        if test6_ok:
            print("PASS test 6")
        else:
            print(f"FAIL test 6: {details}")
            ok = False

        return 0 if ok else 1
    finally:
        shutil.rmtree(D)

def main():
    args = sys.argv[1:]
    if not args:
        print(USAGE)
        return 2
    if args[0] == "--notice":
        print(NOTICE)
        return 0
    if args[0] == "--autotest":
        return autotest()
    if args[0] == "--session":
        if len(args) < 2:
            print(USAGE)
            return 2
        session_file = args[1]
        threshold = 5.0
        i = 2
        while i < len(args):
            if args[i] == "--threshold":
                if i + 1 >= len(args):
                    print(USAGE)
                    return 2
                try:
                    threshold = float(args[i + 1])
                except ValueError:
                    print(USAGE)
                    return 2
                i += 2
            else:
                print(USAGE)
                return 2
        try:
            objs = load_transcript(session_file)
        except OSError:
            print("NO TRANSCRIPT: " + session_file)
            return 2
        msgs = usage_rules.group(objs)
        t = usage_rules.totals(msgs)
        print(usage_rules.receipt(t, threshold))
        print(f"OUTPUT conversation {t['conversation']} | work {t['work']} | thinking {t['thinking']}")
        for line in session_share.session_lines(objs, msgs, t, os.environ, session_share.local_offset()):
            print(line)
        return 0
    if args[0] == "--hook":
        threshold = 5.0
        i = 1
        while i < len(args):
            if args[i] == "--threshold":
                if i + 1 < len(args):
                    try:
                        threshold = float(args[i + 1])
                    except ValueError:
                        pass
            i += 1
        enabled, mode = _switch(_read_prefs(HOME_DIR))
        if not enabled or mode == "silent":
            return 0
        data = sys.stdin.read()
        msg = "Tokens: receipt unavailable (no transcript_path)"
        try:
            obj = json.loads(data)
        except Exception:
            obj = None
        if isinstance(obj, dict):
            tp = obj.get("transcript_path")
            if isinstance(tp, str) and tp != "":
                try:
                    t = usage_rules.totals(usage_rules.group(load_transcript(tp)))
                    msg = usage_rules.receipt(t, threshold)
                except OSError:
                    msg = "Tokens: receipt unavailable (transcript unreadable)"
        print(json.dumps({"systemMessage": msg}))
        return 0
    if args[0] == "--delegations":
        log_path = os.path.join(HOME_DIR, "delegations.jsonl")
        models_path = os.path.join(HOME_DIR, "models.json")
        i = 1
        while i < len(args):
            if args[i] == "--log":
                if i + 1 >= len(args):
                    print(USAGE)
                    return 2
                log_path = args[i + 1]
                i += 2
            elif args[i] == "--models":
                if i + 1 >= len(args):
                    print(USAGE)
                    return 2
                models_path = args[i + 1]
                i += 2
            else:
                print(USAGE)
                return 2
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                txt = f.read()
        except (OSError, UnicodeDecodeError):
            print("NO LOG: " + log_path)
            return 2
        records, _ = journal_rules.parse_lines(txt)
        try:
            with open(models_path, 'r', encoding='utf-8') as f:
                doc = json.load(f)
        except (OSError, ValueError):
            doc = {}
        s = ledger_rules.summarize(records, ledger_rules.model_index(doc))
        cost = ledger_rules.counterfactual(s, *ledger_rules.session_prices(doc))
        for line in ledger_rules.report(s, cost):
            print(line)
        return 0
    else:
        print(USAGE)
        return 2

if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "usage_report", sys.argv[1:])
