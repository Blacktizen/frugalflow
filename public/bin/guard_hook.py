#!/usr/bin/env python3
import json
import os
import sys
import subprocess
import shutil
import tempfile
import datetime
import hashlib

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import guard_rules, guard_checks, ceilings
    IMPORT_ERROR = None
except Exception as _e:
    IMPORT_ERROR = _e

try:
    import journal_guard
except Exception:
    journal_guard = None

HOME = os.environ.get("FRUGALFLOW_HOME") or os.path.expanduser("~/.frugalflow")

NOTICE = (
    "NAME      guard_hook.py - the PreToolUse hook: reads the tool call, asks guard_rules for the decision, logs it and prints the refusal.\n"
    "READS     stdin (the tool call); FRUGALFLOW_HOME/guard.json, else ~/.frugalflow/guard.json; FRUGALFLOW_HOME/preferences.json (the switch); the delegation logs it names; the size of the files its entry checks ask about.\n"
    "WRITES    one JSON line per logged decision to the audit log it names; each refusal, replayable, to blocks/guard.jsonl; the refusal on stdout, and in observe mode one short systemMessage turn line when display.turn_line is on. Always exits 0.\n"
    "EXAMPLE   echo '{\"tool_name\": \"Read\", \"tool_input\": {}}' | python3 guard_hook.py --hook\n"
    "PITFALLS  2026-09-25 the old hook let the call through when its input was unreadable or a module was missing, and never logged its shell refusals.\n"
    "          Every doubt now refuses with a \"To fix:\" line, and shell refusals are logged like the others.\n"
    "          2026-10-03 the switch lived only in the assistant's memory, which never bites; the hook now reads preferences.json on every call so off and observe are real.\n"
    "          2026-10-04 an observed refusal in observe mode now prints one short systemMessage line when display.turn_line is on; it never says deny.\n"
)


TURN_PREFIX = "FrugalFlow \u00b7 observe: "


def deny_json(reason):
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }
        },
        ensure_ascii=False,
    )


def load_settings(home):
    path = os.path.join(home, "guard.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise ValueError("guard.json unreadable or invalid JSON")
    if not isinstance(data, dict):
        raise ValueError("guard.json is not a dict")
    for key in ("code_extensions", "delegation_logs", "audit_log"):
        if key not in data:
            raise ValueError(f"guard.json missing key: {key}")
    return data


def resolve(home, path):
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(home, p)
    return p


def load_records(home, settings):
    records = []
    for p in settings["delegation_logs"]:
        q = resolve(home, p)
        if not os.path.exists(q):
            continue
        try:
            with open(q, "r", encoding="utf-8") as f:
                text = f.read()
            records.extend(guard_rules.receipt_rules.parse_lines(text))
        except Exception:
            return None
    return records


def write_audit(home, settings, tool, res):
    try:
        path = resolve(home, settings["audit_log"])
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        line = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "tool": tool,
            "decision": res["decision"],
            "audit": res["audit"],
            "targets": res["targets"][:5],
            "reason": res["reason"][:300],
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(line, ensure_ascii=False) + "\n")
    except Exception:
        print("audit log cannot be written", file=sys.stderr)


