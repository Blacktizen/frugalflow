#!/usr/bin/env python3
import os
import re
import sys
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_quotes

AGGREGATION = [re.compile(r"\bgrep\s+-\S*o"), re.compile(r"\buniq\s+-c\b"), re.compile(r"\bsort\s+-rn\b"), re.compile(r"\bsort\s+-n\s*\|\s*uniq\b")]
DYNAMIC = re.compile(r"(?s)[*`]|(?<!\$)\?|\$(?!\?)|<<|\b(?:find|rg|du)\b|\bgrep\b[^|;&]*\s-\w*[rR]|\bcd\b.*\bcd\b")  # lang-ok: du is the disk usage command
REDIRECT = re.compile(r"\d*>>?&?\s*[^\s|&;]+")


def material(masked, exts):
    if not exts:
        return []
    pattern = r"[^\s|&;]+(?:" + "|".join(re.escape(e) for e in exts) + r")\b"
    text = REDIRECT.sub(" ", masked)
    return [m.group(0).lstrip("<(") for m in re.finditer(pattern, text)]


def aggregates(masked, command):
    for pat in AGGREGATION:
        if pat.search(masked):
            return True
    # awk_calls judges every awk call; only an awk printing fields of an ls listing passes.
    try:
        import awk_calls
        return awk_calls.digests(command)
    except Exception:
        return bool(re.search(r"\bawk\b", masked) and re.search(r"\bprint\b", command))


def exempt(masked, command):
    # an exemption covers one lone command, outside comments; after ;, &&, ||, & or a new line all is judged.
    if re.search(r"[;\n]|&&|\|\||(?<![|>&])&(?![>&])", masked):
        return False
    if re.search(r"(?:^|[\s;&|])git(?=\s|$)", masked):
        return True
    if "--autotest" in masked or "--verify" in masked:
        return True
    m = re.match(r"^\s*(?:python3|bash)\s+(\S+)", masked)
    if m and not m.group(1).startswith(("-", "<")):
        return True
    return False


def waived(command, marker):
    m = re.search(r"#\s*" + re.escape(marker) + r":\s*(.+)", command)
    return m is not None and len(m.group(1).strip()) >= 10


def small_files(masked, config, ctx):
    m = REDIRECT.sub(" ", masked)
    if DYNAMIC.search(m):
        return False
    cd = re.match(r"\s*cd\s+(\S+)\s*&&", m)
    base = os.path.expanduser(cd.group(1)) if cd else ctx["cwd"]
    exts = config.get("digest_extensions", [".md", ".log", ".txt", ".jsonl"])
    paths = set(os.path.normpath(os.path.join(base, os.path.expanduser(t))) for t in material(masked, exts))
    if not paths:
        return False
    sizes = [ctx["stat"](p) for p in sorted(paths)]
    if any(s is None for s in sizes):
        return False
    return sum(s[1] for s in sizes) < int(config.get("digest_max_bytes", 98304))


def check(tool_name, tool_input, config, ctx):
    if tool_name != "Bash":
        return (False, "", [])
    cmd = tool_input.get("command")
    if not isinstance(cmd, str):
        return (False, "", [])
    marker = config.get("digest_waiver", "manual-digest")
    exts = config.get("digest_extensions", [".md", ".log", ".txt", ".jsonl"])
    masked = shell_quotes.mask_quotes(shell_quotes.strip_comments(cmd))
    if exempt(masked, cmd):
        return (False, "", [])
    if waived(cmd, marker):
        return (False, "", [])
    if not aggregates(masked, cmd):
        return (False, "", [])
    targets = material(masked, exts)
    if not targets:
        return (False, "", [])
    if small_files(masked, config, ctx):
        return (False, "", [])
    # a ranking pipeline that ends with head, tail, wc or grep -c prints little; failure: refuse.
    try:
        import bounded_output
        if bounded_output.bounded(cmd):
            return (False, "", [])
    except Exception:
        pass
    max_bytes = int(config.get("digest_max_bytes", 98304))
    reason = (f"Digest refused: this command ranks or extracts the lines of {targets[0]}, "
              f"a large or unknown file; reading it belongs to a model. To fix: have a local model "
              f"digest the file, rank named files under {max_bytes} bytes, or end the command with "
              f"# {marker}: <reason of 10 characters or more>.")
    return (True, reason, targets)


NOTICE = (
    "NAME      digest_rules.py - refuses a shell command that ranks or extracts the lines of a large text file: that digest belongs to a model.\n"
    "READS     nothing: pure module; the caller passes the tool call, the settings and ctx (cwd, and stat(path) giving (lines, bytes) or None).\n"
    "WRITES    nothing: check() returns (refuse, reason, targets); every refusal ends with \"To fix:\" and names the waiver comment.\n"
    "EXAMPLE   python3 digest_rules.py --notice\n"
    "PITFALLS  2026-09-26 the old check refused grep -c on a small note: named, ordinary files under the size limit now pass.\n"
    "          A glob, a variable, a heredoc, find or grep -r cannot be sized: the ranking is refused, as before.\n"
    "          2026-09-26 a pure count (grep -c, wc -l) prints only numbers: it passes whatever the size (operator decision).\n"
)


