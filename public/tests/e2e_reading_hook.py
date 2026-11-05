#!/usr/bin/env python3
# e2e_reading_hook.py - end-to-end test: the guard hook opens the reading gate itself, and never lets its attestation be written by hand

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

SETTINGS = {
    "code_extensions": [".py"],
    "line_threshold": 3,
    "receipt_minutes": 60,
    "delegate_tools": [],
    "fix_hint": "delegate it.",
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}

ATTEST = ".reading.json"
SCHEMA = "# S\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n"
SCHEMA_NO_BLOCK = "# S\n## Rules\n- nothing is required here\n"
OVERVIEW = "# O\n⛔⛔ never push to main\nplain\n"
TODO = "# T\n- [ ] ⭐⭐ fix the parser\n"
NEW_RULE = "⛔ seal the log before writing\n"
PAGE = "# notes\nthe first write into the vault\n"
BEARINGS = ["⛔⛔ never push to main", "- [ ] ⭐⭐ fix the parser"]


def CALL(tool, inp, cwd=None):
    payload = {"tool_name": tool, "tool_input": inp}
    if cwd:
        payload["cwd"] = cwd
    return json.dumps(payload)


def ENV(home):
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY", "FRUGALFLOW_BRIEF_RULES"):
        env.pop(key, None)
    env["FRUGALFLOW_HOME"] = home
    env["HOME"] = home
    return env


def RUN(args, home, stdin_text=""):
    try:
        r = subprocess.run(
            [sys.executable] + args,
            input=stdin_text,
            capture_output=True,
            text=True,
            env=ENV(home),
            timeout=120,
        )
        return (r.returncode, r.stdout)
    except subprocess.TimeoutExpired:
        return (-1, "")


def HOOK(home, call):
    code, out = RUN([os.path.join(BIN, "guard_hook.py"), "--hook"], home, call)
    stripped = out.strip()
    if stripped == "":
        return (code, "allow", "")
    try:
        h = json.loads(stripped)["hookSpecificOutput"]
        return (code, h["permissionDecision"], h["permissionDecisionReason"])
    except (json.JSONDecodeError, KeyError, TypeError):
        return (code, "unreadable", stripped)


def STATUS(home, vault):
    code, out = RUN([os.path.join(BIN, "reading_gate.py"), "--vault", vault, "--status"], home)
    return (code, out.strip())


def make_vault(v, schema):
    for rel, text in (("SCHEMA.md", schema), ("overview.md", OVERVIEW), ("todo.md", TODO)):
        with open(os.path.join(v, rel), "w", encoding="utf-8") as f:
            f.write(text)


