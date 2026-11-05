import os
import sys
import json

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")
CFG_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config", "guard.example.json")
sys.path.insert(0, BIN)

import guard_rules  # noqa: E402

with open(CFG_PATH, encoding="utf-8") as f:
    CFG = json.load(f)
CFG["line_threshold"] = 3

SRC4 = "import os\nx = 1\ny = 2\nprint(x + y)"
NB = "/w/analyse.ipynb"


def decide(tool, inp):
    return guard_rules.decide(tool, inp, CFG, [])


def main():
    failures = 0

    r = decide("NotebookEdit", {"notebook_path": NB, "new_source": SRC4, "edit_mode": "replace"})
    ok1 = r["decision"] == "deny" and r["audit"] == "no_receipt"
    print(("PASS" if ok1 else "FAIL") + " 1 NotebookEdit 4 code lines without receipt refused: got " + repr((r["decision"], r["audit"])))
    failures += 0 if ok1 else 1

    r = decide("Write", {"file_path": "/w/analyse.py", "content": SRC4})
    ok2 = r["decision"] == "deny"
    print(("PASS" if ok2 else "FAIL") + " 2 control: Write of 4 code lines in .py refused: got " + repr((r["decision"], r["audit"])))
    failures += 0 if ok2 else 1

    r = decide("NotebookEdit", {"notebook_path": "/w/notes.md", "new_source": SRC4})
    ok3 = r["decision"] == "allow"
    print(("PASS" if ok3 else "FAIL") + " 3 control: NotebookEdit on a non-code target allowed: got " + repr((r["decision"], r["audit"])))
    failures += 0 if ok3 else 1

    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())