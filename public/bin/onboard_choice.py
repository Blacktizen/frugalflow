import copy
import os
import subprocess
import sys
import tempfile

NOTICE = (
    "NAME      onboard_choice.py - the decisions of the guided setup: "
    "which engines to offer, which one is chosen, how it lands in models.json.\n"
    "READS     nothing: pure module, it only works on the values it is given.\n"
    "WRITES    nothing: every function returns a value; apply_choice "
    "returns a copy and never changes its input.\n"
    "EXAMPLE   python3 onboard_choice.py --autotest\n"
    "PITFALLS  2026-10-25 an engine typed without /v1 was written as is "
    "and every call failed; endpoints are now normalized to end with /v1.\n"
    "          2026-10-25 a key found in the environment is only named "
    "in models.json; its value is never read here."
)


def normalize_endpoint(url):
    s = url.strip()
    while s.endswith("/"):
        s = s[:-1]
    if s == "":
        return ""
    if s.endswith("/v1"):
        return s
    return s + "/v1"


def build_candidates(findings, endpoint_url, key_env):
    cands = []
    for f in findings:
        if f["kind"] == "lmstudio":
            cands.append({"kind": "lmstudio", "where": f["where"],
                          "label": "LM Studio at " + f["where"]})
    for f in findings:
        if f["kind"] == "ollama":
            cands.append({"kind": "ollama", "where": f["where"],
                          "label": "Ollama at " + f["where"]})
    if endpoint_url != "":
        cands.append({"kind": "openai", "where": endpoint_url,
                      "label": "OpenAI-compatible endpoint at " + endpoint_url})
    keys = sorted(
        [f for f in findings if f["kind"] == "key"],
        key=lambda f: f["where"],
    )
    if key_env != "":
        keys = [k for k in keys if k["where"] == key_env]
    for f in keys:
        cands.append({"kind": "key", "where": f["where"],
                      "label": "API key in the environment variable " + f["where"]})
    return cands


def select(cands, engine):
    if engine == "":
        if cands:
            return (True, cands[0])
        return (True, None)
    if engine == "none":
        return (True, None)
    for c in cands:
        if c["kind"] == engine:
            return (True, c)
    return (False, None)


def menu_lines(cands):
    lines = []
    for i, c in enumerate(cands, 1):
        lines.append("  " + str(i) + ") " + c["label"])
    lines.append("  0) none: guards only, no delegation")
    return lines


def parse_answer(text, n):
    t = text.strip()
    if t == "":
        return 1 if n >= 1 else 0
    if t.isdigit():
        v = int(t)
        if 0 <= v <= n:
            return v
    return None


def apply_choice(doc, choice):
    result = copy.deepcopy(doc)
    kind = choice.get("kind", "")
    models = result.get("models", [])

    def find_model(mid):
        for m in models:
            if m.get("id") == mid:
                return m
        return None

    if kind in ("lmstudio", "ollama"):
        m = find_model("local-reader")
        if m is not None:
            m["endpoint"] = choice.get("endpoint", "")
            if choice.get("model", "") != "":
                m["name"] = choice["model"]
    elif kind == "openai":
        key_env = choice.get("key_env", "")
        if key_env == "":
            m = find_model("local-reader")
            if m is not None:
                m["endpoint"] = choice.get("endpoint", "")
                if choice.get("model", "") != "":
                    m["name"] = choice["model"]
        else:
            m = find_model("remote-coder")
            if m is not None:
                m["endpoint"] = choice.get("endpoint", "")
                m["key_env"] = key_env
                if choice.get("model", "") != "":
                    m["name"] = choice["model"]
    elif kind == "key":
        key_env = choice.get("key_env", "")
        m = find_model("remote-coder")
        if m is not None:
            m["key_env"] = key_env
            if key_env == "DEEPSEEK_API_KEY":
                m["endpoint"] = "https://api.deepseek.com/v1"
    return result


# ---------- fixtures ----------

FINDINGS = [
    {"kind": "key", "where": "ZED_API_KEY"},
    {"kind": "ollama", "where": "http://127.0.0.1:11434"},
    {"kind": "lmstudio", "where": "http://127.0.0.1:1234"},
    {"kind": "key", "where": "ABC_API_KEY"},
]

DOC = {"models": [
    {"id": "local-reader", "name": "qwen",
     "endpoint": "http://127.0.0.1:8000/v1", "key_env": ""},
    {"id": "remote-coder", "name": "deepseek-v4-pro",
     "endpoint": "https://api.example.com/v1", "key_env": "FRUGALFLOW_REMOTE_KEY"},
]}