def read_switch(home):
    path = os.path.join(home, "preferences.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except Exception:
        return (True, "active")
    if not isinstance(doc, dict):
        return (True, "active")
    switch = doc.get("switch")
    if switch is None:
        return ceilings.switch_state(doc)
    if not isinstance(switch, dict):
        return (True, "active")
    if "enabled" not in switch or not isinstance(switch["enabled"], bool):
        return (True, "active")
    if "mode" not in switch or switch["mode"] not in ceilings.MODES:
        return (True, "active")
    return (switch["enabled"], switch["mode"])


def turn_line_enabled(home):
    path = os.path.join(home, "preferences.json")
    try:
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        if not isinstance(doc, dict):
            return True
        return bool(ceilings.display_state(doc).get("turn_line", True))
    except Exception:
        return True


def turn_message(reason):
    lines = str(reason).splitlines()
    first = lines[0] if lines else ""
    budget = 200 - len(TURN_PREFIX)
    return TURN_PREFIX + first[:budget]


def run_hook(stdin_text):
    if IMPORT_ERROR is not None:
        return (
            deny_json(
                f"Guard unavailable: {IMPORT_ERROR}. To fix: put guard_rules.py, guard_checks.py "
                "and their neighbour modules back beside guard_hook.py."
            ),
            False,
        )

    try:
        payload = json.loads(stdin_text)
    except Exception:
        payload = None
    if not isinstance(payload, dict):
        return (
            deny_json(
                "Guard refused: the tool call cannot be read. "
                "To fix: check the hook command in the assistant settings."
            ),
            False,
        )

    home = HOME
    try:
        settings = load_settings(home)
    except ValueError:
        return (
            deny_json(
                f"Guard refused: the settings file {os.path.join(home, 'guard.json')} "
                "is missing or incomplete. To fix: create it with code_extensions, "
                "delegation_logs and audit_log."
            ),
            False,
        )

    tool = payload.get("tool_name", "")
    inp = payload.get("tool_input")
    if not isinstance(inp, dict):
        inp = {}

    if os.environ.get("FRUGALFLOW_GUARD") == "0" or settings.get("active", True) is False:
        res = guard_rules.result("allow", "disarmed", [], "")
        write_audit(home, settings, tool, res)
        return ("", True)

    enabled, mode = read_switch(home)

    records = load_records(home, settings)

    observed_reason = None
    if enabled is False:
        res = guard_rules.result("allow", "off", [], "")
    else:
        try:
            res = guard_rules.decide(tool, inp, settings, records, guard_checks.build(settings, records, payload.get("cwd")))
        except Exception as e:
            res = guard_rules.result(
                "deny",
                "guard_failed",
                [],
                f"Guard refused: the decision failed ({e}). "
                "To fix: report this command; nothing passes while the guard fails.",
            )

        if mode == "observe" and res["decision"] == "deny":
            observed_reason = res["reason"]
            res = guard_rules.result("allow", "observed:" + str(res["audit"]), res["targets"], res["reason"])

    if res["decision"] != "deny" and journal_guard is not None:
        try:
            cwd = payload.get("cwd")
            if not (cwd is not None and isinstance(cwd, str) and cwd):
                cwd = os.getcwd()
            protected = journal_guard.protected_paths(home, settings)
            touched_paths = journal_guard.touched(tool, inp, protected, cwd)
        except Exception:
            touched_paths = []
        if touched_paths:
            res = guard_rules.result(
                "deny",
                "journal",
                touched_paths,
                "Guard refused: this call writes, removes, moves or links the guard's own logs ("
                + ", ".join(touched_paths)
                + "). To fix: never touch these files; read them only.",
            )

    replaying = os.environ.get("FRUGALFLOW_REPLAY") == "1"
    audit_written = False
    if res["audit"] is not None and not replaying:
        write_audit(home, settings, tool, res)
        audit_written = True

    if res["decision"] == "deny":
        try:
            import block_log
            spec = {"argv": [sys.executable, os.path.abspath(__file__), "--hook"], "stdin": stdin_text, "env": {"FRUGALFLOW_REPLAY": "1"}, "blocked_if": {"stdout_contains": '"deny"'}}
            ver = hashlib.sha256(open(guard_rules.__file__, "rb").read()).hexdigest()[:12]
            if not replaying: block_log.record_block("guard", res["audit"] or "deny", {"tool_name": tool, "tool_input": inp}, res["reason"], ver, spec, home=home)
        except Exception:
            print("block log cannot be written", file=sys.stderr)
        return (deny_json(res["reason"]), audit_written)
    if observed_reason is not None and turn_line_enabled(home):
        return (json.dumps({"systemMessage": turn_message(observed_reason)}, ensure_ascii=False), audit_written)
    return ("", audit_written)


# ---------------------------------------------------------------------------
# Auto-test fixtures (exact literals from the specification)
# ---------------------------------------------------------------------------
BIG = "a\nb\nc\nd\n"
CODE60 = "\n".join("x%d" % i for i in range(60)) + "\n"
SETTINGS = {
    "code_extensions": [".py"],
    "line_threshold": 3,
    "receipt_minutes": 60,
    "delegate_tools": [],
    "fix_hint": "delegate it.",
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}


def RECEIPT():
    return {
        "time": datetime.datetime.now().astimezone().isoformat(),
        "status": "success",
        "model_answered": "m",
        "target": "/w/a.py",
        "sha256": hashlib.sha256(BIG.encode("utf-8")).hexdigest(),
    }


def CALL(tool, inp):
    return json.dumps({"tool_name": tool, "tool_input": inp})


def _RUN(home, stdin_text, env_extra=None, script=None):
    env = dict(os.environ)
    env["FRUGALFLOW_HOME"] = home
    env.pop("FRUGALFLOW_GUARD", None)
    if env_extra:
        env.update(env_extra)
    script_path = script if script else os.path.abspath(__file__)
    r = subprocess.run(
        [sys.executable, script_path, "--hook"],
        input=stdin_text,
        capture_output=True,
        text=True,
        env=env,
    )
    return (r.returncode, r.stdout)


def _AUDIT(home):
    path = os.path.join(home, "audit.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                out.append(json.loads(line)["audit"])
    return out


def _SETUP(home, logs_text):
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(SETTINGS, f)
    with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
        f.write(logs_text)


def _PREFS(enabled, mode):
    return {"schema_version": "1",
            "verbosity": {"final_answer_words": 150, "step_message_words": 35},
            "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 60000},
            "splitting": {"max_proofs_per_task": 5, "max_brief_lines": 140},
            "grouping": {"independent_calls_same_turn": True},
            "switch": {"enabled": enabled, "mode": mode}}


def _write_prefs(home, prefs):
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f)


# ---------------------------------------------------------------------------
# Auto-test
# ---------------------------------------------------------------------------
def _autotest():
    results = []

    # --- Proof 1 ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/b.py", "content": BIG}))
        expected = "deny, To fix:, audit=no_receipt"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                pd = d["hookSpecificOutput"]["permissionDecision"]
                reason = d["hookSpecificOutput"]["permissionDecisionReason"]
                if pd != "deny" or "To fix:" not in reason:
                    ok = False
                    got = f"decision={pd}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        audit = _AUDIT(h)
        if audit != ["no_receipt"]:
            ok = False
            got = f"audit={audit}"
        results.append((1, ok, expected, got))

    # --- Proof 2 ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        code, stdout = _RUN(h, CALL("Bash", {"command": "tee /w/b.py"}))
        expected = "deny, audit=shell_write; then allow, stdout='', audit unchanged"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                if d["hookSpecificOutput"]["permissionDecision"] != "deny":
                    ok = False
                    got = f"decision={d['hookSpecificOutput']['permissionDecision']}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        audit = _AUDIT(h)
        if audit != ["shell_write"]:
            ok = False
            got = f"audit={audit}"

        code2, stdout2 = _RUN(h, CALL("Bash", {"command": "ls"}))
        if code2 != 0:
            ok = False
            got = f"code2={code2}"
        if stdout2 != "":
            ok = False
            got = f"stdout2={stdout2!r}"
        audit2 = _AUDIT(h)
        if audit2 != ["shell_write"]:
            ok = False
            got = f"audit2={audit2}"
        results.append((2, ok, expected, got))

    # --- Proof 3 ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, json.dumps(RECEIPT()) + "\n")
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/a.py", "content": BIG}))
        expected = "stdout='', audit=receipt_match; dir-as-log: deny, audit=log_unreadable"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        if stdout != "":
            ok = False
            got = f"stdout={stdout!r}"
        audit = _AUDIT(h)
        if audit != ["receipt_match"]:
            ok = False
            got = f"audit={audit}"

        with tempfile.TemporaryDirectory() as h2:
            _SETUP(h2, "")
            os.remove(os.path.join(h2, "delegations.jsonl"))
            os.mkdir(os.path.join(h2, "delegations.jsonl"))
            code, stdout = _RUN(h2, CALL("Write", {"file_path": "/w/a.py", "content": BIG}))
            if code != 0:
                ok = False
                got = f"code_h2={code}"
            else:
                try:
                    d = json.loads(stdout)
                    if d["hookSpecificOutput"]["permissionDecision"] != "deny":
                        ok = False
                        got = f"decision_h2={d['hookSpecificOutput']['permissionDecision']}"
                except Exception as e:
                    ok = False
                    got = f"parse_h2: {e}"
            audit2 = _AUDIT(h2)
            if audit2 != ["log_unreadable"]:
                ok = False
                got = f"audit_h2={audit2}"
        results.append((3, ok, expected, got))

    # --- Proof 4 ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        code, stdout = _RUN(h, "not json")
        expected = "bad-json deny; no-guard.json deny; disarmed allow+audit"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                reason = d["hookSpecificOutput"]["permissionDecisionReason"]
                if not reason.startswith("Guard refused: the tool call cannot be read."):
                    ok = False
                    got = f"reason={reason[:60]}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"

        with tempfile.TemporaryDirectory() as h3:
            code, stdout = _RUN(h3, CALL("Read", {}))
            if code != 0:
                ok = False
                got = f"code_h3={code}"
            else:
                try:
                    d = json.loads(stdout)
                    reason = d["hookSpecificOutput"]["permissionDecisionReason"]
                    if "guard.json" not in reason:
                        ok = False
                        got = f"reason_h3={reason[:60]}"
                except Exception as e:
                    ok = False
                    got = f"parse_h3: {e}"

        _SETUP(h, "")
        code, stdout = _RUN(
            h,
            CALL("Write", {"file_path": "/w/b.py", "content": BIG}),
            env_extra={"FRUGALFLOW_GUARD": "0"},
        )
        if code != 0:
            ok = False
            got = f"code_disarm={code}"
        if stdout != "":
            ok = False
            got = f"stdout_disarm={stdout!r}"
        audit = _AUDIT(h)
        if not audit or audit[-1] != "disarmed":
            ok = False
            got = f"audit_disarm={audit}"
        results.append((4, ok, expected, got))

    # --- Proof 5 ---
    with tempfile.TemporaryDirectory() as d:
        with tempfile.TemporaryDirectory() as h:
            shutil.copy(os.path.abspath(__file__), os.path.join(d, "guard_hook.py"))
            _SETUP(h, "")
            script_path = os.path.join(d, "guard_hook.py")

            code, stdout = _RUN(h, CALL("Read", {}), script=script_path)
            expected = "Guard unavailable; --notice ok; no-arg usage exit 2"
            got = "ok"
            ok = True
            if code != 0:
                ok = False
                got = f"code={code}"
            else:
                try:
                    dd = json.loads(stdout)
                    reason = dd["hookSpecificOutput"]["permissionDecisionReason"]
                    if not reason.startswith("Guard unavailable:"):
                        ok = False
                        got = f"reason={reason[:60]}"
                except Exception as e:
                    ok = False
                    got = f"parse: {e}"

            env = dict(os.environ)
            env["FRUGALFLOW_HOME"] = h
            r = subprocess.run(
                [sys.executable, script_path, "--notice"],
                capture_output=True, text=True, env=env,
            )
            if r.returncode != 0:
                ok = False
                got = f"notice_code={r.returncode}"
            if not r.stdout.startswith("NAME      guard_hook.py"):
                ok = False
                got = f"notice_start={r.stdout[:40]!r}"

            r = subprocess.run(
                [sys.executable, script_path],
                capture_output=True, text=True, env=env,
            )
            if r.returncode != 2:
                ok = False
                got = f"usage_code={r.returncode}"
            if r.stdout != "usage: guard_hook.py --hook | --notice | --autotest\n":
                ok = False
                got = f"usage_out={r.stdout!r}"
            results.append((5, ok, expected, got))

    # --- Proof 6 ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        code, stdout = _RUN(h, CALL("Bash", {"command": f"echo x >> {h}/delegations.jsonl"}))
        expected = "write to delegations.jsonl denied; wc -l of it allowed"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                reason = d["hookSpecificOutput"]["permissionDecisionReason"]
                if d["hookSpecificOutput"]["permissionDecision"] != "deny" or "guard's own logs" not in reason:
                    ok = False
                    got = f"decision={d['hookSpecificOutput']['permissionDecision']} reason={reason[:60]}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"

        code2, stdout2 = _RUN(h, CALL("Bash", {"command": f"wc -l {h}/delegations.jsonl"}))
        if code2 != 0:
            ok = False
            got = f"code2={code2}"
        if stdout2 != "":
            ok = False
            got = f"stdout2={stdout2!r}"
        results.append((6, ok, expected, got))

    # --- Proof 7: switch off lets the write pass and logs audit=off ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        _write_prefs(h, _PREFS(False, "active"))
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/b.py", "content": BIG}))
        expected = "off: stdout='', audit=off"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        if stdout != "":
            ok = False
            got = f"stdout={stdout!r}"
        audit = _AUDIT(h)
        if not audit or audit[-1] != "off":
            ok = False
            got = f"audit={audit}"
        results.append((7, ok, expected, got))

    # --- Proof 8: observe converts a deny into a counted allow and prints the turn line ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        _write_prefs(h, _PREFS(True, "observe"))
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/b.py", "content": BIG}))
        expected = "observe: one systemMessage turn line, audit=observed:no_receipt"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                if not str(d.get("systemMessage", "")).startswith(TURN_PREFIX):
                    ok = False
                    got = f"stdout={stdout!r}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        audit = _AUDIT(h)
        if not audit or audit[-1] != "observed:no_receipt":
            ok = False
            got = f"audit={audit}"
        results.append((8, ok, expected, got))

    # --- Proof 9: the journal stays protected even when off ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        _write_prefs(h, _PREFS(False, "active"))
        code, stdout = _RUN(h, CALL("Bash", {"command": f"echo x >> {h}/delegations.jsonl"}))
        expected = "off still denies a write to the guard's own logs"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                reason = d["hookSpecificOutput"]["permissionDecisionReason"]
                if d["hookSpecificOutput"]["permissionDecision"] != "deny" or "guard's own logs" not in reason:
                    ok = False
                    got = f"decision={d['hookSpecificOutput']['permissionDecision']} reason={reason[:60]}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        results.append((9, ok, expected, got))

    # --- Proof 10: no preferences.json means the barrier stays active ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/b.py", "content": BIG}))
        expected = "preferences absent: deny, audit=no_receipt"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                d = json.loads(stdout)
                if d["hookSpecificOutput"]["permissionDecision"] != "deny":
                    ok = False
                    got = f"decision={d['hookSpecificOutput']['permissionDecision']}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        audit = _AUDIT(h)
        if not audit or audit[-1] != "no_receipt":
            ok = False
            got = f"audit={audit}"
        results.append((10, ok, expected, got))

    # --- Proof 11: observe turns a 60-line code write into one systemMessage turn line ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        _write_prefs(h, _PREFS(True, "observe"))
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/big.py", "content": CODE60}))
        expected = "observe: one systemMessage line starting with the observe prefix"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        else:
            try:
                lines = [l for l in stdout.splitlines() if l.strip()]
                if len(lines) != 1:
                    ok = False
                    got = f"lines={len(lines)} stdout={stdout!r}"
                else:
                    d = json.loads(lines[0])
                    msg = str(d.get("systemMessage", ""))
                    if not msg.startswith(TURN_PREFIX) or len(msg) > 200:
                        ok = False
                        got = f"msg={msg[:80]!r} len={len(msg)}"
            except Exception as e:
                ok = False
                got = f"parse: {e}"
        results.append((11, ok, expected, got))

    # --- Proof 12: the same observed write stays silent when display.turn_line is off ---
    with tempfile.TemporaryDirectory() as h:
        _SETUP(h, "")
        prefs = _PREFS(True, "observe")
        prefs["display"] = {"statusline": True, "turn_line": False, "summary": True}
        _write_prefs(h, prefs)
        code, stdout = _RUN(h, CALL("Write", {"file_path": "/w/big.py", "content": CODE60}))
        expected = "turn_line off: stdout='', audit=observed:no_receipt"
        got = "ok"
        ok = True
        if code != 0:
            ok = False
            got = f"code={code}"
        if stdout != "":
            ok = False
            got = f"stdout={stdout!r}"
        audit = _AUDIT(h)
        if not audit or audit[-1] != "observed:no_receipt":
            ok = False
            got = f"audit={audit}"
        results.append((12, ok, expected, got))

    all_pass = True
    for num, passed, expected, got in results:
        if passed:
            print(f"PASS proof {num}: expected {expected} | got ok")
        else:
            print(f"FAIL proof {num}: expected {expected} | got {got}")
            all_pass = False

    return all_pass


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--hook":
        _stdin = sys.stdin.read()
        _output, _ = run_hook(_stdin)
        if _output:
            print(_output)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        _ok = _autotest()
        sys.exit(0 if _ok else 1)
    else:
        print("usage: guard_hook.py --hook | --notice | --autotest")
        sys.exit(2)
