#!/usr/bin/env python3
# e2e_guards.py - end-to-end test: the guard hooks and brief checks

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
CASES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "brief_cases.json")
PROBES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "guard_probes.py")
ATTACKS = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "guard_attacks.json")

SETTINGS = {
    "code_extensions": [".py"],
    "line_threshold": 3,
    "receipt_minutes": 60,
    "delegate_tools": [],
    "fix_hint": "delegate it.",
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
}
CODE = "a\nb\nc\nd\n"
PROBE2 = "cat > /tmp/x.py <<EOF\nprint(1)\nEOF"
BIG = ("x" * 249 + "\n") * 500
SMALL = "a\nb\n"


def CALL(tool, inp):
    return json.dumps({"tool_name": tool, "tool_input": inp})


def ENV(home):
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY", "FRUGALFLOW_BRIEF_RULES"):
        env.pop(key, None)
    env["FRUGALFLOW_HOME"] = home
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


def JSONL(path):
    if not os.path.exists(path):
        return []
    result = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                result.append(json.loads(line))
    return result


def AUDIT(home):
    return [r.get("audit") for r in JSONL(os.path.join(home, "audit.jsonl"))]


def BLOCKS(home):
    return [
        r.get("rule")
        for r in JSONL(os.path.join(home, "blocks", "guard.jsonl"))
        if r.get("kind") == "block"
    ]


def CASE(expected):
    with open(CASES, "r", encoding="utf-8") as f:
        data = json.load(f)
    for c in data["cases"]:
        if c["expected"] == expected and c.get("trust", "private") == "private":
            return c
    raise ValueError("no case with expected=%r" % expected)


