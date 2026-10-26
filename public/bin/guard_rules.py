import os
import sys
import subprocess
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_rules
import receipt_rules
from example_defaults import setting

LOG_UNREADABLE = "Code write refused: the delegation log cannot be read, so no receipt can be checked. To fix: repair the delegation log file named in the settings."


def result(decision, audit, targets, reason):
    return {"decision": decision, "audit": audit, "targets": list(targets), "reason": reason}


def is_code(path, config):
    return isinstance(path, str) and path and os.path.splitext(path)[1].lower() in config.get("code_extensions", [])


def decide(tool_name, tool_input, config, records, checks=(), judge=None, now=None):
    if judge is None:
        judge = shell_rules.judge_command
    if now is None:
        now = datetime.now().astimezone()
    minutes = setting(config, "guard", "receipt_minutes")
    hint = config.get("fix_hint", "")

    for name, fn in checks:
        try:
            refused, reason, targets = fn(tool_name, tool_input, config)
        except Exception as e:
            return result("deny", "check_failed:" + name, [], f"{name} failed: {e}. To fix: repair or remove this check in the settings; nothing passes while it fails.")
        if refused:
            return result("deny", "refused:" + name, targets, reason)

    if tool_name == "Bash":
        cmd = tool_input.get("command")
        if not isinstance(cmd, str):
            return result("deny", "bad_input", [], "Command refused: the command is not text. To fix: send the command as text.")
        try:
            r = judge(cmd, {"code_extensions": config.get("code_extensions", []), "delegate_tools": config.get("delegate_tools", [])})
        except Exception as e:
            return result("deny", "shell_failed", [], f"Command refused: the shell analysis failed ({e}). To fix: split the command into simpler commands.")
        if r["verdict"] == "free":
            return result("allow", None, [], "")
        if records is None:
            return result("deny", "log_unreadable", r["targets"], LOG_UNREADABLE)
        if r["verdict"] == "unknown":
            return result("deny", "shell_unknown", r["targets"], f"Shell write of code refused: the command writes code and its target cannot be read. To fix: {hint}")
        missing = [t for t in r["targets"] if receipt_rules.find_receipt(records, t, now, minutes) is None]
        if not missing:
            return result("allow", "shell_write_with_receipt", r["targets"], "")
        return result("deny", "shell_write", r["targets"], f"Shell write of code refused: no delegation receipt for {missing[0]}. To fix: {hint}")

    if tool_name in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        if tool_name == "Write":
            path = tool_input.get("file_path")
            content = tool_input.get("content")
            fragment = False
        elif tool_name == "Edit":
            path = tool_input.get("file_path")
            content = tool_input.get("new_string")
            fragment = True
        elif tool_name == "MultiEdit":
            path = tool_input.get("file_path")
            content = "\n".join(e.get("new_string", "") for e in tool_input.get("edits", []))
            fragment = True
        else:
            path = tool_input.get("notebook_path")
            content = tool_input.get("new_source")
            fragment = True

        if not isinstance(path, str):
            path = ""
        if not isinstance(content, str):
            content = ""

        lines = len(content.splitlines())

        if not is_code(path, config):
            return result("allow", None, [path], "")
        if lines <= setting(config, "guard", "line_threshold"):
            return result("allow", None, [path], "")
        if records is None:
            return result("deny", "log_unreadable", [path], LOG_UNREADABLE)

        v = receipt_rules.content_verdict(records, path, content, now, minutes, fragment)
        if v == "match":
            return result("allow", "receipt_match", [path], "")
        elif v == "declared_edit":
            return result("allow", "declared_edit", [path], "")
        elif v == "no_receipt":
            return result("deny", "no_receipt", [path], f"Code write refused: {lines} lines in {path}, and no recent successful delegation for this file. To fix: {hint}")
        elif v == "no_fingerprint":
            return result("deny", "no_fingerprint", [path], f"Code write refused: the receipt for {path} has no fingerprint. To fix: delegate again with an output file, which records the fingerprint.")
        else:
            return result("deny", "divergent", [path], f"Code write refused: the content differs from what was delegated for {path}. To fix: write the delegated file as it is, or declare the edit in the delegation log (kind edit, target, reason).")

    return result("allow", None, [], "")