def _autotest():
    SIZES = {"/w/small.md": (10, 500), "/w/big.jsonl": (9000, 2500000), "/w/notes/a.md": (20, 900)}

    def STAT(path):
        return SIZES.get(path)

    def STAT_CRASH(path):
        raise OSError("disk")

    CTX = {"cwd": "/w", "stat": STAT}
    CFG = {}

    def R(cmd, cfg=None, ctx=None):
        return check("Bash", {"command": cmd}, CFG if cfg is None else cfg, CTX if ctx is None else ctx)[0]

    all_pass = True

    # Test 1
    try:
        res = check("Bash", {"command": "sort -rn big.jsonl"}, CFG, CTX)
        ok = (isinstance(res, tuple) and len(res) == 3
              and res[0] is True and res[2] == ["big.jsonl"]
              and "To fix:" in res[1] and "# manual-digest:" in res[1]
              and R("grep -oh x /w/big.jsonl") is True
              and R("awk '/E/ {print}' big.jsonl") is True
              and R("cat missing.md | sort | uniq -c") is True
              and R("grep -c x big.jsonl") is False
              and R("wc -l /w/big.jsonl") is False)
        if not ok:
            print(f"FAIL 1: expected (True, reason w/ 'To fix:' and '# manual-digest:', ['big.jsonl']) + 5 sub-assertions, got refuse={res[0]} targets={res[2]}")
            all_pass = False
        else:
            print("PASS 1: refuse=True targets=['big.jsonl'], all sub-assertions hold")
    except Exception as e:
        print(f"FAIL 1: expected tuple of 3 elements, got exception {type(e).__name__}: {e}")
        all_pass = False

    # Test 2
    try:
        ok = (R("sort -rn small.md") is False
              and R("cd /w/notes && sort -rn a.md") is False
              and R("sort -rn small.md big.jsonl") is True
              and R("sort -rn *.md") is True
              and R("sort -rn small.md", cfg={"digest_max_bytes": 100}) is True
              and R("sort -rn small.md > out.txt") is False
              and R("grep -c x *.md") is False)
        if not ok:
            print(f"FAIL 2: expected [F,F,T,T,T,F,F], got [{R('sort -rn small.md')},{R('cd /w/notes && sort -rn a.md')},{R('sort -rn small.md big.jsonl')},{R('sort -rn *.md')},{R('sort -rn small.md',cfg={'digest_max_bytes':100})},{R('sort -rn small.md > out.txt')},{R('grep -c x *.md')}]")
            all_pass = False
        else:
            print("PASS 2: small files pass, large/glob/override refuse, redirect and pure count pass")
    except Exception as e:
        print(f"FAIL 2: expected 7 booleans, got exception {type(e).__name__}: {e}")
        all_pass = False

    # Test 3
    try:
        ok = (R("git log | sort -rn") is False
              and R("python3 run.py big.jsonl | sort -rn") is False
              and R("sort -rn big.jsonl # manual-digest: checking one announced figure") is False
              and R("sort -rn big.jsonl # manual-digest: short") is True
              and R('grep -rln "sort -rn" big.jsonl') is False
              and R("sort -rn main.py") is False
              and R('echo "sort -rn big.jsonl"') is False)
        if not ok:
            got3 = [R("git log | sort -rn"),
                    R("python3 run.py big.jsonl | sort -rn"),
                    R("sort -rn big.jsonl # manual-digest: checking one announced figure"),
                    R("sort -rn big.jsonl # manual-digest: short"),
                    R('grep -rln "sort -rn" big.jsonl'),
                    R("sort -rn main.py"),
                    R('echo "sort -rn big.jsonl"')]
            print("FAIL 3: expected [F,F,F,T,F,F,F], got [" + ",".join(str(v) for v in got3) + "]")
            all_pass = False
        else:
            print("PASS 3: exemptions, waivers, grep -r, non-ext and quoted commands all pass")
    except Exception as e:
        print(f"FAIL 3: expected 7 booleans, got exception {type(e).__name__}: {e}")
        all_pass = False

    # Test 4
    try:
        ok = (check("Read", {"file_path": "/w/big.jsonl"}, CFG, CTX) == (False, "", [])
              and check("Bash", {"command": 5}, CFG, CTX) == (False, "", [])
              and R("sort -rn big.jsonl # skip-digest: checking one announced figure", cfg={"digest_waiver": "skip-digest"}) is False)
        try:
            R("sort -rn small.md", ctx={"cwd": "/w", "stat": STAT_CRASH})
            ok = False
        except OSError:
            pass
        if not ok:
            print("FAIL 4: expected (False,'',[]) x2, waiver pass, and OSError from STAT_CRASH")
            all_pass = False
        else:
            print("PASS 4: non-Bash and non-str pass, custom waiver works, OSError propagates")
    except Exception as e:
        print(f"FAIL 4: expected clean results + OSError, got exception {type(e).__name__}: {e}")
        all_pass = False

    # Test 5
    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        ok_notice = proc.returncode == 0 and proc.stdout.startswith("NAME      digest_rules.py")
        proc2 = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
        ok_usage = proc2.returncode == 2 and proc2.stdout == "usage: digest_rules.py --notice | --autotest\n"
        ok = ok_notice and ok_usage
        if not ok:
            print(f"FAIL 5: expected notice code=0 stdout starts 'NAME      digest_rules.py' and no-arg code=2 stdout=usage, got notice_code={proc.returncode} usage_code={proc2.returncode}")
            all_pass = False
        else:
            print("PASS 5: --notice exits 0 with correct header, no-arg exits 2 with usage line")
    except Exception as e:
        print(f"FAIL 5: expected subprocess results, got exception {type(e).__name__}: {e}")
        all_pass = False

    sys.exit(0 if all_pass else 1)


def _cli():
        if len(sys.argv) == 2 and sys.argv[1] == "--notice":
            sys.stdout.write(NOTICE)
            sys.exit(0)
        elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
            _autotest()
        else:
            print("usage: digest_rules.py --notice | --autotest")
            sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "digest_rules", sys.argv[1:])
