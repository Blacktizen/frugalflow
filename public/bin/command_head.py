"""command_head.py - drops the words in front of a shell command that are not the command (assignments, sudo, env, nice, timeout, xargs) with their options, and says whether it could."""

import os
import re
import subprocess
import sys

KEYWORDS = {"do", "then", "else", "elif", "if", "while", "until", "!", "nohup", "builtin"}
SHELL = ["sh"]
WRAPPERS = {
    "sudo": ({"-u", "-g", "-C", "-D", "-h", "-p", "-r", "-t", "-U", "-R", "-T", "--user", "--group", "--chdir", "--host", "--prompt", "--role", "--type", "--other-user", "--chroot", "--command-timeout", "--close-from"},
             {"-A", "-b", "-E", "-H", "-k", "-K", "-n", "-P", "-S", "-B", "-N", "--askpass", "--background", "--preserve-env", "--set-home", "--reset-timestamp", "--non-interactive", "--preserve-groups", "--stdin", "--bell", "--no-update", "--"}),
    "doas": ({"-u", "-C"}, {"-n", "-L", "--"}),
    "env": ({"-u", "--unset", "-C", "--chdir"}, {"-i", "-", "--ignore-environment", "-0", "--null", "-v", "--debug", "--"}),
    "nice": ({"-n", "--adjustment"}, {"--"}),
    "timeout": ({"-s", "--signal", "-k", "--kill-after"}, {"--foreground", "--preserve-status", "-v", "--verbose", "--"}),
    "gtimeout": ({"-s", "--signal", "-k", "--kill-after"}, {"--foreground", "--preserve-status", "-v", "--verbose", "--"}),
    "stdbuf": ({"-i", "-o", "-e", "--input", "--output", "--error"}, {"--"}),
    "ionice": ({"-c", "-n", "-p", "-P", "-u", "--class", "--classdata"}, {"-t", "--ignore", "--"}),
    "time": (set(), {"-p", "--"}),
    "command": (set(), {"-p", "-v", "-V", "--"}),
    "exec": ({"-a"}, {"-c", "-l", "--"}),
    "setsid": (set(), {"-f", "-w", "-c", "--fork", "--wait", "--ctty", "--"}),
    "caffeinate": ({"-t", "-w"}, {"-d", "-i", "-m", "-s", "-u"}),
    "xargs": ({"-a", "-d", "-E", "-e", "-I", "-J", "-L", "-l", "-n", "-P", "-R", "-S", "-s", "--arg-file", "--delimiter", "--max-args", "--max-procs", "--max-lines", "--replace"},
              {"-0", "-o", "-p", "-r", "-t", "-x", "--null", "--no-run-if-empty", "--verbose", "--open-tty", "--interactive", "--exit"}),
    "parallel": ({"-j", "-n", "-a", "-d", "-I", "-S", "--jobs", "--arg-file", "--delimiter", "--sshlogin"}, {"-0", "-k", "-q", "-v", "--keep-order", "--quote", "--null", "--verbose"}),
}
POSITIONAL = {"timeout": 1, "gtimeout": 1}
TAKES_SHELL = {"sudo": {"-s", "-i", "--shell", "--login"}, "doas": {"-s"}}
REFUSED = {"sudo": {"-e", "--edit", "-l", "--list", "-v", "--validate"}, "env": {"-S", "--split-string"}}

_ASSIGN_RE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*=.*")


