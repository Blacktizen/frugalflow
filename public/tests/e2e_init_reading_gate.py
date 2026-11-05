#!/usr/bin/env python3
# e2e_init_reading_gate.py - end-to-end test: init installs reading_gate in guard.json checks and doctor flags its absence

import json
import os
import shutil
import subprocess
import sys
import tempfile

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")

NOTICE = (
    "NAME      e2e_init_reading_gate.py - end-to-end test: init installs reading_gate in guard.json checks and doctor flags its absence.\n"
    "READS     the tools in ../bin; temporary directories for FRUGALFLOW_HOME and HOME.\n"
    "WRITES    nothing outside temporary directories: one PASS or FAIL line per case, then E2E INIT READING GATE OK (0) or FAILED (1).\n"
    "EXAMPLE   python3 e2e_init_reading_gate.py\n"
    "PITFALLS  2026-11-05 the reading_gate check must be in guard.json checks for the gate to be armed on install; doctor must flag its absence."
)


def ENV(home):
    env = dict(os.environ)
    for key in ("FRUGALFLOW_GUARD", "FRUGALFLOW_REPLAY"):
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
        return (r.returncode, r.stdout, r.stderr)
    except subprocess.TimeoutExpired:
        return (-1, "", "timeout")


def main():
    if len(sys.argv) > 1 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)

    all_pass = True

    def report(ok, name, expected, got):
        nonlocal all_pass
        if not ok:
            all_pass = False
        print("%s %s: expected %s got %s" % ("PASS" if ok else "FAIL", name, expected, got))

    T = tempfile.mkdtemp()
    try:
        home = os.path.join(T, "ff")
        claude = os.path.join(T, "claude")

        # --- a) Run init ---
        init_args = [
            os.path.join(BIN, "init_cmd.py"),
            "--home", home,
            "--claude-dir", claude,
            "--ollama-url", "http://127.0.0.1:1",
            "--lmstudio-url", "http://127.0.0.1:1",
        ]
        rc, out, err = RUN(init_args, T)
        ok = rc == 0
        report(ok, "a init rc=0", "0", str(rc))

        # --- b) guard.json checks contain reading_gate ---
        guard_path = os.path.join(home, "guard.json")
        try:
            with open(guard_path, "r", encoding="utf-8") as f:
                guard = json.load(f)
            checks = guard.get("checks", [])
            ok = "reading_gate" in checks
            report(ok, "b init checks contain reading_gate", "reading_gate in checks", "checks=%s" % checks)
        except Exception as e:
            report(False, "b init checks contain reading_gate", "no exception", str(e))

        # --- c) doctor silent on reading_gate after init ---
        doctor_args = [
            os.path.join(BIN, "doctor_cmd.py"),
            "--home", home,
            "--claude-dir", claude,
            "--ollama-url", "http://127.0.0.1:1",
            "--lmstudio-url", "http://127.0.0.1:1",
        ]
        rc, out, err = RUN(doctor_args, T)
        fail_lines = [line for line in out.splitlines() if line.startswith("FAIL") and "reading_gate" in line]
        ok = rc == 0 and len(fail_lines) == 0
        report(ok, "c doctor silent on reading_gate after init", "rc=0 and no FAIL reading_gate", "rc=%d fail_lines=%s" % (rc, fail_lines))

        # --- d) Remove reading_gate from checks, doctor flags it ---
        try:
            with open(guard_path, "r", encoding="utf-8") as f:
                guard = json.load(f)
            original_checks = list(guard.get("checks", []))
            guard["checks"] = [c for c in guard.get("checks", []) if c != "reading_gate"]
            with open(guard_path, "w", encoding="utf-8") as f:
                json.dump(guard, f, indent=2, ensure_ascii=False)
                f.write("\n")

            rc, out, err = RUN(doctor_args, T)
            fail_lines = [line for line in out.splitlines() if line.startswith("FAIL") and "reading_gate" in line]
            ok = rc == 1 and len(fail_lines) >= 1
            report(ok, "d doctor flags a checks list without reading_gate", "rc=1 and FAIL line with reading_gate", "rc=%d fail_lines=%s" % (rc, fail_lines))
        except Exception as e:
            report(False, "d doctor flags a checks list without reading_gate", "no exception", str(e))

        # --- e) Restore original guard.json ---
        try:
            with open(guard_path, "r", encoding="utf-8") as f:
                guard = json.load(f)
            guard["checks"] = original_checks
            with open(guard_path, "w", encoding="utf-8") as f:
                json.dump(guard, f, indent=2, ensure_ascii=False)
                f.write("\n")
            report(True, "e restore original guard.json", "success", "ok")
        except Exception as e:
            report(False, "e restore original guard.json", "no exception", str(e))

        # Set switch to active mode for the reading gate test (deny only happens in active)
        prefs_path = os.path.join(home, "preferences.json")
        try:
            with open(prefs_path, "r", encoding="utf-8") as f:
                prefs = json.load(f)
            prefs["switch"]["mode"] = "active"
            with open(prefs_path, "w", encoding="utf-8") as f:
                json.dump(prefs, f, indent=2, ensure_ascii=False)
                f.write("\n")
        except Exception as e:
            report(False, "e set mode to active", "no exception", str(e))

        # --- f) Create vault and verify REQUIRED-READING block ---
        new_project_args = [
            os.path.join(BIN, "frugalflow.py"),
            "new-project", "demo",
            "--root", os.path.join(T, "projects"),
        ]
        rc, out, err = RUN(new_project_args, T)
        ok = rc == 0
        report(ok, "f new-project rc=0", "0", str(rc))

        vault_path = os.path.join(T, "projects", "demo", "vault")
        schema_path = os.path.join(vault_path, "SCHEMA.md")
        has_required_block = False
        if os.path.isfile(schema_path):
            with open(schema_path, "r", encoding="utf-8") as f:
                content = f.read()
            has_required_block = "REQUIRED-READING" in content
        report(has_required_block, "f vault SCHEMA.md has REQUIRED-READING block", "True", str(has_required_block))

        # --- g) First Write into the new vault is refused ---
        if has_required_block:
            notes_path = os.path.join(vault_path, "notes.md")
            call = json.dumps({
                "tool_name": "Write",
                "tool_input": {"file_path": notes_path, "content": "first write\n"},
                "cwd": vault_path
            })
            rc, out, err = RUN([os.path.join(BIN, "guard_hook.py"), "--hook"], home, call)
            denied = False
            try:
                if out.strip():
                    h = json.loads(out.strip())["hookSpecificOutput"]
                    denied = h.get("permissionDecision") == "deny"
            except (json.JSONDecodeError, KeyError, TypeError):
                denied = False
            report(denied, "g first Write into the new vault is refused", "deny", "denied=%s rc=%d out=%r" % (denied, rc, out[:200]))
        else:
            report(False, "g first Write into the new vault is refused", "deny", "skipped (no REQUIRED-READING block)")

    finally:
        shutil.rmtree(T, ignore_errors=True)

    if all_pass:
        print("E2E INIT READING GATE OK")
        sys.exit(0)
    else:
        print("E2E INIT READING GATE FAILED")
        sys.exit(1)


if __name__ == "__main__":
    main()