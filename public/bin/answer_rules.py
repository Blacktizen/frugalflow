import sys
import os
import re
import subprocess

GRAVES = chr(96) * 3

RETRY_TRUNCATED = "Your previous answer looped and was cut. Redo the task above going straight to the final code: no reasoning comments, no draft, one version only."

NOTICE = """NAME      answer_rules.py - reads a model's answer, strips the code fences, builds the retry, and names the candidate file.
READS     nothing: pure module; it works on the decoded answer and the texts it is given.
WRITES    nothing: read_answer() returns the content, the model that answered and a refusal if any.
EXAMPLE   python3 answer_rules.py --notice
PITFALLS  2026-08-23 an answer without a model field passed as the model asked; it is now a refusal.
          2026-09-23 the candidate file lost its .py extension and a check could not load it; the extension is kept."""

G = chr(96) * 3
FENCED = G + "python\nprint(1)\n" + G + "\n"
INNER = G + "python\ns = '''\n" + G + "\nx\n" + G + "\n'''\n" + G
OPEN = G + "\nprint(2)\n"
GOOD = {"model": "alpha-7b", "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}], "usage": {"prompt_tokens": 12, "completion_tokens": 3}}
CUT = {"model": "alpha-7b", "choices": [{"message": {"content": "abc"}, "finish_reason": "length"}], "usage": {"prompt_tokens": True}}
SUBST = {"choices": [{"message": {"content": "ok"}}]}
EMPTY = {"model": "alpha-7b", "choices": [{"message": {"content": "  "}}]}
BASE = [{"role": "system", "content": "s"}, {"role": "user", "content": "u"}]


def strip_fences(text):
    if not isinstance(text, str):
        return "\n"
    s = text.strip()
    if s == "":
        return "\n"
    lines = s.split("\n")
    def is_open(line):
        st = line.strip()
        if not st.startswith(GRAVES):
            return False
        rest = st[len(GRAVES):].strip()
        return re.fullmatch(r"[A-Za-z0-9_+-]*", rest) is not None
    def is_close(line):
        return line.strip() == GRAVES
    if is_open(lines[0]):
        if len(lines) >= 2 and is_close(lines[-1]):
            body = lines[1:-1]
        else:
            body = lines[1:]
        return "\n".join(body).rstrip("\n") + "\n"
    return s + "\n"


def read_answer(data, asked_model):
    if not isinstance(data, dict):
        choices = None
    else:
        choices = data.get("choices")
    if not isinstance(choices, list) or len(choices) == 0 or not isinstance(choices[0], dict):
        return {"content": "", "truncated": False, "model": None, "tokens_in": None, "tokens_out": None, "refusal": "no choice in the answer"}

    model = data.get("model")
    choice0 = choices[0]
    message = choice0.get("message")
    content = message.get("content") if isinstance(message, dict) and isinstance(message.get("content"), str) else ""
    truncated = (choice0.get("finish_reason") == "length")

    usage = data.get("usage")
    if not isinstance(usage, dict):
        usage = {}

    def int_not_bool(v):
        return v if isinstance(v, int) and not isinstance(v, bool) else None

    tokens_in = int_not_bool(usage.get("prompt_tokens"))
    tokens_out = int_not_bool(usage.get("completion_tokens"))

    if model != asked_model:
        refusal = "model substituted: expected " + str(asked_model) + ", answered by " + str(model)
    elif content.strip() == "":
        refusal = "empty answer"
    else:
        refusal = None

    return {"content": content, "truncated": truncated, "model": model, "tokens_in": tokens_in, "tokens_out": tokens_out, "refusal": refusal}


def retry_messages(base, content, report, truncated):
    if truncated:
        return list(base) + [{"role": "user", "content": RETRY_TRUNCATED}]
    return list(base) + [
        {"role": "assistant", "content": content},
        {"role": "user", "content": "This code fails. Output of the check:\n\n" + report + "\n\nFix it and send the COMPLETE corrected file. Code only, no explanation."}
    ]


def candidate_path(out):
    stem, ext = os.path.splitext(out)
    return stem + ".candidate" + ext


def run_autotest():
    all_ok = True

    # Test 1
    expected1 = ("print(1)\n", "s = '''\n" + G + "\nx\n" + G + "\n'''\n", "print(2)\n", "plain\n", "\n")
    got1 = (strip_fences(FENCED), strip_fences(INNER), strip_fences(OPEN), strip_fences("plain"), strip_fences(None))
    ok1 = expected1 == got1
    print(f"{'PASS' if ok1 else 'FAIL'} test1 expected={expected1!r} got={got1!r}")
    all_ok = all_ok and ok1

    # Test 2
    expected2a = {"content": "ok", "truncated": False, "model": "alpha-7b", "tokens_in": 12, "tokens_out": 3, "refusal": None}
    got2a = read_answer(GOOD, "alpha-7b")
    expected2b = {"content": "abc", "truncated": True, "model": "alpha-7b", "tokens_in": None, "tokens_out": None, "refusal": None}
    got2b = read_answer(CUT, "alpha-7b")
    expected2 = (expected2a, expected2b)
    got2 = (got2a, got2b)
    ok2 = expected2 == got2
    print(f"{'PASS' if ok2 else 'FAIL'} test2 expected={expected2!r} got={got2!r}")
    all_ok = all_ok and ok2

    # Test 3
    expected3 = (
        "model substituted: expected alpha-7b, answered by None",
        "empty answer",
        "no choice in the answer",
        "model substituted: expected beta-3b, answered by alpha-7b"
    )
    got3 = (
        read_answer(SUBST, "alpha-7b")["refusal"],
        read_answer(EMPTY, "alpha-7b")["refusal"],
        read_answer([], "alpha-7b")["refusal"],
        read_answer(GOOD, "beta-3b")["refusal"]
    )
    ok3 = expected3 == got3
    print(f"{'PASS' if ok3 else 'FAIL'} test3 expected={expected3!r} got={got3!r}")
    all_ok = all_ok and ok3

    # Test 4
    r = retry_messages(BASE, "code", "FAIL 1", True)
    expected4a = BASE + [{"role": "user", "content": RETRY_TRUNCATED}]
    expected4b = [
        {"role": "assistant", "content": "code"},
        {"role": "user", "content": "This code fails. Output of the check:\n\nFAIL 1\n\nFix it and send the COMPLETE corrected file. Code only, no explanation."}
    ]
    expected4 = (expected4a, len(r), len(BASE), expected4b, "dir/card.candidate.py", "notes.candidate")
    got4 = (r, len(r), len(BASE), retry_messages(BASE, "code", "FAIL 1", False)[2:], candidate_path("dir/card.py"), candidate_path("notes"))
    ok4 = expected4 == got4
    print(f"{'PASS' if ok4 else 'FAIL'} test4 expected={expected4!r} got={got4!r}")
    all_ok = all_ok and ok4

    # Test 5
    proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
    expected5 = (0, True)
    got5 = (proc.returncode, proc.stdout.startswith("NAME      answer_rules.py"))
    ok5 = expected5 == got5
    print(f"{'PASS' if ok5 else 'FAIL'} test5 expected={expected5!r} got={got5!r}")
    all_ok = all_ok and ok5

    return all_ok


def _cli():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        ok = run_autotest()
        sys.exit(0 if ok else 1)
    else:
        print("usage: answer_rules.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "answer_rules", sys.argv[1:])
