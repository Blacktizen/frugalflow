"""awk_calls.py - tells whether a shell command runs awk in a way that can digest file contents."""

import os
import re
import shlex
import subprocess
import sys

AWK_NAMES = {"awk", "gawk", "mawk", "nawk"}


def digests(command):
    """Return True if the given shell command may digest file contents via an awk call."""
    try:
        if re.search(r"(?<![\w.-])[gmn]?awk(?![\w.-])", command) is None:
            return False

        lex = shlex.shlex(command, posix=True, punctuation_chars="();<>|&\n")
        lex.whitespace = " \t\r"
        lex.whitespace_split = True
        try:
            tokens = list(lex)
        except ValueError:
            return True

        for tok in tokens:
            if tok == "(" or tok == ")" or chr(96) in tok:
                return True

        sep_chars = frozenset(";&|\n")
        pipes = []
        current_pipe = []
        current_cmd = []

        for tok in tokens:
            if tok and all(c in sep_chars for c in tok):
                if current_cmd:
                    current_pipe.append(current_cmd)
                    current_cmd = []
                if tok != "|" and tok != "|&":
                    if current_pipe:
                        pipes.append(current_pipe)
                    current_pipe = []
            else:
                current_cmd.append(tok)

        if current_cmd:
            current_pipe.append(current_cmd)
        if current_pipe:
            pipes.append(current_pipe)

        P = r"(?:[A-Za-z_]\w*=)?(?:.*/)?[gmn]?awk"
        for pipe in pipes:
            for k, cmd in enumerate(pipe):
                for i in range(1, len(cmd)):
                    if re.fullmatch(P, cmd[i]):
                        return True
                if re.fullmatch(r"[A-Za-z_]\w*=(?:.*/)?[gmn]?awk", cmd[0]):
                    return True

                if os.path.basename(cmd[0]) in AWK_NAMES:
                    ok = True
                    if len(cmd) != 2:
                        ok = False
                    if ok and re.fullmatch(
                        r"\{\s*print(\s+\$(\d+|NF)(\s*,\s*\$(\d+|NF))*)?\s*\}",
                        cmd[1],
                    ) is None:
                        ok = False
                    if ok and (k < 1 or os.path.basename(pipe[0][0]) != "ls"):
                        ok = False
                    if ok:
                        for j in range(1, k):
                            if os.path.basename(pipe[j][0]) not in {"head", "tail"}:
                                ok = False
                                break
                            for t in pipe[j][1:]:
                                if re.fullmatch(r"-n|-\d+|\+?\d+", t) is None:
                                    ok = False
                                    break
                            if not ok:
                                break

                    if not ok:
                        return True

        return False
    except Exception:
        return True


NOTICE = (
    "NAME      awk_calls.py - tells whether a shell command runs awk in a way that can digest file contents; only an awk that prints fields of an ls listing is harmless.\n"
    "READS     nothing: pure module; it works on the command text it is given.\n"
    "WRITES    nothing: digests() returns True or False; --judge prints DIGEST or FREE.\n"
    "EXAMPLE   python3 awk_calls.py --judge \"ls -l | awk '{print $5}'\"\n"
    "PITFALLS  2026-09-27 ls | awk '{print $5}' was refused as a digest while awk '{system(...)}' and awk -f after ls passed: awk without print was never counted.\n"
    "          2026-09-27 a first version missed awk behind do, then, {, LC_ALL=C or busybox: any awk not heading its command is a doubt."
)


def _autotest():
    F1 = "ls -l *.jsonl | awk '{print $5,$9}'"
    F2 = "cat session.jsonl | awk '{print $1}'"
    F3 = "ls -lt a/*.jsonl | head -6 | awk '{print $5, $NF}'"
    F4 = "ls *.log | awk '{print $1}' journal.log"
    F5 = "echo 'awk is a word' | wc -l"

    cases = [
        (F1, "FREE", 0),
        (F2, "DIGEST", 1),
        (F3, "FREE", 0),
        (F4, "DIGEST", 1),
        (F5, "FREE", 0),
    ]

    all_pass = True
    for i, (fixture, expected_out, expected_code) in enumerate(cases, 1):
        try:
            proc = subprocess.run(
                [sys.executable, __file__, "--judge", fixture],
                capture_output=True,
                text=True,
            )
            lines = proc.stdout.split("\n")
            actual_out = lines[0].strip() if lines else ""
            actual_code = proc.returncode
        except Exception:
            actual_out = ""
            actual_code = -1

        passed = (actual_out == expected_out) and (actual_code == expected_code)
        status = "PASS" if passed else "FAIL"
        print(
            f"{status} test {i}: expected {expected_out!r} code {expected_code}, "
            f"got {actual_out!r} code {actual_code}"
        )
        if not passed:
            all_pass = False

    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]
    if len(args) == 2 and args[0] == "--judge":
        if digests(args[1]):
            print("DIGEST")
            sys.exit(1)
        else:
            print("FREE")
            sys.exit(0)
    elif len(args) == 1 and args[0] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif len(args) == 1 and args[0] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: awk_calls.py --judge COMMAND | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "awk_calls", sys.argv[1:])
