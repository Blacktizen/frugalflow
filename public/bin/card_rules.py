import sys
import os
import subprocess

P_LMS = {"data": [{"id": "alpha-7b", "loaded_context_length": 65536}]}
P_VLLM = {"data": [{"id": "alpha-7b", "max_model_len": 32768}, "junk"]}
P_TWO = {"data": [{"id": "alpha-7b", "loaded_context_length": 65536}, {"id": "beta-3b", "loaded_context_length": 8192}]}
P_BAD = {"models": []}
P_BOOL = {"data": [{"id": "alpha-7b", "loaded_context_length": True}]}
P_LLAMA = {"data": [{"id": "alpha-7b", "meta": {"n_ctx": 131072}}]}
A64 = [{"id": "alpha-7b", "context": 65536}]
A32 = [{"id": "alpha-7b", "context": 32768}]

NOTICE = (
    "NAME      card_rules.py - says whether the local engine serves the expected model, alone, with enough context.\n"
    "READS     nothing: pure module; it judges the values it is given.\n"
    "WRITES    nothing: parse_models(), judge() and classify_probe() return a code and a message.\n"
    "EXAMPLE   python3 card_rules.py --notice\n"
    "PITFALLS  2026-08-23 another model was loaded on the same card and the delegation ran on it; the answer's model field is checked.\n"
    "          2026-09-17 a window too wide cut the throughput to 0.7 token/s; the loaded context is compared to the one required.\n"
    "          2026-10-10 a llama.cpp-style server gives its window as meta.n_ctx; reading only two formats refused every delegation."
)


def parse_models(payload):
    if not isinstance(payload, dict) or "data" not in payload or not isinstance(payload["data"], list):
        return ([], "no data list")
    result = []
    for m in payload["data"]:
        if not isinstance(m, dict):
            continue
        model_id = str(m.get("id", ""))
        if "loaded_context_length" in m:
            ctx = m["loaded_context_length"]
        elif "max_model_len" in m:
            ctx = m["max_model_len"]
        elif isinstance(m.get("meta"), dict) and "n_ctx" in m["meta"]:
            ctx = m["meta"]["n_ctx"]
        else:
            ctx = 0
        if isinstance(ctx, bool) or not isinstance(ctx, int):
            ctx = 0
        result.append({"id": model_id, "context": ctx})
    return (result, None)


def judge(models, expected, min_context):
    if len(models) == 0:
        return ("no_model", "no model is loaded")
    if len(models) > 1:
        ids = ", ".join(m["id"] for m in models)
        return ("several_models", "several models are loaded: " + ids)
    model = models[0]
    if model["id"] != expected:
        return ("wrong_model", "expected " + expected + ", loaded " + model["id"])
    ctx = model["context"]
    if ctx < min_context:
        return ("short_context", str(ctx) + " tokens loaded, " + str(min_context) + " required")
    return ("ok", expected + " loaded with " + str(ctx) + " tokens")


def classify_probe(outcome, expected):
    reached = outcome.get("reached")
    timed_out = outcome.get("timed_out")
    status = outcome.get("status")
    model = outcome.get("model")

    if reached is not True and timed_out is True:
        return ("model_stuck", "no answer within the time limit")
    if reached is not True:
        return ("engine_absent", "the engine does not answer")
    if status == 400 or status == 404:
        return ("model_unknown", "the engine does not know " + expected)
    if status != 200:
        return ("engine_error", "HTTP " + str(status))
    if model != expected:
        return ("model_substituted", "expected " + expected + ", answered by " + str(model))
    return ("ok", "answered by " + expected)


def evaluate_test(num, checks):
    failures = []
    for desc, expected, obtained in checks:
        if expected != obtained:
            failures.append(f"{desc}: expected {expected!r}, obtained {obtained!r}")
    if failures:
        print(f"FAIL test {num}: {'; '.join(failures)}")
        return False
    else:
        print(f"PASS test {num}: expected all checks to pass, obtained all checks passed")
        return True


