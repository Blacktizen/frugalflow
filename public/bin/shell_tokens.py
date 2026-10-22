import os
import re
import shlex
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import shell_quotes
import command_head

OPERATOR = re.compile(r"(?:(?:^|(?<=\s))\d+)?(?:&>>|&>|>>|>\||>&|>)")
DEVICES = {"/dev/null", "/dev/stdout", "/dev/stderr", "/dev/tty"}
DYNAMIC = ("__SUB__", "$", "`", "*", "?", "[", "{}")

EXTS = [".py", ".sh", ".js"]

NOTICE = """NAME      shell_tokens.py - cuts one simple shell command into words, drops the prefixes that are not the command, and lists its output redirections with their targets.
READS     nothing: pure module; it works on the command text and the code extensions it is given, with shell_quotes.py beside it.
WRITES    nothing: every function returns a new list, tuple or string.
EXAMPLE   python3 shell_tokens.py --notice
PITFALLS  2026-09-25 the standard splitter cut ${d}/a.py into five pieces: redirection operators are spaced out first, then words are split.
          A target built at run time ($f, a subshell, a glob) is unknown, never free.
          2026-09-27 log-$n.txt was unknown although no expansion can change its literal .txt suffix; a{md,py} brace lists are unknown."""

USAGE = "usage: shell_tokens.py --notice | --autotest\n"


def tokenize(seg):
    if not isinstance(seg, str):
        return None
    masked = shell_quotes.mask_quotes(seg)
    parts = []
    last = 0
    for m in OPERATOR.finditer(masked):
        start, end = m.span()
        parts.append(seg[last:start])
        parts.append(" " + seg[start:end] + " ")
        last = end
    parts.append(seg[last:])
    result = "".join(parts)
    try:
        return shlex.split(result)
    except ValueError:
        return None


def strip_prefixes(tokens):
    # sudo -u x bash took x for the command; prefixes and their options are in command_head.py.
    return command_head.skip(tokens)[0]


def classify_target(target, exts):
    if target in DEVICES:
        return None
    if "{" in target and ("," in target or ".." in target):
        return "unknown"
    if any(target.endswith(ext) for ext in exts):
        return "code"
    last = max((target.rfind(d) + len(d) for d in DYNAMIC if d in target), default=-1)
    if last >= 0 and not re.search(r"\.[A-Za-z0-9]+$", target[last:]):
        return "unknown"
    return None


def redirections(tokens, exts):
    targets = []
    unknown = False
    plain = []
    i = 0
    n = len(tokens)
    while i < n:
        t = tokens[i]
        op = re.sub(r"^\d+", "", t)
        dest = None
        if op in (">", ">>", ">|", "&>", "&>>"):
            if i + 1 < n:
                dest = tokens[i + 1]
                i += 2
            else:
                i += 1
        elif op == ">&":
            if i + 1 < n and (tokens[i + 1].isdigit() or tokens[i + 1] == "-"):
                i += 2
            elif i + 1 < n:
                dest = tokens[i + 1]
                i += 2
            else:
                i += 1
        else:
            plain.append(t)
            i += 1
            continue

        if dest is not None:
            c = classify_target(dest, exts)
            if c == "code" and dest not in targets:
                targets.append(dest)
            elif c == "unknown":
                unknown = True

    return (targets, unknown, plain)


def _test1():
    actual = (
        tokenize("echo x 2>&1 >out.py"),
        tokenize("cat f>>a.py"),
        tokenize('echo "x > y" ${d}/a.py'),
        tokenize("x &>/dev/null"),
        tokenize("echo 'abc"),
        tokenize(None),
    )
    expected = (
        ["echo", "x", "2>&", "1", ">", "out.py"],
        ["cat", "f", ">>", "a.py"],
        ["echo", "x > y", "${d}/a.py"],
        ["x", "&>", "/dev/null"],
        None,
        None,
    )
    return actual, expected


def _test2():
    actual = (
        strip_prefixes(["a=1", "b=__SUB__", "env", "X=2", "tee", "-a", "lib/u.py"]),
        strip_prefixes(["do", "echo", "$n"]),
        strip_prefixes(["xargs", "-0", "wc", "-l"]),
        strip_prefixes(["sudo", "nohup", "python3", "x.py"]),
        strip_prefixes(["make", "A=1"]),
        strip_prefixes([]),
    )
    expected = (
        ["tee", "-a", "lib/u.py"],
        ["echo", "$n"],
        ["wc", "-l"],
        ["python3", "x.py"],
        ["make", "A=1"],
        [],
    )
    return actual, expected


def _test3():
    actual = (
        classify_target("a.py", EXTS),
        classify_target("/dev/null", EXTS),
        classify_target("notes.txt", EXTS),
        classify_target("$f", EXTS),
        classify_target("$DIR/x.py", EXTS),
        classify_target("__SUB__", EXTS),
        classify_target("out*.log", EXTS),
        classify_target("${d}/a.js", EXTS),
    )
    expected = (
        "code",
        None,
        None,
        "unknown",
        "code",
        "unknown",
        None,
        "code",
    )
    return actual, expected


def _test4():
    actual = (
        redirections(["echo", "x", "2>&", "1", ">", "out.py"], EXTS),
        redirections(["echo", "a", ">&", "2"], EXTS),
        redirections(["cmd", ">|", "f.py", ">>", "f.py", "&>", "/dev/null"], EXTS),
        redirections(["cat", ">", "$out"], EXTS),
        redirections(["cat", ">"], EXTS),
        redirections(["x", ">&", "log.sh"], EXTS),
    )
    expected = (
        (["out.py"], False, ["echo", "x"]),
        ([], False, ["echo", "a"]),
        (["f.py"], False, ["cmd"]),
        ([], True, ["cat"]),
        ([], False, ["cat"]),
        (["log.sh"], False, ["x"]),
    )
    return actual, expected


def _test5():
    p1 = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True,
    )
    p2 = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True,
        text=True,
    )
    actual = (p1.returncode, p1.stdout.startswith("NAME      shell_tokens.py"), p2.returncode, p2.stdout)
    expected = (0, True, 2, "usage: shell_tokens.py --notice | --autotest\n")
    return actual, expected


def _value_matches(actual, expected):
    if type(actual) is not type(expected):
        return False
    return actual == expected


def run_autotest():
    tests = [_test1, _test2, _test3, _test4, _test5]
    all_ok = True
    for idx, test in enumerate(tests, 1):
        actual, expected = test()
        ok = _value_matches(actual, expected)
        status = "PASS" if ok else "FAIL"
        print(f"{status} test {idx}: want={expected!r} got={actual!r}")
        all_ok = all_ok and ok
    return all_ok


def main(argv):
    if not argv:
        sys.stdout.write(USAGE)
        return 2
    arg = argv[0]
    if arg == "--notice":
        sys.stdout.write(NOTICE + "\n")
        return 0
    if arg == "--autotest":
        return 0 if run_autotest() else 1
    sys.stdout.write(USAGE)
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "shell_tokens", sys.argv[1:])
