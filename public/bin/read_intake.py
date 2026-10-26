import os
import sys
import subprocess
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import receipt_rules
from example_defaults import setting

IMAGES = [".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".tiff", ".heic"]
DOCUMENTS = [".pdf", ".docx", ".xlsx", ".pptx", ".ipynb"]
DECLARE = "declare the read in the delegation log (kind read, target, time, reason)."


def declared_read(records, path, now, minutes):
    if not isinstance(records, list):
        return False
    for r in records:
        if not isinstance(r, dict):
            continue
        if r.get("kind") != "read":
            continue
        if not receipt_rules.same_target(path, r.get("target")):
            continue
        reason = r.get("reason")
        if not isinstance(reason, str) or len(reason.strip()) < 5:
            continue
        t = receipt_rules.to_time(r.get("time"), now.tzinfo)
        if t is None:
            continue
        delta = (now - t).total_seconds()
        if -120 <= delta <= minutes * 60:
            return True
    return False


def check(tool_name, tool_input, config, ctx):
    if tool_name != "Read":
        return (False, "", [])
    path = tool_input.get("file_path")
    if not isinstance(path, str) or path == "":
        return (False, "", [])
    if config.get("intake_active", True) is False:
        return (False, "", [])
    if tool_input.get("limit") is not None or tool_input.get("offset") is not None or tool_input.get("pages"):
        return (False, "", [])
    st = ctx["stat"](path)
    if st is None:
        return (False, "", [])
    lines, size = st
    if declared_read(ctx.get("records"), path, ctx["now"], setting(config, "guard", "read_waiver_minutes")):
        return (False, "", [])
    ext = os.path.splitext(path)[1].lower()
    if ext in config.get("intake_image_extensions", IMAGES):
        return (True, f"Read refused: {path} is an image, which would enter the context whole. To fix: have a local vision model describe it, or {DECLARE}", [path])
    if ext in config.get("intake_document_extensions", DOCUMENTS):
        return (True, f"Read refused: {path} is a {ext} document, which would enter the context whole. To fix: extract its text and have a local model digest it, or {DECLARE}", [path])
    if lines > int(setting(config, "guard", "intake_max_lines")) or size > int(setting(config, "guard", "intake_max_bytes")):
        return (True, f"Read refused: {path} has {lines} lines ({size} bytes), too large to enter whole. To fix: read a targeted part (offset and limit), have a local model digest it, or {DECLARE}", [path])
    return (False, "", [])


# --- Fixtures ---
NOW = datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc)
SIZES = {"/w/small.md": (10, 500), "/w/big.log": (5000, 300000), "/w/wide.json": (3, 70000), "/w/pic.png": (1, 800), "/w/doc.pdf": (10, 5000)}


def STAT(path):
    return SIZES.get(path)


def STAT_CRASH(path):
    raise OSError("disk")


WAIVER = {"kind": "read", "target": "/w/big.log", "time": (NOW - timedelta(minutes=5)).isoformat(), "reason": "need the header"}
OLD_WAIVER = dict(WAIVER, time=(NOW - timedelta(minutes=30)).isoformat())


def R(inp, cfg=None, records=(), tool="Read", stat=STAT):
    recs = None if records is None else list(records)
    return check(tool, inp, {} if cfg is None else cfg, {"stat": stat, "records": recs, "now": NOW})


