#!/usr/bin/env python3
# e2e_reading_bash.py - end-to-end test: the guard hook judges a Bash write into a gated vault like a Write

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
    "checks": ["reading_gate"],
}

ATTEST = ".reading.json"
SCHEMA = "# S\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n"
OVERVIEW = "# O\n⛔⛔ never push to main\nplain\n"
TODO = "# T\n- [ ] ⭐⭐ fix the parser\n"
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
    W = tempfile.mkdtemp()  # throwaway folder: no SCHEMA.md at all
    dirs = [H, W]
    all_pass = True

    def report(ok, name, expected, got):
        nonlocal all_pass
        if not ok:
            all_pass = False
        print("%s %s: expected %s got %s" % ("PASS" if ok else "FAIL", name, expected, got))

    def new_vault():
        v = os.path.realpath(tempfile.mkdtemp())
        dirs.append(v)
        make_vault(v, SCHEMA)
        return v

    def new_dir():
        d = os.path.realpath(tempfile.mkdtemp())
        dirs.append(d)
        return d

    def deny_ok(code, dec, reason):
        # an empty stdout reads as allow: a missing denial is a FAIL.
        shown = [b for b in BEARINGS if b in reason]
        return code == 0 and dec == "deny" and len(shown) >= 1 and "To fix:" in reason

    try:
        with open(os.path.join(H, "guard.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(SETTINGS))
        with open(os.path.join(H, "delegations.jsonl"), "w", encoding="utf-8") as f:
            f.write("")

        # --- E1: a Bash write into a gated vault is refused once, then allowed ---
        V1 = new_vault()
        call1 = CALL("Bash", {"command": "echo hello > notes.md"}, V1)
        try:
            code, dec, reason = HOOK(H, call1)
            ok = deny_ok(code, dec, reason)
            report(ok, "E1 echo > notes.md (cwd = vault)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E1 echo > notes.md (cwd = vault)", "no exception", str(e))

        try:
            code2, out2 = STATUS(H, V1)
            ok = os.path.isfile(os.path.join(V1, ATTEST)) and code2 == 0 and out2 == "READ attestation matches the pages"
            report(ok, "E1 the hook attested its own refusal", "%s exists/--status 0 READ" % ATTEST, "exists=%s/--status %s %s" % (os.path.isfile(os.path.join(V1, ATTEST)), code2, out2))
        except Exception as e:
            report(False, "E1 the hook attested its own refusal", "no exception", str(e))

        try:
            code3, dec3, reason3 = HOOK(H, call1)
            ok = code3 == 0 and dec3 == "allow" and reason3 == ""
            report(ok, "E1 the identical call right after", "allow/0/no restitution", "%s/%s/%r" % (dec3, code3, reason3[:120]))
        except Exception as e:
            report(False, "E1 the identical call right after", "no exception", str(e))

        # --- E2: an absolute target outside the cwd is judged on its own vault ---
        V2 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "printf x > " + os.path.join(V2, "new.md")}, W))
            ok = deny_ok(code, dec, reason)
            report(ok, "E2 printf > <vault>/new.md (cwd outside)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E2 printf > <vault>/new.md (cwd outside)", "no exception", str(e))

        # --- E3: a cd into the vault is tracked ---
        V3 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "cd " + V3 + " && echo x > a.md"}, W))
            ok = deny_ok(code, dec, reason)
            report(ok, "E3 cd <vault> && echo x > a.md (cwd outside)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E3 cd <vault> && echo x > a.md (cwd outside)", "no exception", str(e))

        # --- E4: a cd to the parent, then a relative path into the vault ---
        V4 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "cd " + os.path.dirname(V4) + " && echo x > " + os.path.basename(V4) + "/b.md"}, W))
            ok = deny_ok(code, dec, reason)
            report(ok, "E4 cd <parent> && echo x > <vault>/b.md (cwd outside)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E4 cd <parent> && echo x > <vault>/b.md (cwd outside)", "no exception", str(e))

        # --- E5: tee and cp name their destination without a redirection ---
        V5 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "tee notes2.md"}, V5))
            ok = deny_ok(code, dec, reason)
            report(ok, "E5 tee notes2.md (cwd = vault)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E5 tee notes2.md (cwd = vault)", "no exception", str(e))

        V5b = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "cp src.md notes3.md"}, V5b))
            ok = deny_ok(code, dec, reason)
            report(ok, "E5 cp src.md notes3.md (cwd = vault)", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E5 cp src.md notes3.md (cwd = vault)", "no exception", str(e))

        # --- E6: a read stays free ---
        V6 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "cat overview.md todo.md"}, V6))
            ok = code == 0 and dec == "allow" and not os.path.exists(os.path.join(V6, ATTEST))
            report(ok, "E6 cat overview.md todo.md (cwd = vault)", "allow/0/no %s written" % ATTEST, "%s/%s/%s exists=%s" % (dec, code, reason[:60], os.path.exists(os.path.join(V6, ATTEST))))
        except Exception as e:
            report(False, "E6 cat overview.md todo.md (cwd = vault)", "no exception", str(e))

        # --- E7: a write outside any vault stays free ---
        OUT = new_dir()
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "echo hi > " + os.path.join(OUT, "out.txt")}, W))
            ok = code == 0 and dec == "allow" and not os.path.exists(os.path.join(OUT, ATTEST))
            report(ok, "E7 echo > <outside>/out.txt", "allow/0/no %s written" % ATTEST, "%s/%s/%s exists=%s" % (dec, code, reason[:60], os.path.exists(os.path.join(OUT, ATTEST))))
        except Exception as e:
            report(False, "E7 echo > <outside>/out.txt", "no exception", str(e))

        # --- E8: the attestation file stays hand-write-proof, Bash included ---
        try:
            code, dec, reason = HOOK(H, CALL("Bash", {"command": "echo x > " + ATTEST}, V1))
            ok = code == 0 and dec == "deny" and "To fix: never write this file by hand" in reason
            report(ok, "E8 echo > .reading.json (cwd = vault)", "deny/0/'To fix: never write this file by hand'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "E8 echo > .reading.json (cwd = vault)", "no exception", str(e))

        # --- Témoin: the Write tool path is untouched ---
        V7 = new_vault()
        try:
            code, dec, reason = HOOK(H, CALL("Write", {"file_path": os.path.join(V7, "notes.md"), "content": PAGE}, V7))
            ok = deny_ok(code, dec, reason)
            report(ok, "Témoin Write to <vault>/notes.md", "deny/0/a bearing line in the reason/'To fix:'", "%s/%s/%r" % (dec, code, reason[:120]))
        except Exception as e:
            report(False, "Témoin Write to <vault>/notes.md", "no exception", str(e))

    finally:
        for d in dirs:
            shutil.rmtree(d, ignore_errors=True)

    return all_pass


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--notice":
            print(
                "NAME      e2e_reading_bash.py - end-to-end test: the guard hook judges a Bash write into a vault that requires a reading like a Write - redirections, tee, cp, cd and pushd tracked - while a read and a write outside a vault stay free.\n"
                "READS     the tools in ../bin; everything else lives in temporary folders (FRUGALFLOW_HOME and HOME are thrown away under /tmp).\n"
                "WRITES    nothing outside its temporary folders: one PASS or FAIL line per case, then E2E READING BASH OK (0) or E2E READING BASH FAILED (1).\n"
                "EXAMPLE   python3 e2e_reading_bash.py\n"
                "PITFALLS  2026-11-05 a Bash write into a gated vault passed untouched: the gate only judged Write, Edit, MultiEdit and NotebookEdit. An empty stdout reads as allow - every deny case must be seen red before it is trusted.\n"
                "          Each deny case needs a fresh vault: the hook attests its own refusal, so the next write into the same vault is allowed on purpose.\n"
            )
            sys.exit(0)
        elif sys.argv[1] != "--autotest":
            print("usage: e2e_reading_bash.py [--autotest] | --notice")
            sys.exit(2)

    ok = run_e2e()
    if ok:
        print("E2E READING BASH OK")
        sys.exit(0)
    else:
        print("E2E READING BASH FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
