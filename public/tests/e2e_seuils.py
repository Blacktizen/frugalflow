#!/usr/bin/env python3
import os
import sys
import json
import subprocess
import tempfile
import shutil
import time

ROOT = os.environ.get("FF_ROOT") or os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
CFG_EXAMPLE = os.path.join(ROOT, "config", "guard.example.json")

def run_hook(home, work, tool_name, tool_input, prefs=None, env_extra=None):
    """Run guard_hook.py as a real hook. Returns (decision, reason, audit_labels)."""
    hook_script = os.path.join(BIN, "guard_hook.py")
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input, "cwd": work})
    env = {"PATH": "/usr/bin:/bin", "FRUGALFLOW_HOME": home}
    if "HOME" in os.environ:
        env["HOME"] = os.environ["HOME"]
    if env_extra:
        env.update(env_extra)
    proc = subprocess.run(
        [sys.executable, hook_script, "--hook"],
        input=payload,
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
    )
    decision = "allow"
    reason = ""
    if proc.stdout.strip():
        try:
            last_line = proc.stdout.strip().splitlines()[-1]
            d = json.loads(last_line)
            decision = d["hookSpecificOutput"]["permissionDecision"]
            reason = d["hookSpecificOutput"]["permissionDecisionReason"]
        except Exception:
            pass
    audit_labels = read_audit(home)
    return decision, reason, audit_labels

def read_audit(home):
    path = os.path.join(home, "audit.jsonl")
    if not os.path.exists(path):
        return []
    out = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                try:
                    out.append(json.loads(line)["audit"])
                except Exception:
                    pass
    return out

