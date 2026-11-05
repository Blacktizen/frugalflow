#!/usr/bin/env python3
NOTICE = (
    "NAME      e2e_same_target.py - end-to-end tests for receipt_rules.same_target and content_verdict with absolute targets.\n"
    "READS     nothing: creates temporary files under /tmp.\n"
    "WRITES    a temporary directory under /tmp, removed on exit; --notice writes nothing.\n"
    "EXAMPLE   python3 public/tests/e2e_same_target.py [--notice]\n"
    "PITFALLS  2026-11-05 a bare-name edit target covered any file of the same name; same_target now needs equal absolute paths.\n"
)

import os
import sys
import tempfile
import shutil
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "bin"))
import receipt_rules


def fingerprint(text):
    if isinstance(text, bytes):
        data = text
    else:
        data = str(text).encode("utf-8")
    import hashlib
    return hashlib.sha256(data).hexdigest()


def main():
    all_ok = True
    lines = []

    # Create a temporary directory for the test
    with tempfile.TemporaryDirectory(prefix="e2e_same_target_") as tmpdir:
        # Create subdirectories
        w_dir = os.path.join(tmpdir, "w")
        other_dir = os.path.join(w_dir, "other")
        os.makedirs(other_dir)

        # --- Case 1: same_target with bare name should be False ---
        # Test that same_target("/w/other/a.py", "a.py") is False
        # (relative "a.py" resolves against cwd, not against the target's directory)
        abs_target = os.path.join(other_dir, "a.py")
        # The bare name "a.py" resolves to cwd/a.py, not to other_dir/a.py
        # Since we don't control cwd here, we test the absolute path comparison directly:
        # same_target(abs_target, "a.py") should be False because abspath("a.py") != abs_target
        # (unless cwd happens to be other_dir, which it won't be)
        try:
            result = receipt_rules.same_target(abs_target, "a.py")
            if result is False:
                lines.append("PASS case 1: same_target(abs_other_a, 'a.py') is False")
            else:
                lines.append(f"FAIL case 1: expected False, got {result}")
                all_ok = False
        except Exception as exc:
            lines.append(f"FAIL case 1: exception {type(exc).__name__}: {exc}")
            all_ok = False

        # --- Case 2: content_verdict with divergent (edit target differs) ---
        # Receipt for <tmp>/a.py with sha256 of "x\n"
        # Edit declaration targets <tmp>/other/a.py (different file)
        # Write content "y\n" to <tmp>/a.py -> should be "divergent"
        target_file = os.path.join(w_dir, "a.py")
        edit_target = os.path.join(other_dir, "a.py")
        now = datetime.now(timezone.utc)
        receipt_time = (now - timedelta(minutes=3)).isoformat()
        edit_time = (now - timedelta(minutes=5)).isoformat()

        receipt = {
            "time": receipt_time,
            "status": "success",
            "model_answered": "m",
            "target": target_file,
            "sha256": fingerprint("x\n"),
        }
        edit_decl = {
            "kind": "edit",
            "target": edit_target,  # Different from target_file
            "time": edit_time,
            "reason": "r",
        }

        try:
            verdict = receipt_rules.content_verdict(
                [receipt, edit_decl], target_file, "y\n", now
            )
            if verdict == "divergent":
                lines.append("PASS case 2a: content_verdict with different edit target -> divergent")
            else:
                lines.append(f"FAIL case 2a: expected 'divergent', got '{verdict}'")
                all_ok = False
        except Exception as exc:
            lines.append(f"FAIL case 2a: exception {type(exc).__name__}: {exc}")
            all_ok = False

        # --- Case 3: content_verdict with declared_edit (edit target matches) ---
        # Same receipt, but edit declaration targets the same file <tmp>/a.py
        # Write content "y\n" -> should be "declared_edit"
        edit_decl_same = {
            "kind": "edit",
            "target": target_file,  # Same as target_file
            "time": edit_time,
            "reason": "r",
        }

        try:
            verdict = receipt_rules.content_verdict(
                [receipt, edit_decl_same], target_file, "y\n", now
            )
            if verdict == "declared_edit":
                lines.append("PASS case 3: content_verdict with matching edit target -> declared_edit")
            else:
                lines.append(f"FAIL case 3: expected 'declared_edit', got '{verdict}'")
                all_ok = False
        except Exception as exc:
            lines.append(f"FAIL case 3: exception {type(exc).__name__}: {exc}")
            all_ok = False

    for ln in lines:
        print(ln)

    if not all_ok:
        print("FAILURE")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    main()