def skip(tokens):
    """Strip prefix words (assignments, wrappers, keywords) from a token list.

    Returns a tuple (rest, sure): rest is a new list of remaining words,
    sure is True when every prefix was recognized, False otherwise.
    The input list is never mutated.
    """
    items = list(tokens)
    sure = True
    shell = False
    while items:
        first = items[0]
        if _ASSIGN_RE.fullmatch(first):
            items = items[1:]
            continue
        if first in KEYWORDS:
            items = items[1:]
            continue
        name = os.path.basename(first)
        if name in WRAPPERS:
            items = items[1:]
            valued, flags = WRAPPERS[name]
            while items and (items[0] == "-" or items[0].startswith("-")):
                word = items[0]
                key = word.split("=", 1)[0]
                if key in REFUSED.get(name, set()):
                    return (items, False)
                if name in TAKES_SHELL and key in TAKES_SHELL[name]:
                    shell = True
                    items = items[1:]
                    continue
                if word in flags or key in flags:
                    items = items[1:]
                    if word == "--":
                        break
                    continue
                if key in valued:
                    items = items[1:]
                    if "=" not in word:
                        if items:
                            items = items[1:]
                    continue
                if len(word) > 2 and word[:2] in valued:
                    items = items[1:]
                    continue
                if name == "nice" and re.fullmatch(r"-\d+", word):
                    items = items[1:]
                    continue
                return (items, False)
            if name == "env":
                while items and _ASSIGN_RE.fullmatch(items[0]):
                    items = items[1:]
            positional = POSITIONAL.get(name, 0)
            for _ in range(positional):
                if items:
                    items = items[1:]
            continue
        break
    if not items and shell:
        return (list(SHELL), sure)
    return (items, sure)


def _print_notice():
    print("NAME      command_head.py - drops the words in front of a shell command that are not the command (assignments, sudo, env, nice, timeout, xargs) with their options, and says whether it could.")
    print("READS     nothing: pure module; it works on the list of words it is given.")
    print("WRITES    nothing: skip() returns the remaining words and True, or False when an option is unknown; --head prints them.")
    print("EXAMPLE   python3 command_head.py --head sudo -u bob bash -c ls")
    print("PITFALLS  2026-09-27 sudo -u x bash, nice -n 5 bash and timeout 5 bash hid the shell: the option value was taken for the command.")


def _run_autotest():
    F1 = ["sudo", "-u", "x", "bash", "-c", "ls"]
    F2 = ["A=1", "nice", "-n", "5", "timeout", "-s", "KILL", "10", "python3", "a.txt"]
    F3 = ["sudo", "-s"]
    F4 = ["sudo", "--frobnicate", "bash"]
    F5 = ["env", "-i", "B=2", "/usr/bin/xargs", "-I", "{}", "-0", "sh"]

    fixtures = [
        (F1, "bash|-c|ls", "SURE", 0),
        (F2, "python3|a.txt", "SURE", 0),
        (F3, "sh", "SURE", 0),
        (F4, "--frobnicate|bash", "UNSURE", 1),
        (F5, "sh", "SURE", 0),
    ]

    all_pass = True
    for idx, (words, exp_line1, exp_line2, exp_code) in enumerate(fixtures, 1):
        proc = subprocess.run(
            [sys.executable, __file__, "--head"] + words,
            capture_output=True,
            text=True,
        )
        lines = proc.stdout.splitlines()
        got_line1 = lines[0] if len(lines) > 0 else ""
        got_line2 = lines[1] if len(lines) > 1 else ""
        got_code = proc.returncode
        if got_line1 == exp_line1 and got_line2 == exp_line2 and got_code == exp_code:
            print("PASS F{}: expected {} | {} | {} got {} | {} | {}".format(
                idx, exp_line1, exp_line2, exp_code, got_line1, got_line2, got_code))
        else:
            print("FAIL F{}: expected {} | {} | {} got {} | {} | {}".format(
                idx, exp_line1, exp_line2, exp_code, got_line1, got_line2, got_code))
            all_pass = False
    return 0 if all_pass else 1


def main():
    argv = sys.argv[1:]
    if not argv:
        print("usage: command_head.py --head WORD... | --notice | --autotest")
        sys.exit(2)
    cmd = argv[0]
    if cmd == "--head":
        rest, sure = skip(argv[1:])
        print("|".join(rest))
        print("SURE" if sure else "UNSURE")
        sys.exit(0 if sure else 1)
    elif cmd == "--notice":
        _print_notice()
        sys.exit(0)
    elif cmd == "--autotest":
        sys.exit(_run_autotest())
    else:
        print("usage: command_head.py --head WORD... | --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "command_head", sys.argv[1:])