def setup_home(home):
    """Create guard.json, delegations.jsonl, preferences.json, empty audit.jsonl not created."""
    with open(CFG_EXAMPLE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    # Keep line_threshold at 20 (default), set receipt_minutes to 30
    cfg["line_threshold"] = 20
    cfg["receipt_minutes"] = 30
    with open(os.path.join(home, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(cfg, f)
    with open(os.path.join(home, "delegations.jsonl"), "w", encoding="utf-8") as f:
        pass
    # 2026-11-12: the code-receipt rule lives in orchestrator mode.
    prefs = {"schema_version": "1", "switch": {"enabled": True, "mode": "orchestrator"}}
    with open(os.path.join(home, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(prefs, f)

def main():
    failures = 0
    check_num = 0

    def check(num, expected, got, desc):
        nonlocal failures
        if expected == got:
            print(f"PASS {num} {desc}: expected {expected} got {got}")
        else:
            print(f"FAIL {num} {desc}: expected {expected} got {got}")
            failures += 1

    # Scenario 1: C13 - Write of notebook on ONE line with 60 code cells -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            cells = [{"cell_type": "code", "source": [f"y{i} = {i}\n"], "metadata": {}, "outputs": [], "execution_count": None} for i in range(60)]
            nb = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
            content = json.dumps(nb)
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "nb.ipynb"), "content": content})
            check(check_num, "deny", decision, "C13: notebook 60 code cells one line")

    # Scenario 2: C13 witness - Write of notebook with 1 code cell (3 lines) + 1 markdown -> allow
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            cells = [
                {"cell_type": "code", "source": ["a=1\n", "b=2\n", "c=3\n"], "metadata": {}, "outputs": [], "execution_count": 1},
                {"cell_type": "markdown", "source": ["# Note"], "metadata": {}},
            ]
            nb = {"cells": cells, "metadata": {}, "nbformat": 4, "nbformat_minor": 5}
            content = json.dumps(nb)
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "nb2.ipynb"), "content": content})
            check(check_num, "allow", decision, "C13 witness: notebook 1 code cell 3 lines + markdown")

    # Scenario 3: C15 tsx - Write of 60 lines .tsx -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content = "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "comp.tsx"), "content": content})
            check(check_num, "deny", decision, "C15 tsx: 60 lines .tsx")

    # Scenario 4: C15 go - Write of 60 lines .go -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content = "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "main.go"), "content": content})
            check(check_num, "deny", decision, "C15 go: 60 lines .go")

    # Scenario 5: C15 shebang - Write of no-extension file with #! and 60 lines -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content = "#!/usr/bin/env python3\n" + "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "tool"), "content": content})
            check(check_num, "deny", decision, "C15 shebang: no-ext file with #! and 60 lines")

    # Scenario 6: C15/C13 witness - non-code files 60 lines -> allow; small.py 2 lines -> allow
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content60 = "\n".join(f"line{i}" for i in range(60)) + "\n"
            d1, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "notes.md"), "content": content60})
            d2, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "data.txt"), "content": content60})
            d3, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "small.py"), "content": "a = 1\nb = 2\n"})
            check(check_num, "allow", d1, "C15/C13 witness: notes.md 60 lines")
            check_num += 1
            check(check_num, "allow", d2, "C15/C13 witness: data.txt 60 lines")
            check_num += 1
            check(check_num, "allow", d3, "C15/C13 witness: small.py 2 lines")

    # Scenario 7: C13 - Write of one.py with 14 statements on ONE line > 2000 bytes -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            stmt = "; ".join(f"z{i}={i}" for i in range(14))
            # Pad to exceed 2000 bytes
            content = stmt + " # " + "x" * 2000
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "one.py"), "content": content})
            check(check_num, "deny", decision, "C13: one.py 14 stmts one line >2000 bytes")

    # Scenario 8: C18 cumulative - five Write calls of 20 lines each to same file
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            results = []
            for k in range(1, 6):
                content = "\n".join(f"f{k}_{i} = {i}" for i in range(20)) + "\n"
                decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "frag.py"), "content": content})
                results.append((decision, audit[-1] if audit else None))
            expected = ["allow", "allow", "allow", "deny", "deny"]
            expected_labels = ["free_write", "free_write", "free_write", "cumulative", "cumulative"]
            for i, (dec, lbl) in enumerate(results):
                check_num += 1
                check(check_num, expected[i], dec, f"C18 cumulative call {i+1}")
                check_num += 1
                check(check_num, expected_labels[i], lbl, f"C18 cumulative call {i+1} audit label")

    # Scenario 9: C18 witness - single Write of 20 lines to fresh home -> allow
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content = "\n".join(f"o{i} = {i}" for i in range(20)) + "\n"
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "once.py"), "content": content})
            check(check_num, "allow", decision, "C18 witness: single 20-line write")

    # Scenario 10: C18 with Edit - four Edits of 20 lines each to same file (file created directly, not via hook)
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            # Create the file directly (bypassing hook) so it doesn't count in audit
            frag2_path = os.path.join(work, "frag2.py")
            with open(frag2_path, "w", encoding="utf-8") as f:
                f.write("initial\n")
            results = []
            old_content = "initial\n"
            for k in range(1, 5):
                new_string = "\n".join(f"f2_{k}_{i} = {i}" for i in range(20)) + "\n"
                decision, reason, audit = run_hook(home, work, "Edit", {"file_path": frag2_path, "old_string": old_content, "new_string": new_string})
                results.append((decision, audit[-1] if audit else None))
                old_content = new_string
            expected = ["allow", "allow", "allow", "deny"]
            expected_labels = ["free_write", "free_write", "free_write", "cumulative"]
            for i, (dec, lbl) in enumerate(results):
                check_num += 1
                check(check_num, expected[i], dec, f"C18 Edit call {i+1}")
                check_num += 1
                check(check_num, expected_labels[i], lbl, f"C18 Edit call {i+1} audit label")

    # Scenario 11: D8 segment cap - a command cut into more than 1000 segments
    # is refused at once, in under 2 seconds; 100 segments still pass.
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            decision, reason, audit = run_hook(home, work, "Bash", {"command": "rm x; " * 100})
            check(check_num, "allow", decision, "D8 witness: 100 segments")
            check_num += 1
            started = time.time()
            decision, reason, audit = run_hook(home, work, "Bash", {"command": "rm x; " * 3000})
            elapsed = time.time() - started
            check(check_num, "deny", decision, "D8: 3000 segments refused")
            check_num += 1
            check(check_num, True, "more than 1000 segments" in reason, "D8: refusal names the segment cap")
            check_num += 1
            check(check_num, True, elapsed < 2.0, f"D8: refusal in {elapsed:.2f} s (under 2 s)")

    # Scenario 12: D10 extensions - .sql and Makefile count as code; 60-line
    # .md and .csv still pass.
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content60 = "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"
            d1, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "query.sql"), "content": content60})
            check(check_num, "deny", d1, "D10: 60 lines .sql")
            check_num += 1
            d2, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "Makefile"), "content": content60})
            check(check_num, "deny", d2, "D10: 60 lines Makefile")

    # Scenario 13: D10 shebang after a byte-order mark and blank lines -> deny
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content = "\ufeff\n\n#!/usr/bin/env python3\n" + "\n".join(f"x{i} = {i}" for i in range(60)) + "\n"
            decision, reason, audit = run_hook(home, work, "Write", {"file_path": os.path.join(work, "tool_bom"), "content": content})
            check(check_num, "deny", decision, "D10: BOM + blank lines + shebang, 60 lines")

    # Scenario 14: D10 witness - 60-line .md and .csv -> allow
    check_num += 1
    with tempfile.TemporaryDirectory() as home:
        with tempfile.TemporaryDirectory() as work:
            setup_home(home)
            os.makedirs(work, exist_ok=True)
            content60 = "\n".join(f"line{i}" for i in range(60)) + "\n"
            d1, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "notes.md"), "content": content60})
            d2, _, _ = run_hook(home, work, "Write", {"file_path": os.path.join(work, "data.csv"), "content": content60})
            check(check_num, "allow", d1, "D10 witness: notes.md 60 lines")
            check_num += 1
            check(check_num, "allow", d2, "D10 witness: data.csv 60 lines")

    print(f"\nTotal checks: {check_num}, Failures: {failures}")
    return 1 if failures else 0

if __name__ == "__main__":
    sys.exit(main())