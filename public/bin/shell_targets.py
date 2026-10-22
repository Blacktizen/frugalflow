#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import re
import shlex
import sys
import subprocess

# Import shell_tokens from the same directory
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_tokens
import command_head

CODE_FLAGS = {
    "python3": ("-c",),
    "node": ("-e", "-p", "--eval"),
    "ruby": ("-e",),
    "php": ("-r",),
    "perl": ("-e", "-E")
}
SHELLS = {"sh", "bash", "zsh", "dash", "ksh"}
FREE_KEYWORDS = {"for", "case", "esac", "done", "fi", "function", "select", "in"}

NOTICE = """NAME      shell_targets.py - judges one simple shell command: which code files it writes, whether that cannot be known, and which inline code must be judged apart.
READS     nothing: pure module; it works on the command and on a config dict (code_extensions, delegate_tools), with shell_tokens.py beside it.
WRITES    nothing: judge_segment() returns verdict, targets, reason, head and nested.
EXAMPLE   python3 shell_targets.py --notice
PITFALLS  2026-09-25 an exemption matched anywhere in the command, even in a comment: a delegation tool is now recognised only as the command itself.
          A command that writes files it cannot name (git apply, tar x, unzip, patch) is unknown, never free.
          2026-09-27 the sed script was judged as a file: a backquote inside it made a notes edit unknown; the script is skipped, the files are judged.
          2026-10-03 git mv SOURCE DEST is judged like mv: a DEST with a code extension is a write to DEST.
"""
USAGE = "usage: shell_targets.py --notice | --autotest\n"