def run_e2e():
    H = tempfile.mkdtemp()  # throwaway FRUGALFLOW_HOME
    V = tempfile.mkdtemp()  # throwaway vault: SCHEMA.md carries a REQUIRED-READING block
    P = tempfile.mkdtemp()  # throwaway folder: SCHEMA.md without any block
    W = tempfile.mkdtemp()  # throwaway folder: no SCHEMA.md at all
    all_pass = True

    def report(ok, name, expected, got):
        nonlocal all_pass
        if not ok:
            all_pass = False
        print("%s %s: expected %s got %s" % ("PASS" if ok else "FAIL", name, expected, got))

    try:
        with open(os.path.join(H, "guard.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(SETTINGS))
        with open(os.path.join(H, "delegations.jsonl"), "w", encoding="utf-8") as f:
            f.write("")
        make_vault(V, SCHEMA)
        make_vault(P, SCHEMA_NO_BLOCK)

        notes = os.path.join(V, "notes.md")
        first_call = CALL("Write", {"file_path": notes, "content": PAGE}, V)
        attest_path = os.path.join(V, ATTEST)

        # --- E1: the first write into a gated vault is refused once, with the bearing lines ---
        try:
            code, dec, reason = HOOK(H, first_call)
            shown = [b for b in BEARINGS if b in reason]
            ok = code == 0 and dec == "deny" and len(shown) >= 1 and "To fix:" in reason
            report(
                ok,
                "E1 first write",
                "deny/0/a bearing line in the reason/'To fix:'",
                "%s/%s/%s/%r" % (dec, code, shown, reason[:120]),
            )
        except Exception as e:
            report(False, "E1 first write", "no exception", str(e))

        try:
            code2, out2 = STATUS(H, V)
            ok = os.path.isfile(attest_path) and code2 == 0 and out2 == "READ attestation matches the pages"
            report(
                ok,
                "E1 the hook attested its own refusal",
                "%s exists/--status 0 READ" % ATTEST,
                "exists=%s/--status %s %s" % (os.path.isfile(attest_path), code2, out2),
            )
        except Exception as e:
            report(False, "E1 the hook attested its own refusal", "no exception", str(e))

        try:
            code3, dec3, reason3 = HOOK(H, first_call)
            ok = code3 == 0 and dec3 == "allow" and reason3 == ""
            report(ok, "E1 the identical write right after", "allow/0/no restitution", "%s/%s/%r" % (dec3, code3, reason3[:120]))
        except Exception as e:
            report(False, "E1 the identical write right after", "no exception", str(e))

        try:
            code4, dec4, reason4 = HOOK(H, CALL("Write", {"file_path": os.path.join(V, "01-context", "other.md"), "content": PAGE}, V))
            ok = code4 == 0 and dec4 == "allow" and reason4 == ""
            report(ok, "E1 refused exactly once (another page)", "allow/0/no restitution", "%s/%s/%r" % (dec4, code4, reason4[:120]))
        except Exception as e:
            report(False, "E1 refused exactly once (another page)", "no exception", str(e))

        # --- E2: the attestation is a protected file: only the hook writes it ---
        try:
            code5, dec5, reason5 = HOOK(H, CALL("Write", {"file_path": attest_path, "content": "{\"fingerprint\": \"hand-made\"}\n"}, V))
            ok = code5 == 0 and dec5 == "deny" and "To fix: never write this file by hand" in reason5
            report(
                ok,
                "E2 hand-written attestation (Write)",
                "deny/0/'To fix: never write this file by hand'",
                "%s/%s/%r" % (dec5, code5, reason5[:120]),
            )
        except Exception as e:
            report(False, "E2 hand-written attestation (Write)", "no exception", str(e))

        try:
            code6, dec6, reason6 = HOOK(H, CALL("Bash", {"command": "echo x > " + attest_path}, V))
            ok = code6 == 0 and dec6 == "deny" and "To fix: never write this file by hand" in reason6
            report(
                ok,
                "E2 hand-written attestation (Bash)",
                "deny/0/'To fix: never write this file by hand'",
                "%s/%s/%r" % (dec6, code6, reason6[:120]),
            )
        except Exception as e:
            report(False, "E2 hand-written attestation (Bash)", "no exception", str(e))

        try:
            code7, out7 = STATUS(H, V)
            with open(attest_path, "r", encoding="utf-8") as f:
                kept = f.read()
            ok = code7 == 0 and out7 == "READ attestation matches the pages" and kept.strip() not in ("x", "")
            report(
                ok,
                "E2 the refusals left the attestation untouched",
                "--status 0 READ/the file is not 'x'",
                "--status %s %s/kept=%r" % (code7, out7, kept[:40]),
            )
        except Exception as e:
            report(False, "E2 the refusals left the attestation untouched", "no exception", str(e))

        try:
            code8, dec8, reason8 = HOOK(H, CALL("Bash", {"command": "cat " + attest_path}, V))
            ok = code8 == 0 and dec8 == "allow"
            report(ok, "E2 reading the attestation is not a write", "allow/0", "%s/%s/%r" % (dec8, code8, reason8[:120]))
        except Exception as e:
            report(False, "E2 reading the attestation is not a write", "no exception", str(e))

        # --- E3: a folder without a required-reading block is never touched ---
        try:
            code9, dec9, reason9 = HOOK(H, CALL("Write", {"file_path": os.path.join(P, "notes.md"), "content": PAGE}, P))
            ok = code9 == 0 and dec9 == "allow" and not os.path.exists(os.path.join(P, ATTEST))
            report(
                ok,
                "E3 SCHEMA.md without a block",
                "allow/0/no %s written" % ATTEST,
                "%s/%s/%s exists=%s" % (dec9, code9, reason9[:60], os.path.exists(os.path.join(P, ATTEST))),
            )
        except Exception as e:
            report(False, "E3 SCHEMA.md without a block", "no exception", str(e))

        try:
            code10, dec10, reason10 = HOOK(H, CALL("Write", {"file_path": os.path.join(W, "notes.md"), "content": PAGE}, W))
            ok = code10 == 0 and dec10 == "allow" and not os.path.exists(os.path.join(W, ATTEST))
            report(
                ok,
                "E3 no SCHEMA.md at all",
                "allow/0/no %s written" % ATTEST,
                "%s/%s/%s exists=%s" % (dec10, code10, reason10[:60], os.path.exists(os.path.join(W, ATTEST))),
            )
        except Exception as e:
            report(False, "E3 no SCHEMA.md at all", "no exception", str(e))

        # --- E4: pages changed = the gate refuses again, once ---
        try:
            with open(os.path.join(V, "todo.md"), "a", encoding="utf-8") as f:
                f.write(NEW_RULE)
            third = os.path.join(V, "third.md")
            stale_call = CALL("Write", {"file_path": third, "content": PAGE}, V)
            code11, dec11, reason11 = HOOK(H, stale_call)
            ok = code11 == 0 and dec11 == "deny" and NEW_RULE in reason11 and "To fix:" in reason11
            report(
                ok,
                "E4 stale attestation",
                "deny/0/%r in the reason/'To fix:'" % NEW_RULE,
                "%s/%s/%s/%r" % (dec11, code11, NEW_RULE in reason11, reason11[:120]),
            )
            code12, dec12, reason12 = HOOK(H, stale_call)
            ok2 = code12 == 0 and dec12 == "allow" and reason12 == ""
            report(ok2, "E4 the identical write right after", "allow/0/no restitution", "%s/%s/%r" % (dec12, code12, reason12[:120]))
        except Exception as e:
            report(False, "E4 stale attestation", "no exception", str(e))

    finally:
        for d in (H, V, P, W):
            shutil.rmtree(d, ignore_errors=True)

    return all_pass


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--notice":
            print(
                "NAME      e2e_reading_hook.py - end-to-end test: the guard hook refuses the first write into a vault that requires a reading, shows the bearing lines, attests the refusal itself, and refuses every hand-write of that attestation.\n"
                "READS     the tools in ../bin; everything else lives in temporary folders (FRUGALFLOW_HOME and HOME are thrown away under /tmp).\n"
                "WRITES    nothing outside its temporary folders: one PASS or FAIL line per case, then E2E READING HOOK OK (0) or E2E READING HOOK FAILED (1).\n"
                "EXAMPLE   python3 e2e_reading_hook.py\n"
                "PITFALLS  2026-11-05 the gate only showed its lines when it was asked; a write into a gated vault passed untouched. This suite runs the real hook and must be seen red before it is trusted.\n"
                "          A folder whose SCHEMA.md carries no block must stay untouched: the gate may not fall back to the default pages here.\n"
            )
            sys.exit(0)
        elif sys.argv[1] != "--autotest":
            print("usage: e2e_reading_hook.py [--autotest] | --notice")
            sys.exit(2)

    ok = run_e2e()
    if ok:
        print("E2E READING HOOK OK")
        sys.exit(0)
    else:
        print("E2E READING HOOK FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
