#!/usr/bin/env python3
"""Whitelist of two proven forms that write no code, for shell_rules.py:
1. git restore / git checkout whose content comes from a git object already
   recorded; nothing else git changes its verdict.
2. a cp or mv whose every destination is in a temporary folder and whose
   sources keep the same code extension as their destination (an identical
   copy, a backup).
At the least doubt the old verdict stands: spare() returns False."""

import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_tokens
import safe_vars

NOTICE = (
    "NAME      restore_rules.py - whitelists the two proven forms that write no code: a git restore/checkout whose content comes from a git object, and a cp/mv of code files into a temporary folder keeping the same code extension.\n"
    "READS     nothing: pure module; it works on one simple command and a config dict (code_extensions), with shell_tokens.py and safe_vars.py beside it.\n"
    "WRITES    nothing: spare() returns True only for a proven form, False at the least doubt.\n"
    "EXAMPLE   python3 restore_rules.py --notice\n"
    "PITFALLS  2026-10-05 a destination is compared to the temporary prefixes after normpath, so a .. that leaves them keeps the old verdict; a relative path is never temporary; a variable is resolved only by safe_vars.py.\n"
    "          2026-10-05 a proven restore path is a literal path under a directory that is not a code root (src, lib): a bare file, a ., a whole src/ or lib/ tree keep the old verdict.\n"
)
USAGE = "usage: restore_rules.py --notice | --autotest\n"

TEMP_DIRS = ("/tmp", "/private/tmp", "/var/folders")
RESTORE_OPTS = ("--worktree", "--staged")
# a path the shell expands (a variable, a glob, a brace) is not a proven path: the old verdict stands
DYNAMIC_CHARS = set("$`*?[{")
# the code roots of a project: restoring a whole tree rooted there is a code write
CODE_ROOTS = ("src", "lib")


def _literal(word):
    return not any(c in DYNAMIC_CHARS for c in word)


def _proven_path(word):
    """Return True when the literal path is a place under a directory that is
    not a code root; a bare file, a ., a whole src/ or lib/ tree are not proven.
    A folder named by a trailing slash is such a place (src/ is not)."""
    if not _literal(word):
        return False
    if "/" not in word and not word.endswith("/"):
        return False
    p = os.path.normpath(word)
    if not p or p in (".", ".."):
        return False
    head = p.lstrip("/").split("/", 1)[0]
    if not head:
        return False
    return head not in CODE_ROOTS


def _is_temp(path):
    """Return True when the normalized path is inside a temporary folder;
    a relative path, and a path a .. brings out, are not."""
    p = os.path.normpath(path)
    if not p.startswith("/"):
        return False
    return any(p == d or p.startswith(d + "/") for d in TEMP_DIRS)


def _code_ext(name, exts):
    """Return the code extension the name ends with, or None."""
    base = name.rsplit("/", 1)[-1]
    for ext in exts:
        if base.endswith(ext):
            return ext
    return None


def _git_restore(ops):
    """Return True for: git restore [--source=<ref>|--source <ref>]
    [--worktree|--staged] [--] <paths>; options first, then paths only."""
    i = 0
    n = len(ops)
    paths = 0
    seen_path = False
    while i < n:
        w = ops[i]
        if w == "--":
            i += 1
            continue
        if w.startswith("-"):
            # only the whitelisted options, and only before the first path
            if not seen_path and w in RESTORE_OPTS:
                i += 1
                continue
            if not seen_path and w == "--source":
                i += 2
                continue
            if not seen_path and w.startswith("--source="):
                i += 1
                continue
            return False
        if not _proven_path(w):
            return False
        seen_path = True
        paths += 1
        i += 1
    return paths > 0


def _git_checkout(ops):
    """Return True for: git checkout [<ref>] -- <paths> and for none else."""
    if "--" not in ops:
        return False
    k = ops.index("--")
    before = ops[:k]
    if len(before) > 1 or (before and before[0].startswith("-")):
        return False
    if before and not _literal(before[0]):
        return False
    after = ops[k + 1:]
    return len(after) >= 1 and all(_proven_path(w) for w in after)


def _copy(dest, sources, exts):
    """Return True when every destination is in a temporary folder and every
    source keeps the same code extension as its destination."""
    if not dest or not sources:
        return False
    if not _is_temp(dest):
        return False
    if dest.endswith("/"):
        # a folder: each copy keeps the source's own name, so the extension
        # of every copy is the extension of its source
        return True
    dext = _code_ext(dest, exts)
    if dext is None:
        return False
    return all(_code_ext(s, exts) == dext for s in sources)