# --- Autotest ---
def _autotest():
    failures = 0

    # Test 1
    try:
        r1 = R({"file_path": "/w/big.log"})
        assert isinstance(r1, tuple) and len(r1) == 3
        assert r1[0] is True
        assert "5000 lines" in r1[1]
        assert "To fix:" in r1[1]
        assert "offset and limit" in r1[1]
        assert r1[2] == ["/w/big.log"]
        assert R({"file_path": "/w/wide.json"})[0] is True
        assert R({"file_path": "/w/small.md"}) == (False, "", [])
        print(f"PASS 1: expected (True, *'5000 lines'*, ['/w/big.log']) and (False,'',[]); got ({r1[0]}, {r1[2]})")
    except Exception as e:
        print(f"FAIL 1: expected (True, *'5000 lines'*, ['/w/big.log']) and (False,'',[]); got exception: {e}")
        failures += 1

    # Test 2
    try:
        assert R({"file_path": "/w/big.log", "offset": 10, "limit": 20})[0] is False
        assert R({"file_path": "/w/big.log", "limit": 20})[0] is False
        assert R({"file_path": "/w/doc.pdf", "pages": "1-2"})[0] is False
        assert R({"file_path": "/w/missing.md"})[0] is False
        assert R({"file_path": "/w/big.log"}, cfg={"intake_active": False})[0] is False
        assert R({"file_path": "/w/big.log"}, cfg={"intake_max_lines": 10000, "intake_max_bytes": 1000000})[0] is False
        print("PASS 2: expected all 6 calls refuse=False; got all False")
    except Exception as e:
        print(f"FAIL 2: expected all 6 calls refuse=False; got exception: {e}")
        failures += 1

    # Test 3
    try:
        r3a = R({"file_path": "/w/pic.png"})
        assert r3a[0] is True
        assert "image" in r3a[1]
        r3b = R({"file_path": "/w/doc.pdf"})
        assert r3b[0] is True
        assert ".pdf document" in r3b[1]
        r3c = R({"file_path": "/w/pic.png"}, cfg={"intake_image_extensions": []})
        assert r3c[0] is False
        print(f"PASS 3: expected image=True, .pdf document=True, empty-exts=False; got ({r3a[0]}, {r3b[0]}, {r3c[0]})")
    except Exception as e:
        print(f"FAIL 3: expected image=True, .pdf document=True, empty-exts=False; got exception: {e}")
        failures += 1

    # Test 4
    try:
        assert R({"file_path": "/w/big.log"}, records=[WAIVER])[0] is False
        assert R({"file_path": "/w/big.log"}, records=[OLD_WAIVER])[0] is True
        assert R({"file_path": "/w/big.log"}, records=[dict(WAIVER, reason="")])[0] is True
        assert R({"file_path": "/w/big.log"}, records=None)[0] is True
        assert R({"file_path": 5}) == (False, "", [])
        assert R({"command": "cat /w/big.log"}, tool="Bash") == (False, "", [])
        try:
            R({"file_path": "/w/small.md"}, stat=STAT_CRASH)
            raise AssertionError("expected OSError to propagate")
        except OSError:
            pass
        print("PASS 4: expected waiver/old/empty-reason/None/non-str/Bash/crash all correct; got all as expected")
    except Exception as e:
        print(f"FAIL 4: expected waiver/old/empty-reason/None/non-str/Bash/crash all correct; got exception: {e}")
        failures += 1

    # Test 5
    try:
        proc_notice = subprocess.run(
            [sys.executable, os.path.abspath(__file__), "--notice"],
            capture_output=True, text=True
        )
        assert proc_notice.returncode == 0
        assert proc_notice.stdout.startswith("NAME      read_intake.py")
        proc_usage = subprocess.run(
            [sys.executable, os.path.abspath(__file__)],
            capture_output=True, text=True
        )
        assert proc_usage.returncode == 2
        assert proc_usage.stdout == "usage: read_intake.py --notice | --autotest\n"
        print(f"PASS 5: expected notice rc=0 stdout starts 'NAME' and usage rc=2; got rc={proc_notice.returncode}, rc={proc_usage.returncode}")
    except Exception as e:
        print(f"FAIL 5: expected notice rc=0 and usage rc=2; got exception: {e}")
        failures += 1

    return failures


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print("NAME      read_intake.py - refuses reading a whole file that is too large, an image or a heavy document: it would enter the context whole.")
        print("READS     nothing: pure module; the caller passes the tool call, the settings and ctx (stat(path) giving (lines, bytes) or None, records, now).")
        print('WRITES    nothing: check() returns (refuse, reason, targets); every refusal ends with "To fix:" and names the targeted read and the declared read.')
        print("EXAMPLE   python3 read_intake.py --notice")
        print("PITFALLS  2026-09-26 the old check passed a file it could not measure, and its waiver was a separate file consumed by a write.")
        print("          A failed measure now refuses; a waiver is a read declared in the delegation log, valid 15 minutes.")
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        failures = _autotest()
        sys.exit(0 if failures == 0 else 1)
    else:
        print("usage: read_intake.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "read_intake", sys.argv[1:])