def _run_autotest():
    n_pass = 0

    # --- Epreuve 1 ---
    ok1 = True
    checks1 = [
        ("http://h:1", "http://h:1/v1"),
        ("  http://h:1/v1/ ", "http://h:1/v1"),
        ("http://h:1/", "http://h:1/v1"),
        ("   ", ""),
    ]
    for inp, exp in checks1:
        got = normalize_endpoint(inp)
        if got != exp:
            ok1 = False
            break
    expected1 = repr(checks1)
    got1 = "ok" if ok1 else repr(normalize_endpoint(checks1[0][0]))
    line1 = ("PASS 1 expected=" + expected1 + " got=" + got1) if ok1 else \
            ("FAIL 1 expected=" + expected1 + " got=" + got1)
    print(line1)
    if ok1:
        n_pass += 1

    # --- Epreuve 2 ---
    c2 = build_candidates(FINDINGS, "http://127.0.0.1:9/v1", "")
    pairs2 = [(c["kind"], c["where"]) for c in c2]
    exp2a = [("lmstudio", "http://127.0.0.1:1234"),
             ("ollama", "http://127.0.0.1:11434"),
             ("openai", "http://127.0.0.1:9/v1"),
             ("key", "ABC_API_KEY"),
             ("key", "ZED_API_KEY")]
    c2b = build_candidates(FINDINGS, "", "ZED_API_KEY")
    pairs2b = [(c["kind"], c["where"]) for c in c2b]
    exp2b = [("lmstudio", "http://127.0.0.1:1234"),
             ("ollama", "http://127.0.0.1:11434"),
             ("key", "ZED_API_KEY")]
    ok2 = (pairs2 == exp2a and pairs2b == exp2b
           and c2[0]["label"] == "LM Studio at http://127.0.0.1:1234")
    if ok2:
        print("PASS 2 expected=" + repr(exp2a) + " got=" + repr(pairs2))
        n_pass += 1
    else:
        print("FAIL 2 expected=" + repr(exp2a) + " got=" + repr(pairs2))

    # --- Epreuve 3 ---
    c3 = c2  # the five candidates from test 2 first case
    s3a = select(c3, "")
    s3b = select(c3, "ollama")
    s3c = select(c3, "none")
    s3d = select(c3, "gemini")
    s3e = select([], "")
    ml = menu_lines(c3)
    ok3 = (s3a == (True, c3[0])
           and s3b == (True, c3[1])
           and s3c == (True, None)
           and s3d == (False, None)
           and s3e == (True, None)
           and len(ml) == 6
           and ml[0] == "  1) LM Studio at http://127.0.0.1:1234"
           and ml[-1] == "  0) none: guards only, no delegation")
    if ok3:
        print("PASS 3 expected=select+menu got=" + repr(ml[0]))
        n_pass += 1
    else:
        print("FAIL 3 expected=select+menu got=" + repr(s3a) + " " + repr(ml))

    # --- Epreuve 4 ---
    checks4 = [("", 3, 1), ("", 0, 0), (" 2 ", 3, 2), ("0", 3, 0),
               ("4", 3, None), ("x", 3, None), ("-1", 3, None)]
    ok4 = all(parse_answer(t, n) == e for t, n, e in checks4)
    if ok4:
        print("PASS 4 expected=" + repr(checks4) + " got=ok")
        n_pass += 1
    else:
        print("FAIL 4 expected=" + repr(checks4) + " got="
              + repr([parse_answer(t, n) for t, n, e in checks4]))

    # --- Epreuve 5 ---
    doc_before = copy.deepcopy(DOC)
    ok5 = True

    # (a) ollama
    ch5a = {"kind": "ollama", "endpoint": "http://127.0.0.1:11434/v1",
            "model": "fake:1b", "key_env": ""}
    r5a = apply_choice(DOC, ch5a)
    if r5a["models"][0]["endpoint"] != "http://127.0.0.1:11434/v1":
        ok5 = False
    if r5a["models"][0]["name"] != "fake:1b":
        ok5 = False
    if r5a["models"][1] != DOC["models"][1]:
        ok5 = False

    # (b) openai with key_env
    ch5b = {"kind": "openai", "endpoint": "https://x.example/v1",
            "model": "", "key_env": "MY_API_KEY"}
    r5b = apply_choice(DOC, ch5b)
    if r5b["models"][1]["endpoint"] != "https://x.example/v1":
        ok5 = False
    if r5b["models"][1]["key_env"] != "MY_API_KEY":
        ok5 = False
    if r5b["models"][1]["name"] != "deepseek-v4-pro":
        ok5 = False
    if r5b["models"][0] != DOC["models"][0]:
        ok5 = False

    # (c) key with DEEPSEEK
    ch5c = {"kind": "key", "endpoint": "", "model": "",
            "key_env": "DEEPSEEK_API_KEY"}
    r5c = apply_choice(DOC, ch5c)
    if r5c["models"][1]["key_env"] != "DEEPSEEK_API_KEY":
        ok5 = False
    if r5c["models"][1]["endpoint"] != "https://api.deepseek.com/v1":
        ok5 = False

    # (d) none: equal but not same object
    ch5d = {"kind": "none", "endpoint": "", "model": "", "key_env": ""}
    r5d = apply_choice(DOC, ch5d)
    if r5d != DOC:
        ok5 = False
    if r5d is DOC:
        ok5 = False

    # DOC must be unchanged
    if DOC != doc_before:
        ok5 = False

    # subprocess: no-arg call must exit 2
    script = os.path.abspath(__file__)
    with tempfile.TemporaryDirectory() as td:
        env = dict(os.environ)
        env["PYTHONPYCACHEPREFIX"] = td
        proc = subprocess.run(
            [sys.executable, script],
            capture_output=True,
            env=env,
        )
        if proc.returncode != 2:
            ok5 = False

    if ok5:
        print("PASS 5 expected=apply_choice+exit2 got=ok")
        n_pass += 1
    else:
        print("FAIL 5 expected=apply_choice+exit2 got=mismatch")

    print("AUTOTEST " + str(n_pass) + "/5")
    return 0 if n_pass == 5 else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_run_autotest())
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    print("usage: onboard_choice.py --notice | --autotest")
    sys.exit(2)