def run_autotest():
    overall = True

    overall &= evaluate_test(1, [
        ("parse_models(P_LMS)", (A64, None), parse_models(P_LMS)),
        ("parse_models(P_VLLM)", (A32, None), parse_models(P_VLLM)),
        ("parse_models(P_BAD)", ([], "no data list"), parse_models(P_BAD)),
        ("parse_models('x')", ([], "no data list"), parse_models("x")),
        ("parse_models(P_BOOL)", ([{"id": "alpha-7b", "context": 0}], None), parse_models(P_BOOL)),
    ])

    overall &= evaluate_test(2, [
        ("judge([], 'alpha-7b', 1)", ("no_model", "no model is loaded"), judge([], "alpha-7b", 1)),
        ("judge(parse_models(P_TWO)[0], 'alpha-7b', 1)", ("several_models", "several models are loaded: alpha-7b, beta-3b"), judge(parse_models(P_TWO)[0], "alpha-7b", 1)),
    ])

    overall &= evaluate_test(3, [
        ("judge(A64, 'beta-3b', 1000)", ("wrong_model", "expected beta-3b, loaded alpha-7b"), judge(A64, "beta-3b", 1000)),
        ("judge(A32, 'alpha-7b', 65536)", ("short_context", "32768 tokens loaded, 65536 required"), judge(A32, "alpha-7b", 65536)),
        ("judge(A64, 'alpha-7b', 65536)", ("ok", "alpha-7b loaded with 65536 tokens"), judge(A64, "alpha-7b", 65536)),
    ])

    overall &= evaluate_test(4, [
        ("classify_probe({}, 'alpha-7b')", ("engine_absent", "the engine does not answer"), classify_probe({}, "alpha-7b")),
        ("classify_probe({'timed_out': True}, 'alpha-7b')", ("model_stuck", "no answer within the time limit"), classify_probe({"timed_out": True}, "alpha-7b")),
        ("classify_probe({'reached': True, 'status': 404}, 'alpha-7b')", ("model_unknown", "the engine does not know alpha-7b"), classify_probe({"reached": True, "status": 404}, "alpha-7b")),
        ("classify_probe({'reached': True, 'status': 500}, 'alpha-7b')", ("engine_error", "HTTP 500"), classify_probe({"reached": True, "status": 500}, "alpha-7b")),
        ("classify_probe({'reached': True, 'status': 200, 'model': 'beta-3b'}, 'alpha-7b')", ("model_substituted", "expected alpha-7b, answered by beta-3b"), classify_probe({"reached": True, "status": 200, "model": "beta-3b"}, "alpha-7b")),
        ("classify_probe({'reached': True, 'status': 200, 'model': 'alpha-7b'}, 'alpha-7b')", ("ok", "answered by alpha-7b"), classify_probe({"reached": True, "status": 200, "model": "alpha-7b"}, "alpha-7b")),
    ])

    overall &= evaluate_test(6, [
        ("parse_models(P_LLAMA)", ([{"id": "alpha-7b", "context": 131072}], None), parse_models(P_LLAMA)),
        ("parse_models({'data': [{'id': 'alpha-7b', 'loaded_context_length': 65536, 'meta': {'n_ctx': 999}}]})", (A64, None), parse_models({"data": [{"id": "alpha-7b", "loaded_context_length": 65536, "meta": {"n_ctx": 999}}]})),
    ])

    overall &= evaluate_test(7, [
        ("parse_models({'data': [{'id': 'alpha-7b', 'meta': {'n_ctx': True}}]})", ([{"id": "alpha-7b", "context": 0}], None), parse_models({"data": [{"id": "alpha-7b", "meta": {"n_ctx": True}}]})),
    ])

    overall &= evaluate_test(8, [
        ("parse_models({'data': [{'id': 'alpha-7b', 'meta': 'x'}]})", ([{"id": "alpha-7b", "context": 0}], None), parse_models({"data": [{"id": "alpha-7b", "meta": "x"}]})),
        ("parse_models({'data': [{'id': 'alpha-7b', 'meta': {'n_ctx': 'big'}}]})", ([{"id": "alpha-7b", "context": 0}], None), parse_models({"data": [{"id": "alpha-7b", "meta": {"n_ctx": "big"}}]})),
    ])

    try:
        proc = subprocess.run([sys.executable, os.path.abspath(__file__), "--notice"], capture_output=True, text=True)
        code_ok = proc.returncode == 0
        prefix_ok = proc.stdout.startswith("NAME      card_rules.py")
        if code_ok and prefix_ok:
            print("PASS test 5: expected exit 0 and notice prefix, obtained exit 0 and notice prefix")
            overall = overall and True
        else:
            details = f"exit {proc.returncode} and stdout prefix {proc.stdout[:30]!r}"
            print(f"FAIL test 5: expected exit 0 and notice prefix, obtained {details}")
            overall = False
    except Exception as exc:
        print(f"FAIL test 5: expected exit 0 and notice prefix, obtained exception {exc!r}")
        overall = False

    return overall


def main(argv=None):
    if argv is None:
        argv = sys.argv[1:]
    if not argv:
        print("usage: card_rules.py --notice | --autotest")
        return 2
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return 0 if run_autotest() else 1
    print("usage: card_rules.py --notice | --autotest")
    return 2


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "card_rules", sys.argv[1:])