def judge_segment(seg, config):
    exts = list(config.get("code_extensions", []))
    delegates = set(config.get("delegate_tools", []))

    tokens = shell_tokens.tokenize(seg)
    if tokens is None:
        return {"verdict": "unknown", "targets": ["<unknown>"], "reason": "unreadable", "head": "", "nested": None}

    # input redirections (<f, <<M, <<<x) are not words of the command: sudo -s <<M hid the shell.
    ops = [k for k, t in enumerate(tokens) if re.match(r"\d*<", t)]
    gone = set(ops) | {k + 1 for k in ops if re.fullmatch(r"\d*<(<-?|<<|&)?", tokens[k])}
    tokens = [t for k, t in enumerate(tokens) if k not in gone]

    raw = tokens
    tokens, sure = command_head.skip(tokens)
    if not sure:  # an unknown prefix option: the real command cannot be read
        return {"verdict": "unknown", "targets": ["<unknown>"], "reason": "unknown prefix option", "head": "", "nested": None}
    via_xargs = any(w in ("xargs", "parallel") for w in raw[:len(raw) - len(tokens)])
    if not tokens:
        return {"verdict": "free", "targets": [], "reason": "empty", "head": "", "nested": None}

    head = tokens[0].rsplit("/", 1)[-1]
    if re.fullmatch(r"python3?(\.\d+)?", head):
        head = "python3"

    targets, unknown, plain = shell_tokens.redirections(tokens, exts)
    reason = "redirection" if (targets or unknown) else ""

    args = plain[1:]
    nonopt = [a for a in args if not a.startswith("-")]
    nested = None

    def add(t, why):
        nonlocal targets, unknown, reason
        c = shell_tokens.classify_target(t, exts)
        if c == "code" and t not in targets:
            targets.append(t)
        elif c == "unknown":
            unknown = True
        if c is not None and reason == "":
            reason = why

    # Rules that apply only when head is neither a free keyword nor a delegation tool
    if head not in FREE_KEYWORDS and head not in delegates:
        if head in ("tee", "truncate"):
            for a in nonopt:
                add(a, head)

        elif head in ("cp", "mv", "install", "ln"):
            if len(nonopt) >= 2:
                dest = nonopt[-1]
                if shell_tokens.classify_target(dest, exts) is not None:
                    add(dest, "copy")
                else:
                    if dest.endswith("/") or (dest.rsplit("/", 1)[-1] and "." not in dest.rsplit("/", 1)[-1]):
                        for s in nonopt[:-1]:
                            if shell_tokens.classify_target(s, exts) == "code":
                                add(dest.rstrip("/") + "/" + s.rsplit("/", 1)[-1], "copy")
                                break

        elif head == "dd":
            for a in args:
                if a.startswith("of="):
                    add(a[3:], "dd")

        elif head == "curl":
            for k, a in enumerate(args):
                if (a == "-o" or a == "--output") and k + 1 < len(args):
                    add(args[k+1], "download")
                elif a.startswith("--output="):
                    add(a[9:], "download")
                elif a.startswith("-o") and len(a) > 2 and not a.startswith("--"):
                    add(a[2:], "download")

        elif head == "wget":
            for k, a in enumerate(args):
                if (a == "-O" or a == "--output-document") and k + 1 < len(args):
                    add(args[k+1], "download")
                elif a.startswith("--output-document="):
                    add(a[18:], "download")
                elif a.startswith("-O") and len(a) > 2 and not a.startswith("--"):
                    add(a[2:], "download")

        elif head == "sed":
            inplace = any(a == "--in-place" or a.startswith("-i") or a.startswith("--in-place=") for a in args)
            if inplace:
                scripts = {k + 1 for k, a in enumerate(args) if a in ("-e", "-f", "--expression", "--file")}
                files = [a for k, a in enumerate(args) if k not in scripts and a and not a.startswith("-")]
                for a in (files if scripts else files[1:]):
                    add(a, "in-place edit")

        elif head == "perl":
            inplace = any(a.startswith("-") and not a.startswith("--") and "i" in a[1:] for a in args)
            if inplace:  # the -e program is not a file; without -e the first word is the program file
                progs = {k + 1 for k, a in enumerate(args) if re.fullmatch(r"-[^-]*[eE]", a)}
                files = [a for k, a in enumerate(args) if k not in progs and not a.startswith("-")]
                for a in (files if any(re.match(r"-[^-]*[eE]", a) for a in args) else files[1:]):
                    add(a, "in-place edit")
            if head in CODE_FLAGS:
                for k, a in enumerate(args):
                    if a in CODE_FLAGS[head] and k + 1 < len(args):
                        nested = {"kind": "code", "text": args[k+1]}
                        break

        elif head in CODE_FLAGS:
            for k, a in enumerate(args):
                if a in CODE_FLAGS[head] and k + 1 < len(args):
                    nested = {"kind": "code", "text": args[k+1]}
                    break

        elif head in SHELLS:
            for k, a in enumerate(args):
                if re.fullmatch(r"-[a-zA-Z]*c", a) and k + 1 < len(args):
                    nested = {"kind": "command", "text": args[k+1]}
                    break

        elif head == "eval":
            if args:
                nested = {"kind": "command", "text": " ".join(args)}

        elif head in ("awk", "gawk"):
            if nonopt:
                prog = nonopt[0]
                for m in re.finditer(r'>>?\s*"([^"]+)"', prog):
                    add(m.group(1), "awk")
                for m in re.finditer(r">>?\s*([^\s\"';}()]+)", prog):
                    add(m.group(1), "awk")

        elif head == "git":
            a = args
            if a[:1] == ["-C"]:
                a = a[2:]
            sub = ""
            rest = []
            for i, w in enumerate(a):
                if not w.startswith("-"):
                    sub = w
                    rest = a[i+1:]
                    break

            if sub in ("apply", "am"):
                unknown = True
                if reason == "":
                    reason = "git"
            elif sub == "stash" and rest and rest[0] in ("pop", "apply"):
                unknown = True
                if reason == "":
                    reason = "git"
            elif sub in ("restore", "checkout"):
                for r in rest:
                    add(r, "git")
                for r in rest:  # git checkout . and git checkout -p passed
                    if r in ("-p", "--patch") or (r != "--" and not r.startswith("-") and (r == "." or r.endswith("/"))):
                        unknown = True
                        if reason == "":
                            reason = "git"
                        break
            elif sub == "mv":
                # git mv SOURCE DEST creates a code file when DEST has a code extension; the rename is a write to DEST.
                nonopts = [w for w in rest if not w.startswith("-")]
                if len(nonopts) >= 2:
                    dest = nonopts[-1]
                    if shell_tokens.classify_target(dest, exts) is not None:
                        add(dest, "git")
                    else:
                        if dest.endswith("/") or (dest.rsplit("/", 1)[-1] and "." not in dest.rsplit("/", 1)[-1]):
                            for s in nonopts[:-1]:
                                if shell_tokens.classify_target(s, exts) == "code":
                                    add(dest.rstrip("/") + "/" + s.rsplit("/", 1)[-1], "git")
                                    break

        elif head == "tar":
            if any((a.startswith("-") and not a.startswith("--") and "x" in a) or a.startswith("--extract") for a in args) or \
               (args and re.fullmatch(r"[a-zA-Z]+", args[0]) and "x" in args[0]):
                unknown = True
                if reason == "":
                    reason = "archive"

        elif head == "unzip":
            unknown = True
            if reason == "":
                reason = "archive"

        elif head == "patch":
            unknown = True
            if reason == "":
                reason = "patch"

        elif head == "rsync":
            if nonopt and shell_tokens.classify_target(nonopt[-1], exts) == "code":
                add(nonopt[-1], "sync")
            elif len(nonopt) >= 2:
                unknown = True
                if reason == "":
                    reason = "sync"

        elif head == "find":
            stops = ("-exec", "-execdir", "-ok", "-okdir", ";", "\\;", "+")
            ex = [k for k, a in enumerate(args) if a in stops[:4]]
            if ex:  # every -exec command is judged; its terminators become separators
                nested = {"kind": "command", "text": " ".join(";" if a in stops else shlex.quote(a) for a in args[ex[0]:])}
            for k, a in enumerate(args[:-1]):
                if a in ("-fprint", "-fprint0", "-fprintf", "-fls"):
                    add(args[k + 1], "find output")

        # xargs adds targets read from stdin: a writer under it has targets nobody can read
        in_place = head in ("sed", "perl") and any(a.startswith("-i") or a.startswith("--in-place") or (head == "perl" and a.startswith("-") and "i" in a[1:]) for a in args)
        if via_xargs and (in_place or head in ("tee", "truncate", "cp", "mv", "install", "ln", "dd")):
            unknown = True
            reason = reason or "xargs"

    if head in delegates and reason == "":
        reason = "delegation tool"

    if unknown:
        verdict = "unknown"
        targets = targets + ["<unknown>"]
    elif targets:
        verdict = "write"
    elif nested:
        verdict = "nested"
    else:
        verdict = "free"

    if reason == "":
        reason = "nested" if nested else "free"

    return {"verdict": verdict, "targets": targets, "reason": reason, "head": head, "nested": nested}

