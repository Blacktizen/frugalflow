import sys
import os
import json
import argparse
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import sampling_rules
import layers

NOTICE_TEXT = (
    "NAME      sampling_check.py - says which sampling settings a local role's model gets, or refuses when none is known.\n"
    "READS     models.json from --models, else FRUGALFLOW_HOME, else ~/.frugalflow; the model's notice file (model.yaml or generation_config.json).\n"
    "WRITES    nothing: SAMPLING or SKIPPED (0), bad arguments or models file (2), NOTICE UNREADABLE or SAMPLING REFUSED (3).\n"
    "EXAMPLE   python3 sampling_check.py --role code --json\n"
    "PITFALLS  2026-09-19 a model named without a publisher got no settings and ran on guessed values, in silence; that is now a refusal."
)


def resolve_models_path(models_arg):
    if models_arg:
        return models_arg
    env = os.environ.get("FRUGALFLOW_HOME")
    if env:
        return os.path.join(env, "models.json")
    return os.path.join(os.path.expanduser("~"), ".frugalflow", "models.json")


def run_autotest():
    D = tempfile.mkdtemp()
    try:
        ALPHA_YAML = ("model: acme/alpha-7b\n"
                      "      - key: llm.prediction.temperature\n"
                      "        value: 1.0\n"
                      "      - key: llm.prediction.topKSampling\n"
                      "        value: 20\n"
                      "      - key: llm.prediction.topPSampling\n"
                      "        value:\n"
                      "          checked: true\n"
                      "          value: 0.95\n")
        GEN_JSON = '{"do_sample": true, "temperature": 0.6, "top_k": 20, "top_p": 0.95}'

        def entry(mid, **extra):
            e = {"id": mid, "name": mid + "-7b", "location": "local",
                 "endpoint": "http://127.0.0.1:9/v1", "context_window": 8192,
                 "trust": "private", "key_env": ""}
            e.update(extra)
            return e

        def models_doc(gen_path):
            ids = ["yaml", "gen", "explicit", "bare", "broken", "badsamp", "far"]
            return {"models": [
                entry("yaml", notice="alpha.yaml"),
                entry("gen", notice=gen_path),
                entry("explicit", sampling={"temperature": 0.7}, notice="alpha.yaml"),
                entry("bare"),
                entry("broken", notice="missing.json"),
                entry("badsamp", sampling={"seed": 1}),
                entry("far", location="remote")],
                "layers": [{"name": "reading", "delegable": True}],
                "roles": [{"name": i, "layer": "reading", "model": i} for i in ids]}

        with open(os.path.join(D, "alpha.yaml"), "w", encoding="utf-8") as f:
            f.write(ALPHA_YAML)
        with open(os.path.join(D, "gen.json"), "w", encoding="utf-8") as f:
            f.write(GEN_JSON)
        with open(os.path.join(D, "models.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(models_doc(os.path.join(D, "gen.json"))))

        script = os.path.abspath(__file__)
        mp = os.path.join(D, "models.json")
        all_pass = True

        def run(args):
            return subprocess.run([sys.executable, script] + args,
                                  capture_output=True, text=True, timeout=20)

        def lines(r):
            return r.stdout.strip().splitlines() if r.stdout.strip() else []

        # Test 1
        r = run(["--models", mp, "--role", "yaml"])
        got = lines(r)
        exp = ["SAMPLING publisher notice: temperature=1.0 top_k=20 top_p=0.95"]
        ok = r.returncode == 0 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 1a: expected " + str(exp) + " rc=0, got " + str(got) + " rc=" + str(r.returncode))

        r = run(["--models", mp, "--role", "gen", "--json"])
        got = lines(r)
        exp = ['{"temperature": 0.6, "top_k": 20, "top_p": 0.95}']
        ok = r.returncode == 0 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 1b: expected " + str(exp) + " rc=0, got " + str(got) + " rc=" + str(r.returncode))

        # Test 2
        r = run(["--models", mp, "--role", "explicit"])
        got = lines(r)
        exp = ["SAMPLING models.json: temperature=0.7"]
        ok = r.returncode == 0 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 2: expected " + str(exp) + " rc=0, got " + str(got) + " rc=" + str(r.returncode))

        # Test 3
        r = run(["--models", mp, "--role", "bare"])
        got = lines(r)
        exp = ["SAMPLING REFUSED: no sampling settings: neither models.json nor a publisher notice"]
        ok = r.returncode == 3 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 3: expected " + str(exp) + " rc=3, got " + str(got) + " rc=" + str(r.returncode))

        # Test 4
        r = run(["--models", mp, "--role", "broken"])
        got = lines(r)
        ok = r.returncode == 3 and len(got) > 0 and got[0].startswith("NOTICE UNREADABLE: ")
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 4a: expected rc=3 prefix 'NOTICE UNREADABLE: ', got " + str(got) + " rc=" + str(r.returncode))

        r = run(["--models", mp, "--role", "badsamp"])
        got = lines(r)
        exp = ["MODELS REFUSED: sampling.seed is not a known setting"]
        ok = r.returncode == 2 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 4b: expected " + str(exp) + " rc=2, got " + str(got) + " rc=" + str(r.returncode))

        r = run(["--models", mp, "--role", "far"])
        got = lines(r)
        exp = ["SKIPPED far: not a local model"]
        ok = r.returncode == 0 and got == exp
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 4c: expected " + str(exp) + " rc=0, got " + str(got) + " rc=" + str(r.returncode))

        # Test 5
        r = run([])
        got = lines(r)
        ok = r.returncode == 2 and len(got) > 0
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 5a: expected rc=2 non-empty stdout, got " + str(got) + " rc=" + str(r.returncode))

        r = run(["--models", os.path.join(D, "absent.json"), "--role", "yaml"])
        got = lines(r)
        ok = r.returncode == 2 and len(got) > 0 and got[0].startswith("NO MODELS FILE: ")
        all_pass = all_pass and ok
        print(("PASS" if ok else "FAIL") + " 5b: expected rc=2 prefix 'NO MODELS FILE: ', got " + str(got) + " rc=" + str(r.returncode))

        sys.exit(0 if all_pass else 1)
    finally:
        shutil.rmtree(D)


def main():
    if "--notice" in sys.argv[1:]:
        print(NOTICE_TEXT)
        sys.exit(0)
    if "--autotest" in sys.argv[1:]:
        run_autotest()

    parser = argparse.ArgumentParser()
    parser.add_argument("--models")
    parser.add_argument("--role")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    if not args.role:
        print("usage: sampling_check.py --role NAME [--models FILE] [--json] | --notice | --autotest")
        sys.exit(2)

    models_path = resolve_models_path(args.models)
    try:
        with open(models_path, "r", encoding="utf-8") as f:
            doc = json.load(f)
    except (OSError, json.JSONDecodeError):
        print("NO MODELS FILE: " + models_path)
        sys.exit(2)

    errors = layers.verify(doc)
    if errors:
        print("MODELS REFUSED: " + errors[0])
        sys.exit(2)

    model, why = layers.route(doc, args.role, layers.TRUST[-1])
    if model is None:
        print("ROLE REFUSED: " + why)
        sys.exit(2)

    if model.get("location") != "local":
        print("SKIPPED " + model["id"] + ": not a local model")
        sys.exit(0)

    explicit = model.get("sampling")
    if "sampling" in model:
        errs = sampling_rules.validate(explicit)
        if errs:
            print("MODELS REFUSED: " + errs[0])
            sys.exit(2)

    notice = None
    if "notice" in model:
        notice_val = model["notice"]
        if not isinstance(notice_val, str) or not notice_val:
            print("MODELS REFUSED: model " + model["id"] + " notice must be a file path")
            sys.exit(2)
        notice_path = os.path.expanduser(notice_val)
        if not os.path.isabs(notice_path):
            notice_path = os.path.join(os.path.dirname(models_path), notice_path)
        try:
            with open(notice_path, "r", encoding="utf-8") as f:
                txt = f.read()
        except OSError:
            print("NOTICE UNREADABLE: " + notice_path)
            sys.exit(3)
        if notice_path.endswith(".yaml") or notice_path.endswith(".yml"):
            notice = sampling_rules.from_model_yaml(txt)
        else:
            try:
                value = json.loads(txt)
            except json.JSONDecodeError:
                print("NOTICE UNREADABLE: " + notice_path)
                sys.exit(3)
            notice = sampling_rules.from_generation_config(value)

    settings, source, error = sampling_rules.resolve(explicit, notice)
    if error is not None:
        print("SAMPLING REFUSED: " + error)
        sys.exit(3)

    if args.json:
        print(json.dumps(settings, sort_keys=True))
    else:
        parts = [str(k) + "=" + str(v) for k, v in sorted(settings.items())]
        print("SAMPLING " + source + ": " + " ".join(parts))
    sys.exit(0)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "sampling_check", sys.argv[1:])
