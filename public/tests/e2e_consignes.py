#!/usr/bin/env python3
# e2e_consignes.py - end-to-end test: refusal texts name only what exists (C14), and the reading gate attests only a refusal the guard renders (C17)
# FF_ROOT=<tree> points the test at another tree (the base, for the red run); default: the tree this file belongs to.

import datetime
import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.environ.get("FF_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
sys.path.insert(0, BIN)

SETTINGS = {
    "code_extensions": [".py"],
    "line_threshold": 3,
    "receipt_minutes": 60,
    "quarantine_minutes": 60,
    "read_waiver_minutes": 10,
    "delegate_tools": [],
    "fix_hint": "delegate it.",
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}

ATTEST = ".reading.json"
SCHEMA = "# S\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n"
OVERVIEW = "# O\n⛔⛔ never push to main\nplain\n"
TODO = "# T\n- [ ] ⭐⭐ fix the parser\n"
PAGE = "# notes\nthe first write into the vault\n"


def prefs(enabled, mode):
    return {"schema_version": "1",
            "verbosity": {"final_answer_words": 120, "step_message_words": 30},
            "ceilings": {"max_trust": "trusted_third_party", "max_tries": 3, "max_output_tokens": 50000},
            "splitting": {"max_proofs_per_task": 4, "max_brief_lines": 100},
            "grouping": {"independent_calls_same_turn": True},
            "switch": {"enabled": enabled, "mode": mode}}


def ENV(home):
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY", "FRUGALFLOW_BRIEF_RULES"):
        env.pop(key, None)
    env["FRUGALFLOW_HOME"] = home
    env["HOME"] = home
    return env


def HOOK(home, tool, inp, cwd):
    payload = json.dumps({"tool_name": tool, "tool_input": inp, "cwd": cwd})
    try:
        r = subprocess.run([sys.executable, os.path.join(BIN, "guard_hook.py"), "--hook"],
                           input=payload, capture_output=True, text=True, env=ENV(home), timeout=120)
    except subprocess.TimeoutExpired:
        return "timeout"
    out = r.stdout.strip()
    if out == "":
        return "allow"
    try:
        data = json.loads(out)
        if "hookSpecificOutput" in data:
            return data["hookSpecificOutput"]["permissionDecision"]
        # observe mode: systemMessage means the hook didn't refuse
        return "allow"
    except json.JSONDecodeError:
        # Only return "unreadable" if output starts with { but fails to decode
        if out.startswith("{"):
            return "unreadable"
        return "allow"


def make_vault(v):
    for rel, text in (("SCHEMA.md", SCHEMA), ("overview.md", OVERVIEW), ("todo.md", TODO)):
        with open(os.path.join(v, rel), "w", encoding="utf-8") as f:
            f.write(text)


def main():
    all_pass = True

    def report(ok, name, expected, got):
        nonlocal all_pass
        if not ok:
            all_pass = False
        print("%s %s: expected %s got %s" % ("PASS" if ok else "FAIL", name, expected, got))

    tmp = tempfile.mkdtemp()
    try:
        import guard_rules
        import read_quarantine
        import receipt_rules

        now = datetime.datetime.now().astimezone()
        stamp = now.isoformat()
        target = os.path.join(tmp, "tool.py")
        with open(target, "w", encoding="utf-8") as f:
            f.write("print('old')\n")

        # --- C14a: a divergent write names a command that exists, never the log by hand ---
        try:
            records = [{"target": target, "time": stamp, "sha256": receipt_rules.fingerprint("print('old')\n"), "status": "success", "model_answered": "m"}]
            res = guard_rules.decide("Write", {"file_path": target, "content": "new = 0\n" * 5},
                                     SETTINGS, records, checks=())
            reason = res.get("reason", "")
            ok = res["decision"] == "deny" and "frugalflow run delegate" in reason \
                and "kind edit" not in reason and "ask the user" in reason
            report(ok, "C14a divergent write refusal", "deny + 'frugalflow run delegate' + 'ask the user', no 'kind edit'",
                   "%s/%r" % (res["decision"], reason[:200]))
        except Exception as e:
            report(False, "C14a divergent write refusal", "no exception", repr(e))

        # --- C14b: a read refusal names no manual log entry ---
        try:
            ctx = {"cwd": tmp, "records": [{"target": target, "time": stamp, "sha256": "x", "status": "success", "model_answered": "m"}],
                   "now": now, "stat": None}
            refuse, reason, _targets = read_quarantine.check("Read", {"file_path": target}, SETTINGS, ctx)
            ok = refuse is True and "kind read" not in reason and "ask the user" in reason and "To fix:" in reason
            report(ok, "C14b read refusal", "refused + 'ask the user', no 'kind read'",
                   "%s/%r" % (refuse, reason[:200]))
        except Exception as e:
            report(False, "C14b read refusal", "no exception", repr(e))

        # --- C17: observe mode renders no refusal, so it attests nothing ---
        H_obs = os.path.join(tmp, "home_observe")
        V_obs = os.path.join(tmp, "vault_observe")
        H_act = os.path.join(tmp, "home_active")
        V_act = os.path.join(tmp, "vault_active")
        for d in (H_obs, V_obs, H_act, V_act):
            os.makedirs(d)
        for h in (H_obs, H_act):
            with open(os.path.join(h, "guard.json"), "w", encoding="utf-8") as f:
                f.write(json.dumps(SETTINGS))
            with open(os.path.join(h, "delegations.jsonl"), "w", encoding="utf-8") as f:
                f.write("")
        with open(os.path.join(H_obs, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs(True, "observe"), f)
        with open(os.path.join(H_act, "preferences.json"), "w", encoding="utf-8") as f:
            json.dump(prefs(True, "active"), f)
        make_vault(V_obs)
        make_vault(V_act)
        try:
            dec_obs = HOOK(H_obs, "Write", {"file_path": os.path.join(V_obs, "notes.md"), "content": PAGE}, V_obs)
            attested_obs = os.path.isfile(os.path.join(V_obs, ATTEST))
            ok = dec_obs == "allow" and not attested_obs
            report(ok, "C17 observe mode attests nothing", "allow + no %s" % ATTEST,
                   "%s/attested=%s" % (dec_obs, attested_obs))
        except Exception as e:
            report(False, "C17 observe mode attests nothing", "no exception", repr(e))

        try:
            dec_act = HOOK(H_act, "Write", {"file_path": os.path.join(V_act, "notes.md"), "content": PAGE}, V_act)
            attested_act = os.path.isfile(os.path.join(V_act, ATTEST))
            ok = dec_act == "deny" and attested_act
            report(ok, "C17 active mode refuses and attests", "deny + %s written" % ATTEST,
                   "%s/attested=%s" % (dec_act, attested_act))
        except Exception as e:
            report(False, "C17 active mode refuses and attests", "no exception", repr(e))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print("SUMMARY e2e_consignes: %s" % ("PASS" if all_pass else "FAIL"))
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())