# --- Fixtures for the self-test ---
CFG = {"code_extensions": [".py", ".sh"], "delegate_tools": ["deleg-tool"]}
def V(seg):
    r = judge_segment(seg, CFG)
    return (r["verdict"], r["targets"])
U = ("unknown", ["<unknown>"])
F = ("free", [])

def check_keys():
    r = judge_segment("printf x", CFG)
    return all(k in r for k in ["verdict", "targets", "reason", "head", "nested"])

# --- Autotest ---
def test1():
    if not check_keys():
        print("FAIL test 1: judge_segment does not return the 5 keys")
        return False
    checks = [
        ("printf x", V("printf x"), F),
        ("tee -a lib/u.py", V("tee -a lib/u.py"), ("write", ["lib/u.py"])),
        ("cat > /tmp/s.py <<EOF", V("cat > /tmp/s.py <<EOF"), ("write", ["/tmp/s.py"])),
        ("echo x > $f", V("echo x > $f"), U),
        ("echo 'abc", V("echo 'abc"), U),
        ("do echo $n", V("do echo $n"), F),
        ("deleg-tool reason", judge_segment("deleg-tool --out a.py -p 'x -> str'", CFG)["reason"], "delegation tool"),
        ("deleg-tool free", V("deleg-tool --out a.py -p 'x -> str'"), F),
        ("deleg-tool redirection", V("deleg-tool x > b.py"), ("write", ["b.py"])),
    ]
    for desc, actual, expected in checks:
        if actual != expected:
            print(f"FAIL test 1: {desc} -> expected {expected}, got {actual}")
            return False
    print("PASS test 1")
    return True

def test2():
    if not check_keys():
        print("FAIL test 2: judge_segment does not return the 5 keys")
        return False
    checks = [
        ("cp a.py dst/", V("cp a.py dst/"), ("write", ["dst/a.py"])),
        ("mv x.txt y.sh", V("mv x.txt y.sh"), ("write", ["y.sh"])),
        ("cp -r src/ dst/", V("cp -r src/ dst/"), F),
        ("cp a.py copy.md", V("cp a.py copy.md"), F),
        ("dd if=/dev/zero of=k.py", V("dd if=/dev/zero of=k.py"), ("write", ["k.py"])),
        ("curl -o out.py http://h/x", V("curl -o out.py http://h/x"), ("write", ["out.py"])),
        ("curl -oout.sh http://h/x", V("curl -oout.sh http://h/x"), ("write", ["out.sh"])),
        ("wget -O w.py http://h", V("wget -O w.py http://h"), ("write", ["w.py"])),
        ("truncate -s 0 t.py", V("truncate -s 0 t.py"), ("write", ["t.py"])),
    ]
    for desc, actual, expected in checks:
        if actual != expected:
            print(f"FAIL test 2: {desc} -> expected {expected}, got {actual}")
            return False
    print("PASS test 2")
    return True

