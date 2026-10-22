import os
import sys
import subprocess
import tempfile
import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import digest_rules
import read_intake
import read_quarantine

CHECKS = [("quarantine_read", read_quarantine.check), ("intake", read_intake.check), ("digest", digest_rules.check)]

_CHECKS_MAP = {name: fn for name, fn in CHECKS}

NOTICE = (
    "NAME      guard_checks.py - builds the entry checks run by guard_rules.decide (read quarantine, intake, digest) and measures files for them.\n"
    "READS     the size and the line count of the files the checks ask about; nothing else.\n"
    "WRITES    nothing: build() returns the (name, check) list; an unknown check name gives a check that fails, so the guard refuses.\n"
    "EXAMPLE   python3 guard_checks.py --notice\n"
    "PITFALLS  2026-09-26 a naive guard imported each check apart and ran on without it when the import failed.\n"
    "          A missing module stops the hook that imports this file, and an unknown check name refuses every call.\n"
)

USAGE = "usage: guard_checks.py --notice | --autotest"


def file_stat(path):
    if not os.path.isfile(path):
        return None
    size = os.path.getsize(path)
    lines = 0
    last_byte = None
    with open(path, "rb") as f:
        while True:
            block = f.read(1048576)
            if not block:
                break
            lines += block.count(b"\n")
            last_byte = block[-1:]
    if size > 0 and last_byte != b"\n":
        lines += 1
    return (lines, size)


def build(settings, records, cwd=None, now=None, stat=None):
    if cwd is not None and isinstance(cwd, str) and cwd:
        ctx_cwd = cwd
    else:
        ctx_cwd = os.getcwd()
    ctx = {
        "cwd": ctx_cwd,
        "records": records,
        "now": now if now is not None else datetime.datetime.now().astimezone(),
        "stat": stat if stat is not None else file_stat,
    }
    names = settings.get("checks", [n for n, _ in CHECKS])
    result = []
    for name in names:
        if name in _CHECKS_MAP:
            fn = _CHECKS_MAP[name]

            def _check(tool_name, tool_input, config, _f=fn, _ctx=ctx):
                return _f(tool_name, tool_input, config, _ctx)

            result.append((name, _check))
        else:

            def _raise(tool_name, tool_input, config, _n=name):
                raise ValueError(
                    f"unknown check {_n}. To fix: use quarantine_read, intake or digest in the checks setting"
                )

            result.append((name, _raise))
    return result