def run_e2e():
    H = tempfile.mkdtemp()
    all_pass = True

    try:
        # shared setup
        with open(os.path.join(H, "guard.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(SETTINGS))
        with open(os.path.join(H, "delegations.jsonl"), "w", encoding="utf-8") as f:
            f.write("")
        with open(os.path.join(H, "big.log"), "w", encoding="utf-8") as f:
            f.write(BIG)
        with open(os.path.join(H, "small.md"), "w", encoding="utf-8") as f:
            f.write(SMALL)

        # --- step 1: write ---
        try:
            code, decision, reason = HOOK(H, CALL("Write", {"file_path": "/w/b.py", "content": CODE}))
            audit = AUDIT(H)
            blocks = BLOCKS(H)
            ok = (
                code == 0
                and decision == "deny"
                and reason != ""
                and "To fix:" in reason
                and audit == ["no_receipt"]
                and blocks == ["no_receipt"]
            )
            if ok:
                print("PASS 1 write: expected deny/0/'To fix:' in reason/audit=[no_receipt]/blocks=[no_receipt] got deny/0/'To fix:' in reason/audit=[no_receipt]/blocks=[no_receipt]")
            else:
                all_pass = False
                print("FAIL 1 write: expected deny/0/'To fix:' in reason/audit=[no_receipt]/blocks=[no_receipt] got %s/%s/%r/audit=%s/blocks=%s" % (decision, code, reason, audit, blocks))
        except Exception as e:
            all_pass = False
            print("FAIL 1 write: expected no exception got %s" % e)

        # --- step 2: shell ---
        try:
            code1, dec1, reason1 = HOOK(H, CALL("Bash", {"command": PROBE2}))
            code2, dec2, reason2 = HOOK(H, CALL("Bash", {"command": "git status"}))
            audit = AUDIT(H)
            blocks = BLOCKS(H)
            code3, out3 = RUN([PROBES, "--autotest"], os.path.join(H, "probes"))
            probes_ok = code3 == 0 and "13/13 probes conform" in out3
            ok = (
                code1 == 0
                and dec1 == "deny"
                and code2 == 0
                and dec2 == "allow"
                and audit == ["no_receipt", "shell_write"]
                and blocks == ["no_receipt", "shell_write"]
                and probes_ok
            )
            if ok:
                print("PASS 2 shell: expected deny/allow/audit=[no_receipt,shell_write]/blocks=[no_receipt,shell_write]/13/13 got deny/allow/audit=[no_receipt,shell_write]/blocks=[no_receipt,shell_write]/13/13")
            else:
                all_pass = False
                print("FAIL 2 shell: expected deny/allow/audit=[no_receipt,shell_write]/blocks=[no_receipt,shell_write]/13/13 got %s/%s/audit=%s/blocks=%s/probes=%d/%r" % (dec1, dec2, audit, blocks, code3, out3.strip()))
        except Exception as e:
            all_pass = False
            print("FAIL 2 shell: expected no exception got %s" % e)

        # --- step 3: entry ---
        try:
            code1, dec1, reason1 = HOOK(H, CALL("Read", {"file_path": os.path.join(H, "big.log")}))
            code2, dec2, reason2 = HOOK(H, CALL("Read", {"file_path": os.path.join(H, "small.md")}))
            audit = AUDIT(H)
            blocks = BLOCKS(H)
            ok = (
                code1 == 0
                and dec1 == "deny"
                and code2 == 0
                and dec2 == "allow"
                and audit == ["no_receipt", "shell_write", "refused:intake"]
                and len(blocks) == 3
            )
            if ok:
                print("PASS 3 entry: expected deny/allow/audit=[no_receipt,shell_write,refused:intake]/blocks_len=3 got deny/allow/audit=[no_receipt,shell_write,refused:intake]/blocks_len=3")
            else:
                all_pass = False
                print("FAIL 3 entry: expected deny/allow/audit=[no_receipt,shell_write,refused:intake]/blocks_len=3 got %s/%s/audit=%s/blocks_len=%d" % (dec1, dec2, audit, len(blocks)))
        except Exception as e:
            all_pass = False
            print("FAIL 3 entry: expected no exception got %s" % e)

        # --- step 4: replay ---
        try:
            n = len(AUDIT(H))
            code, out = RUN(
                [os.path.join(BIN, "block_log.py"), "replay", "--tool", "guard", "--tool-version", "e2e"],
                H,
            )
            audit_after = AUDIT(H)
            expected_str = "replayed 3: reproduced 3, no_longer_reproduced 0"
            ok = (
                code == 0
                and out != ""
                and expected_str in out
                and len(audit_after) == n
                and n == 3
            )
            if ok:
                print("PASS 4 replay: expected 0/'%s'/audit_unchanged=3 got 0/'%s'/audit_len=%d" % (expected_str, expected_str, n))
            else:
                all_pass = False
                print("FAIL 4 replay: expected 0/'%s'/audit_unchanged=3 got %d/%r/audit_len=%d" % (expected_str, code, out.strip(), len(audit_after)))
        except Exception as e:
            all_pass = False
            print("FAIL 4 replay: expected no exception got %s" % e)

        # --- step 5: brief ---
        try:
            dctx = tempfile.TemporaryDirectory()
            d = dctx.name
            bad = CASE("refuse")["brief"]
            good = CASE("pass")["brief"]
            with open(os.path.join(d, "bad.md"), "w", encoding="utf-8") as f:
                f.write(bad)
            with open(os.path.join(d, "good.md"), "w", encoding="utf-8") as f:
                f.write(good)

            c1, _ = RUN(
                [os.path.join(BIN, "brief_check.py"), "--brief", os.path.join(d, "bad.md"), "--trust", "private"],
                d,
            )
            c2, _ = RUN(
                [os.path.join(BIN, "brief_check.py"), "--brief", os.path.join(d, "good.md"), "--trust", "private"],
                d,
            )
            c3, o3 = RUN(
                [os.path.join(BIN, "delegate.py"), "--role", "code", "--file", os.path.join(d, "bad.md"), "--out", os.path.join(d, "e.py")],
                d,
            )
            # the refusal is now logged under blocks/ (every refusal is logged); nothing else may appear.
            logged = os.path.isfile(os.path.join(d, "blocks", "delegate.jsonl"))
            listing = sorted(x for x in os.listdir(d) if x != "blocks")

            ok = (
                c1 == 5
                and c2 == 0
                and c3 == 7
                and o3 != ""
                and "BRIEF REFUSED: nothing sent" in o3
                and listing == ["bad.md", "good.md"]
                and logged
            )
            if ok:
                print("PASS 5 brief: expected 5/0/7+'BRIEF REFUSED: nothing sent'/list=[bad.md,good.md] got 5/0/7+'BRIEF REFUSED: nothing sent'/list=[bad.md,good.md]")
            else:
                all_pass = False
                print("FAIL 5 brief: expected 5/0/7+'BRIEF REFUSED: nothing sent'/list=[bad.md,good.md] got %d/%d/%d/%r/list=%s" % (c1, c2, c3, o3.strip(), listing))
            dctx.cleanup()
        except Exception as e:
            all_pass = False
            print("FAIL 5 brief: expected no exception got %s" % e)

        # --- step 6: attacks (holes kept closed, false refusals lifted) ---
        n = len(json.load(open(ATTACKS, encoding="utf-8"))["probes"])
        r = subprocess.run([sys.executable, PROBES, "--autotest"], capture_output=True, text=True, env=dict(ENV(H), GUARD_PROBES_DATA=ATTACKS))
        fails = [l for l in r.stdout.splitlines() if l.startswith("FAIL")]
        ok = r.returncode == 0 and "%d/%d probes conform" % (n, n) in r.stdout and n >= 107
        all_pass = all_pass and ok
        print("%s 6 attacks: expected %d/%d got rc=%d %s" % ("PASS" if ok else "FAIL", n, n, r.returncode, " || ".join(fails)[:2000]))

    finally:
        shutil.rmtree(H, ignore_errors=True)

    return all_pass


def main():
    if len(sys.argv) > 1:
        if sys.argv[1] == "--notice":
            print(
                "NAME      e2e_guards.py - end-to-end test: the guard hook refuses and logs, the block log replays without writing the audit, the brief guard stops a faulty brief before any sending.\n"
                "READS     the tools in ../bin and the brief cases in ../data next to this file; everything else lives in temporary folders.\n"
                "WRITES    nothing outside its temporary folders: one PASS or FAIL line per step, then E2E GUARDS OK (0) or E2E GUARDS FAILED (1).\n"
                "EXAMPLE   python3 e2e_guards.py\n"
                "PITFALLS  2026-09-26 the entry checks were proved only by hand; this suite runs them through the real hook and must be seen red by bite.py before it is trusted.\n"
                "          2026-09-26 the suite left its temporary folder behind on every run; it is now removed in a finally block, and the 13 probes of a naive guard run in step 2.\n"
                "          2026-09-27 the shell attacks lived only in a report; step 6 replays ../data/guard_attacks.json (holes to keep closed, false refusals lifted)."
            )
            sys.exit(0)
        elif sys.argv[1] != "--autotest":
            print("usage: e2e_guards.py [--autotest] | --notice")
            sys.exit(2)

    ok = run_e2e()
    if ok:
        print("E2E GUARDS OK")
        sys.exit(0)
    else:
        print("E2E GUARDS FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()