def test3():
    if not check_keys():
        print("FAIL test 3: judge_segment does not return the 5 keys")
        return False
    checks = [
        ("sed -i 's/a/b/' f.py", V("sed -i 's/a/b/' f.py"), ("write", ["f.py"])),
        ("sed -n 1,5p f.py", V("sed -n 1,5p f.py"), F),
        ("perl -pi -e 's/a/b/' g.py", V("perl -pi -e 's/a/b/' g.py"), ("write", ["g.py"])),
        ("awk '{print > \"o.py\"}' in.txt", V("awk '{print > \"o.py\"}' in.txt"), ("write", ["o.py"])),
        ("find . -name '*.py' -print0", V("find . -name '*.py' -print0"), F),
        ("for n in 1 2", V("for n in 1 2"), F),
    ]
    for desc, actual, expected in checks:
        if actual != expected:
            print(f"FAIL test 3: {desc} -> expected {expected}, got {actual}")
            return False
    print("PASS test 3")
    return True

def test4():
    if not check_keys():
        print("FAIL test 4: judge_segment does not return the 5 keys")
        return False

    r = judge_segment("python3 -c \"open('x.py','w')\"", CFG)
    if r["verdict"] != "nested":
        print(f"FAIL test 4: verdict python3 -c -> expected nested, got {r['verdict']}")
        return False
    if r["nested"] != {"kind": "code", "text": "open('x.py','w')"}:
        print(f"FAIL test 4: nested python3 -c -> expected {{'kind': 'code', 'text': \"open('x.py','w')\"}}, got {r['nested']}")
        return False

    r = judge_segment("bash -lc 'tee a.sh'", CFG)
    if r["nested"] != {"kind": "command", "text": "tee a.sh"}:
        print(f"FAIL test 4: nested bash -lc -> expected {{'kind': 'command', 'text': 'tee a.sh'}}, got {r['nested']}")
        return False

    r = judge_segment("eval echo hi", CFG)
    if r["nested"] != {"kind": "command", "text": "echo hi"}:
        print(f"FAIL test 4: nested eval -> expected {{'kind': 'command', 'text': 'echo hi'}}, got {r['nested']}")
        return False

    if V("python3 run.py") != F:
        print(f"FAIL test 4: python3 run.py -> expected {F}, got {V('python3 run.py')}")
        return False

    r = judge_segment("python3 run.py", CFG)
    if r["nested"] is not None:
        print(f"FAIL test 4: nested python3 run.py -> expected None, got {r['nested']}")
        return False

    r = judge_segment("python3.12 -c pass", CFG)
    if r["head"] != "python3":
        print(f"FAIL test 4: head python3.12 -> expected python3, got {r['head']}")
        return False

    print("PASS test 4")
    return True

def test5():
    if not check_keys():
        print("FAIL test 5: judge_segment does not return the 5 keys")
        return False
    checks = [
        ("git status", V("git status"), F),
        ("git checkout main", V("git checkout main"), F),
        ("git checkout -- a.py", V("git checkout -- a.py"), ("write", ["a.py"])),
        ("git restore .", V("git restore ."), U),
        ("git restore --staged notes.md", V("git restore --staged notes.md"), F),
        ("git -C repo apply p.diff", V("git -C repo apply p.diff"), U),
        ("git mv notes.md out.py", V("git mv notes.md out.py"), ("write", ["out.py"])),
        ("git mv a.py b.py", V("git mv a.py b.py"), ("write", ["b.py"])),
        ("git mv notes.md out.md", V("git mv notes.md out.md"), F),
        ("git mv a.py src/", V("git mv a.py src/"), ("write", ["src/a.py"])),
        ("tar xzf a.tgz", V("tar xzf a.tgz"), U),
        ("tar -czf a.tgz src", V("tar -czf a.tgz src"), F),
        ("unzip a.zip", V("unzip a.zip"), U),
    ]
    for desc, actual, expected in checks:
        if actual != expected:
            print(f"FAIL test 5: {desc} -> expected {expected}, got {actual}")
            return False

    # Sub-process --notice
    p = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"],
                       capture_output=True, text=True)
    if p.returncode != 0 or not p.stdout.startswith("NAME      shell_targets.py"):
        print(f"FAIL test 5: --notice -> code {p.returncode}, stdout {p.stdout!r}")
        return False

    # Sub-process without argument
    p = subprocess.run([sys.executable, os.path.abspath(__file__)],
                       capture_output=True, text=True)
    if p.returncode != 2 or p.stdout != USAGE:
        print(f"FAIL test 5: without argument -> code {p.returncode}, stdout {p.stdout!r}")
        return False

    print("PASS test 5")
    return True

def run_autotest():
    results = [
        test1(),
        test2(),
        test3(),
        test4(),
        test5()
    ]
    return all(results)

def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        success = run_autotest()
        sys.exit(0 if success else 1)
    else:
        sys.stdout.write(USAGE)
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "shell_targets", sys.argv[1:])
