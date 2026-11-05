#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""E2E test: NOTICE block content and placement checks."""

import os
import sys


def main():
    # 1. ROOT = parent of public/tests, TOOL = ROOT/bin/frugalflow.py
    ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    TOOL = os.path.join(ROOT, "bin", "frugalflow.py")

    # 2. BANNED = "never in the " + "user settings" (concatenated)
    BANNED = "never in the " + "user settings"

    # 3. Read TOOL, extract NOTICE block between "NOTICE = (" and first "\n)\n"
    with open(TOOL, "r", encoding="utf-8") as fh:
        tool_text = fh.read()

    start_marker = "NOTICE = ("
    end_marker = "\n)\n"
    start_idx = tool_text.find(start_marker)
    if start_idx == -1:
        print("FAIL Check 1: NOTICE block start marker not found")
        print("FAIL Check 2: NOTICE block start marker not found")
        print("FAIL Check 3: NOTICE block start marker not found")
        print("E2E NOTICE PLACES 0/3")
        return 1

    start_idx += len(start_marker)
    end_idx = tool_text.find(end_marker, start_idx)
    if end_idx == -1:
        print("FAIL Check 1: NOTICE block end marker not found")
        print("FAIL Check 2: NOTICE block end marker not found")
        print("FAIL Check 3: NOTICE block end marker not found")
        print("E2E NOTICE PLACES 0/3")
        return 1

    notice_block = tool_text[start_idx:end_idx]

    # 4. Check 1: BANNED absent from TOOL, *.md at ROOT, *.md under ROOT/docs
    check1_pass = True
    check1_failures = []

    # Check TOOL
    if BANNED in tool_text:
        check1_pass = False
        check1_failures.append(os.path.relpath(TOOL, ROOT))

    # Check *.md at ROOT
    for fname in os.listdir(ROOT):
        if fname.endswith(".md"):
            fpath = os.path.join(ROOT, fname)
            with open(fpath, "r", encoding="utf-8") as fh:
                if BANNED in fh.read():
                    check1_pass = False
                    check1_failures.append(os.path.relpath(fpath, ROOT))

    # Check *.md under ROOT/docs (os.walk)
    docs_dir = os.path.join(ROOT, "docs")
    if os.path.isdir(docs_dir):
        for dirpath, _dirnames, filenames in os.walk(docs_dir):
            for fname in filenames:
                if fname.endswith(".md"):
                    fpath = os.path.join(dirpath, fname)
                    with open(fpath, "r", encoding="utf-8") as fh:
                        if BANNED in fh.read():
                            check1_pass = False
                            check1_failures.append(os.path.relpath(fpath, ROOT))

    if check1_pass:
        print("PASS Check 1: BANNED phrase absent from TOOL, root *.md, docs/*.md")
    else:
        print("FAIL Check 1: BANNED phrase found in:")
        for f in check1_failures:
            print("  " + f)

    # 5. Check 2: "new-project" and "<project>/.claude/settings.json" in NOTICE block
    check2_pass = (
        "new-project" in notice_block
        and "<project>/.claude/settings.json" in notice_block
    )
    if check2_pass:
        print('PASS Check 2: "new-project" and "<project>/.claude/settings.json" in NOTICE')
    else:
        print('FAIL Check 2: "new-project" and/or "<project>/.claude/settings.json" missing from NOTICE')

    # 6. Check 3: "init" and "~/.claude/settings.json" in NOTICE block
    check3_pass = (
        "init" in notice_block
        and "~/.claude/settings.json" in notice_block
    )
    if check3_pass:
        print('PASS Check 3: "init" and "~/.claude/settings.json" in NOTICE')
    else:
        print('FAIL Check 3: "init" and/or "~/.claude/settings.json" missing from NOTICE')

    # 7. Summary
    passed = sum([check1_pass, check2_pass, check3_pass])
    print("E2E NOTICE PLACES {}/3".format(passed))
    return 0 if passed == 3 else 1


if __name__ == "__main__":
    sys.exit(main())