def _autotest():
    import guard_rules

    CFG = {"code_extensions": [".py"], "line_threshold": 3, "fix_hint": "delegate it."}
    BIG = ("x" * 249 + "\n") * 500
    SMALL = "a\nb\n"

    def K(r):
        return (r["decision"], r["audit"])

    def D(tool, inp, d, records, settings=CFG):
        return guard_rules.decide(tool, inp, settings, records, build(settings, records, cwd=d))

    all_pass = True

    # Test 1
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "small.md"), "wb") as f:
            f.write(SMALL.encode("utf-8"))
        with open(os.path.join(d, "big.log"), "wb") as f:
            f.write(BIG.encode("utf-8"))
        with open(os.path.join(d, "nobreak.txt"), "wb") as f:
            f.write(b"a\nb")
        with open(os.path.join(d, "empty.txt"), "wb") as f:
            f.write(b"")
        expected1 = ((2, 4), (2, 3), (0, 0), None, None, (500, 125000))
        got1 = (
            file_stat(os.path.join(d, "small.md")),
            file_stat(os.path.join(d, "nobreak.txt")),
            file_stat(os.path.join(d, "empty.txt")),
            file_stat(os.path.join(d, "absent.md")),
            file_stat(d),
            file_stat(os.path.join(d, "big.log")),
        )
        if got1 == expected1:
            print(f"PASS 1: expected {expected1} got {got1}")
        else:
            all_pass = False
            print(f"FAIL 1: expected {expected1} got {got1}")

    # Test 2
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "big.log"), "wb") as f:
            f.write(BIG.encode("utf-8"))
        with open(os.path.join(d, "small.md"), "wb") as f:
            f.write(SMALL.encode("utf-8"))
        expected2 = (["quarantine_read", "intake", "digest"], ["digest"], [])
        got2 = (
            [n for n, _ in build(CFG, [], cwd=d)],
            [n for n, _ in build({"checks": ["digest"]}, [], cwd=d)],
            build({"checks": []}, [], cwd=d),
        )
        if got2 == expected2:
            print(f"PASS 2: expected {expected2} got {got2}")
        else:
            all_pass = False
            print(f"FAIL 2: expected {expected2} got {got2}")

    # Test 3
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "big.log"), "wb") as f:
            f.write(BIG.encode("utf-8"))
        with open(os.path.join(d, "small.md"), "wb") as f:
            f.write(SMALL.encode("utf-8"))
        expected3 = (
            ("deny", "refused:intake"),
            ("allow", None),
            ("deny", "refused:digest"),
            ("allow", None),
        )
        got3 = (
            K(D("Read", {"file_path": os.path.join(d, "big.log")}, d, [])),
            K(D("Read", {"file_path": os.path.join(d, "small.md")}, d, [])),
            K(D("Bash", {"command": "sort -rn big.log"}, d, [])),
            K(D("Bash", {"command": "sort -rn small.md"}, d, [])),
        )
        if got3 == expected3:
            print(f"PASS 3: expected {expected3} got {got3}")
        else:
            all_pass = False
            print(f"FAIL 3: expected {expected3} got {got3}")

    # Test 4
    with tempfile.TemporaryDirectory() as d:
        with open(os.path.join(d, "big.log"), "wb") as f:
            f.write(BIG.encode("utf-8"))
        with open(os.path.join(d, "small.md"), "wb") as f:
            f.write(SMALL.encode("utf-8"))
        REC = {
            "time": datetime.datetime.now().astimezone().isoformat(),
            "status": "success",
            "model_answered": "m",
            "target": os.path.join(d, "new.py"),
            "sha256": "x",
        }
        expected4 = (
            ("deny", "refused:quarantine_read"),
            ("deny", "refused:quarantine_read"),
            ("allow", None),
            ("deny", "check_failed:nope"),
        )
        got4 = (
            K(D("Read", {"file_path": os.path.join(d, "new.py")}, d, [REC])),
            K(D("Read", {"file_path": os.path.join(d, "new.py")}, d, None)),
            K(D("Read", {"file_path": os.path.join(d, "other.py")}, d, [REC])),
            K(D("Read", {"file_path": os.path.join(d, "small.md")}, d, [], settings=dict(CFG, checks=["nope"]))),
        )
        if got4 == expected4:
            print(f"PASS 4: expected {expected4} got {got4}")
        else:
            all_pass = False
            print(f"FAIL 4: expected {expected4} got {got4}")

    # Test 5
    p1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True,
    )
    expected5a = (0, True)
    got5a = (p1.returncode, p1.stdout.startswith("NAME      guard_checks.py"))
    p2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True,
        text=True,
    )
    expected5b = (2, "usage: guard_checks.py --notice | --autotest\n")
    got5b = (p2.returncode, p2.stdout)
    expected5 = (expected5a, expected5b)
    got5 = (got5a, got5b)
    if got5 == expected5:
        print(f"PASS 5: expected {expected5} got {got5}")
    else:
        all_pass = False
        print(f"FAIL 5: expected {expected5} got {got5}")

    sys.exit(0 if all_pass else 1)


def _cli():
        if len(sys.argv) == 2 and sys.argv[1] == "--notice":
            sys.stdout.write(NOTICE)
            sys.exit(0)
        elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
            _autotest()
        else:
            sys.stdout.write(USAGE + "\n")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "guard_checks", sys.argv[1:])