def spare(seg, config):
    """Return True when the simple command seg is a proven form that writes
    no code; the old verdict stands at the least doubt."""
    try:
        exts = list(config.get("code_extensions", []))
        # a variable bound earlier in the same chain to a literal path (safe_vars.py)
        seg = safe_vars.resolve(seg)
        tokens = shell_tokens.tokenize(seg)
        if tokens is None:
            return False
        plain = shell_tokens.redirections(tokens, exts)[2]
        if not plain:
            return False
        head = plain[0].rsplit("/", 1)[-1]
        args = plain[1:]
        if head == "git":
            if args[:1] == ["-C"]:
                args = args[2:]
            sub = ""
            rest = []
            for i, w in enumerate(args):
                if not w.startswith("-"):
                    sub = w
                    rest = args[i + 1:]
                    break
            if sub == "restore":
                return _git_restore(rest)
            if sub == "checkout":
                return _git_checkout(rest)
            return False
        if head in ("cp", "mv"):
            nonopt = [a for a in args if not a.startswith("-")]
            if len(nonopt) < 2:
                return False
            return _copy(nonopt[-1], nonopt[:-1], exts)
        return False
    except Exception:
        return False


def _autotest():
    CFG = {"code_extensions": [".py", ".sh"], "delegate_tools": []}
    fixtures = [
        ("git restore --source=n1 --worktree -- public/examples/", True),
        ("git restore --source=n1 -- public/examples/", True),
        ("git restore --staged public/bin/a.py", True),
        ("git restore public/bin/a.py", True),
        ("git restore a.py", False),  # a bare file is not a proven place
        ("git restore .", False),  # the whole worktree is not proven
        ("git restore -- .", False),
        ("git restore src/", False),  # a code root tree is a code write
        ("git restore --source=HEAD~2 lib/", False),
        ("git restore src/a.js", False),
        ("git restore --overlay a.py", False),
        ("git apply p.diff", False),
        ("git checkout -- public/bin/a.py", True),
        ("git checkout n1 -- bin/", True),
        ("git checkout n1 -- public/data/a.json", True),
        ("git checkout -- .", False),  # the whole worktree is not proven
        ("git checkout .", False),
        ("git checkout HEAD -- src/", False),
        ("git checkout -- src/a.js", False),
        ("git checkout -b x", False),
        ("git checkout a.py", False),
        ("git checkout n1 a.py", False),
        ("git restore $F", False),  # a path the shell expands is not proven
        ("git checkout HEAD~1 -- '*.py'", False),  # a glob path is not proven
        ("git checkout $B -- a.py", False),  # a ref the shell expands is not proven
        ("git -C x checkout -- a.py", False),
        ("git mv a.py b.py", False),
        ("cp bin/a.py /tmp/w/a.py", True),
        ("mv bin/b.py /tmp/w/b.py", True),
        ("cp bin/a.py /var/folders/t/w/a.py", True),
        ("cp bin/a.py $B/", False),  # an unresolved $B is not a temporary literal
        ('cp a.py "$B/a.py"', False),  # a quoted, unresolved $B keeps the old verdict
        ("cp bin/a.py /private/tmp/w/s/", True),
        ("cp notes.txt /tmp/b.py", False),
        ("cp /tmp/a.py bin/a.py", False),
        ("cp /tmp/a.py /tmp/../opt/x/bin/a.py", False),
        ("cp a.py rel/a.py", False),
        ("cp /tmp/a.py /tmp/b.sh", False),
        ("cp -f /tmp/a.py /tmp/w/a.py", True),
    ]
    all_pass = True
    for idx, (fixture, expected) in enumerate(fixtures, 1):
        got = spare(fixture, CFG)
        ok = got == expected
        all_pass = all_pass and ok
        print("PASS" if ok else "FAIL", "fixture {}: expected={} got={}".format(idx, repr(expected), repr(got)))
    # a variable bound earlier in the same command is resolved before spare()
    # sees it (safe_vars.py, applied on the whole command by the caller):
    # the unresolved forms above stay False, the resolved ones pass.
    for idx, resolved_text in enumerate(
            ["cp a.py /tmp/w/a.py", "mv b.py /private/tmp/w/"],
            len(fixtures) + 1):
        got = spare(resolved_text, CFG)
        ok = got is True
        all_pass = all_pass and ok
        print("PASS" if ok else "FAIL", "fixture {}: expected=True got={}".format(idx, repr(got)))
    p = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True, text=True,
    )
    ok = p.returncode == 0 and p.stdout.startswith("NAME      restore_rules.py")
    all_pass = all_pass and ok
    print("PASS" if ok else "FAIL", "notice: expected rc=0 and NAME line, got rc={} start={}".format(p.returncode, repr(p.stdout[:40])))
    p = subprocess.run([sys.executable, os.path.abspath(__file__)], capture_output=True, text=True)
    ok = p.returncode == 2 and p.stdout == USAGE
    all_pass = all_pass and ok
    print("PASS" if ok else "FAIL", "usage: expected rc=2, got rc={} out={}".format(p.returncode, repr(p.stdout)))
    return 0 if all_pass else 1


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "restore_rules", sys.argv[1:])