def _cli():
        if len(sys.argv) > 1 and sys.argv[1] == "--notice":
            print('NAME      guard_rules.py - decides whether a tool call of the assistant passes: a code file of more than a few lines must come from a recent, successful delegation.')
            print('READS     nothing: pure module; the caller passes the tool call, the settings, the decoded delegation log (None when unreadable) and the checks to run first.')
            print('WRITES    nothing: decide() returns decision (allow or deny), audit (the log label, or None), targets and reason; every refusal of the guard itself ends with "To fix:".')
            print('EXAMPLE   python3 guard_rules.py --notice')
            print('PITFALLS  2026-09-25 a naive guard let everything through when a check crashed, when its shell analysis was missing or when the log was unreadable: it failed open.')
            print('          A crashed check, a failed analysis and an unreadable log now refuse, and say how to fix it.')
            print('          2026-09-27 an unreadable shell target passed for 60 minutes after any delegation; it is now refused, a receipt covers only its exact file.')
            sys.exit(0)
        elif len(sys.argv) > 1 and sys.argv[1] == "--autotest":
            from datetime import datetime as _dt, timezone as _tz, timedelta as _td

            NOW = _dt(2026, 9, 25, 12, 0, tzinfo=_tz.utc)
            CFG = {"code_extensions": [".py"], "line_threshold": 3, "receipt_minutes": 60, "delegate_tools": ["deleg"], "fix_hint": "delegate it."}
            BIG = "a\nb\nc\nd\n"
            REC = {"time": (NOW - _td(minutes=3)).isoformat(), "status": "success", "model_answered": "m", "target": "/w/a.py", "sha256": receipt_rules.fingerprint(BIG)}
            EDIT = {"kind": "edit", "target": "/w/a.py", "time": (NOW - _td(minutes=5)).isoformat(), "reason": "r"}

            def D(tool, inp, records="default", checks=(), judge=None):
                if records == "default":
                    records = [REC]
                return decide(tool, inp, CFG, records, checks, judge, NOW)

            def K(r):
                return (r["decision"], r["audit"])

            def J_UNKNOWN(cmd, cfg):
                return {"verdict": "unknown", "targets": ["<unknown>"], "reason": "x"}

            def J_CRASH(cmd, cfg):
                raise ValueError("boom")

            def C_REFUSE(tool, inp, cfg):
                return (True, "no.", ["t"])

            def C_CRASH(tool, inp, cfg):
                raise RuntimeError("down")

            def C_PASS(tool, inp, cfg):
                return (False, "", [])

            fails = 0

            # Test 1
            try:
                a = K(D("Write", {"file_path": "/w/a.py", "content": BIG}))
                b = K(D("Write", {"file_path": "/w/a.py", "content": "w\nx\ny\nz\n"}))
                c = K(D("Write", {"file_path": "/w/b.py", "content": BIG}))
                d = K(D("Write", {"file_path": "/w/b.py", "content": "a\n"}))
                e = K(D("Write", {"file_path": "/w/b.md", "content": BIG}))
                f = K(D("Write", {"file_path": "/w/b.py", "content": BIG}, records=None))
                ok = (a == ("allow", "receipt_match") and b == ("deny", "divergent") and c == ("deny", "no_receipt") and d == ("allow", None) and e == ("allow", None) and f == ("deny", "log_unreadable"))
                if ok:
                    print("PASS 1")
                else:
                    print(f"FAIL 1 expected=((('allow','receipt_match'),('deny','divergent'),('deny','no_receipt'),('allow',None),('allow',None),('deny','log_unreadable'))) got=({a},{b},{c},{d},{e},{f})")
                    fails += 1
            except Exception as ex:
                print(f"FAIL 1 exception: {ex}")
                fails += 1

            # Test 2
            try:
                a = K(D("Edit", {"file_path": "/w/a.py", "new_string": BIG}))
                b = K(D("Edit", {"file_path": "/w/a.py", "new_string": BIG}, records=[REC, EDIT]))
                c = K(D("Write", {"file_path": "/w/a.py", "content": BIG}, records=[dict(REC, sha256=None)]))
                d = K(D("MultiEdit", {"file_path": "/w/b.py", "edits": [{"new_string": "a\nb\n"}, {"new_string": "c\nd\n"}]}))
                ok = (a == ("deny", "divergent") and b == ("allow", "declared_edit") and c == ("deny", "no_fingerprint") and d == ("deny", "no_receipt"))
                if ok:
                    print("PASS 2")
                else:
                    print(f"FAIL 2 expected=((('deny','divergent'),('allow','declared_edit'),('deny','no_fingerprint'),('deny','no_receipt'))) got=({a},{b},{c},{d})")
                    fails += 1
            except Exception as ex:
                print(f"FAIL 2 exception: {ex}")
                fails += 1

            # Test 3
            try:
                a = K(D("Bash", {"command": "ls"}))
                b = K(D("Bash", {"command": "cat > /w/a.py <<EOF\nx\nEOF"}))
                c = K(D("Bash", {"command": "tee /w/b.py"}))
                d = "/w/b.py" in D("Bash", {"command": "tee /w/b.py"})["reason"]
                e = K(D("Bash", {"command": "x"}, judge=J_UNKNOWN))
                f = K(D("Bash", {"command": "x"}, records=[], judge=J_UNKNOWN))
                g = K(D("Bash", {"command": "x"}, judge=J_CRASH))
                h = K(D("Bash", {"command": 5}))
                i = K(D("Bash", {"command": "tee /w/b.py"}, records=None))
                ok = (a == ("allow", None) and b == ("allow", "shell_write_with_receipt") and c == ("deny", "shell_write") and d and e == ("deny", "shell_unknown") and f == ("deny", "shell_unknown") and g == ("deny", "shell_failed") and h == ("deny", "bad_input") and i == ("deny", "log_unreadable"))
                if ok:
                    print("PASS 3")
                else:
                    print(f"FAIL 3 expected=((('allow',None),('allow','shell_write_with_receipt'),('deny','shell_write'),True,('deny','shell_unknown'),('deny','shell_unknown'),('deny','shell_failed'),('deny','bad_input'),('deny','log_unreadable'))) got=({a},{b},{c},{d},{e},{f},{g},{h},{i})")
                    fails += 1
            except Exception as ex:
                print(f"FAIL 3 exception: {ex}")
                fails += 1

            # Test 4
            try:
                a = D("Read", {}, checks=[("c1", C_REFUSE)])
                b = K(D("Read", {}, checks=[("c0", C_PASS), ("c2", C_CRASH)]))
                c = "To fix:" in D("Read", {}, checks=[("c2", C_CRASH)])["reason"]
                d = K(D("Read", {}, checks=[("c0", C_PASS)]))
                e = "To fix:" in D("Write", {"file_path": "/w/b.py", "content": BIG})["reason"]
                f = "To fix:" in D("Bash", {"command": "tee /w/b.py"})["reason"]
                ok = (a == {"decision": "deny", "audit": "refused:c1", "targets": ["t"], "reason": "no."} and b == ("deny", "check_failed:c2") and c and d == ("allow", None) and e and f)
                if ok:
                    print("PASS 4")
                else:
                    print(f"FAIL 4 expected=((dict deny refused:c1, ('deny','check_failed:c2'), True, ('allow',None), True, True)) got=({a}, {b}, {c}, {d}, {e}, {f})")
                    fails += 1
            except Exception as ex:
                print(f"FAIL 4 exception: {ex}")
                fails += 1

            # Test 5
            try:
                p1 = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
                p2 = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
                ok = (p1.returncode == 0 and p1.stdout.startswith("NAME      guard_rules.py") and p2.returncode == 2 and p2.stdout == "usage: guard_rules.py --notice | --autotest\n")
                if ok:
                    print("PASS 5")
                else:
                    print(f"FAIL 5 expected=(rc0 starts NAME, rc2 usage) got=(rc{p1.returncode} {p1.stdout[:50]!r}, rc{p2.returncode} {p2.stdout!r})")
                    fails += 1
            except Exception as ex:
                print(f"FAIL 5 exception: {ex}")
                fails += 1

            sys.exit(1 if fails else 0)
        else:
            print("usage: guard_rules.py --notice | --autotest")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "guard_rules", sys.argv[1:])
