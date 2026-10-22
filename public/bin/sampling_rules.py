import sys
import os
import re
import subprocess

KEYS = ["temperature", "top_p", "top_k", "min_p", "presence_penalty", "repetition_penalty"]

NOTICE = """NAME      sampling_rules.py - reads a publisher's sampling settings and says which ones apply, or that none is known.
READS     nothing: pure module; it parses the texts and values it is given.
WRITES    nothing: from_generation_config() and from_model_yaml() return settings, validate() errors, resolve() the choice.
EXAMPLE   python3 sampling_rules.py --notice
PITFALLS  2026-08-25 one temperature written in the code was wrong for another model; the publisher's value is read.
          2026-09-19 a model named without a publisher got no settings, in silence; no source is now a refusal.
"""

def from_generation_config(doc):
    if not isinstance(doc, dict):
        return {}
    result = {}
    for key in KEYS:
        if key in doc and type(doc[key]) in (int, float):
            result[key] = doc[key]
    return result

def from_model_yaml(text):
    mapping = {
        "llm.prediction.temperature": "temperature",
        "llm.prediction.topKSampling": "top_k",
        "llm.prediction.topPSampling": "top_p",
        "llm.prediction.minPSampling": "min_p",
        "llm.prediction.repeatPenalty": "repetition_penalty",
        "llm.prediction.llama.presencePenalty": "presence_penalty",
    }
    if not isinstance(text, str):
        return {}
    lines = text.split("\n")
    result = {}
    key_re = re.compile(r"^\s*- key:\s*(\S+)\s*$")
    value_simple_re = re.compile(r"^\s*value:\s*(\S+)\s*$")
    value_empty_re = re.compile(r"^\s*value:\s*$")
    checked_re = re.compile(r"^\s*checked:\s*(true|false)\s*$")
    int_re = re.compile(r"-?\d+")

    i = 0
    while i < len(lines):
        m = key_re.match(lines[i])
        if not m:
            i += 1
            continue
        original_key = m.group(1)
        if original_key not in mapping:
            i += 1
            continue
        target_key = mapping[original_key]
        # Check next line exists
        if i + 1 >= len(lines):
            i += 1
            continue

        # Case a: simple value on the next line
        m_simple = value_simple_re.match(lines[i+1])
        if m_simple:
            raw = m_simple.group(1)
            value = None
            if raw.isdigit() or (raw.startswith('-') and raw[1:].isdigit()):
                value = int(raw)
            else:
                try:
                    value = float(raw)
                except ValueError:
                    value = None
            if value is not None:
                result[target_key] = value
            i += 1
            continue

        # Case b: empty value on next line; look at i+2 and i+3 for checked and value
        if value_empty_re.match(lines[i+1]):
            raw = None
            checked = True
            for j in (i+2, i+3):
                if j >= len(lines):
                    break
                m_checked = checked_re.match(lines[j])
                if m_checked:
                    checked = (m_checked.group(1) == "true")
                    continue
                m_value = value_simple_re.match(lines[j])
                if m_value:
                    raw = m_value.group(1)
            if raw is not None and checked:
                value = None
                if raw.isdigit() or (raw.startswith('-') and raw[1:].isdigit()):
                    value = int(raw)
                else:
                    try:
                        value = float(raw)
                    except ValueError:
                        value = None
                if value is not None:
                    result[target_key] = value
            i += 1
            continue

        # Case c: ignore
        i += 1

    return result

def validate(sampling):
    if not isinstance(sampling, dict):
        return ["sampling must be an object"]
    errors = []
    for key, value in sampling.items():
        if key not in KEYS:
            errors.append(f"sampling.{key} is not a known setting")
        elif type(value) not in (int, float):
            errors.append(f"sampling.{key} must be a number")
    return errors

def resolve(explicit, notice):
    if explicit is not None and isinstance(explicit, dict) and len(explicit) > 0:
        return (dict(explicit), "models.json", None)
    if notice is not None and isinstance(notice, dict) and len(notice) > 0:
        return (dict(notice), "publisher notice", None)
    return (None, None, "no sampling settings: neither models.json nor a publisher notice")


Y1 = ("model: acme/alpha-7b\n"
      "config:\n"
      "  operation:\n"
      "    fields:\n"
      "      - key: llm.prediction.temperature\n"
      "        value: 1.0\n"
      "      - key: llm.prediction.topKSampling\n"
      "        value: 20\n"
      "      - key: llm.prediction.topPSampling\n"
      "        value:\n"
      "          checked: true\n"
      "          value: 0.95\n"
      "      - key: llm.prediction.minPSampling\n"
      "        value:\n"
      "          checked: false\n"
      "          value: 0\n"
      "      - key: llm.prediction.llama.presencePenalty\n"
      "        value:\n"
      "          value: 1.5\n"
      "          checked: false\n"
      "      - key: llm.prediction.maxTokens\n"
      "        value: 512\n"
      "      - key: llm.prediction.repeatPenalty\n"
      "        value: high\n")

G1 = {"do_sample": True, "temperature": 0.6, "top_k": 20, "top_p": 0.95, "min_p": False, "eos_token_id": [1, 2]}
V_BAD = {"temperature": "hot", "seed": 3, "top_k": 40}


def run_autotest():
    tests = []
    # Test 1
    exp1 = ({"temperature": 1.0, "top_k": 20, "top_p": 0.95}, {})
    got1 = (from_model_yaml(Y1), from_model_yaml(""))
    tests.append((1, exp1, got1, got1 == exp1))
    # Test 2
    exp2 = ({"temperature": 0.6, "top_k": 20, "top_p": 0.95}, {})
    got2 = (from_generation_config(G1), from_generation_config([1]))
    tests.append((2, exp2, got2, got2 == exp2))
    # Test 3
    exp3 = (["sampling.temperature must be a number", "sampling.seed is not a known setting"], [], ["sampling must be an object"])
    got3 = (validate(V_BAD), validate({"top_p": 0.8}), validate("x"))
    tests.append((3, exp3, got3, got3 == exp3))
    # Test 4
    exp4 = (({"temperature": 0.7}, "models.json", None),
            ({"top_k": 20}, "publisher notice", None),
            (None, None, "no sampling settings: neither models.json nor a publisher notice"),
            (None, None, "no sampling settings: neither models.json nor a publisher notice"))
    got4 = (resolve({"temperature": 0.7}, {"temperature": 1.0}),
            resolve({}, {"top_k": 20}),
            resolve(None, {}),
            resolve(None, None))
    tests.append((4, exp4, got4, got4 == exp4))
    # Test 5
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__), "--notice"],
        capture_output=True,
        text=True
    )
    exp5 = (0, True)
    got5 = (proc.returncode, proc.stdout.startswith("NAME      sampling_rules.py"))
    tests.append((5, exp5, got5, got5 == exp5))

    all_passed = True
    for num, exp, got, ok in tests:
        if ok:
            print(f"PASS test {num}: expected {exp!r}, got {got!r}")
        else:
            print(f"FAIL test {num}: expected {exp!r}, got {got!r}")
            all_passed = False
    return 0 if all_passed else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(run_autotest())
    # No args or invalid -> usage, exit 2
    print("usage: sampling_rules.py --notice | --autotest")
    sys.exit(2)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "sampling_rules", sys.argv[1:])
