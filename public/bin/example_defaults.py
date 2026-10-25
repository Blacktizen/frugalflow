import json
import os
import subprocess
import sys
import tempfile


NOTICE = (
    "NAME      example_defaults.py - gives a tool the default of a setting by "
    "reading the documented example file, so no default hides in code.\n"
    "READS     <config dir>/<name>.example.json; FRUGALFLOW_EXAMPLES, when set, "
    "replaces the config dir.\n"
    "WRITES    nothing: get() returns the value, a missing file or key raises "
    "ValueError; --get prints it as JSON.\n"
    "EXAMPLE   python3 example_defaults.py --get guard line_threshold\n"
    "PITFALLS  2026-10-25 a default written in code drifted from the example file "
    "and a stranger got the maintainer value; the example file is now the only "
    "source.\n"
)


def config_dir():
    env = os.environ.get("FRUGALFLOW_EXAMPLES")
    if env and env.strip():
        return env
    return os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config"
    )


def load(name):
    path = os.path.join(config_dir(), name + ".example.json")
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
    except (FileNotFoundError, OSError, json.JSONDecodeError):
        raise ValueError("example defaults missing: " + name)
    if not isinstance(data, dict):
        raise ValueError("example defaults missing: " + name)
    return data


def get(name, dotted):
    data = load(name)
    keys = dotted.split(".")
    current = data
    for key in keys:
        if not isinstance(current, dict) or key not in current:
            raise ValueError("no example default: " + name + "." + dotted)
        current = current[key]
    return current


def run_autotest():
    tmp = tempfile.mkdtemp()
    fixture = '{"limits": {"retries": 7, "mode": "calm"}, "flag": true}'
    filepath = os.path.join(tmp, "demo.example.json")
    with open(filepath, "w", encoding="utf-8") as fh:
        fh.write(fixture)

    results = []

    # Test 1
    try:
        os.environ["FRUGALFLOW_EXAMPLES"] = tmp
        val1 = get("demo", "limits.retries")
        with open(filepath, "w", encoding="utf-8") as fh:
            fh.write('{"limits": {"retries": 9, "mode": "calm"}, "flag": true}')
        val2 = get("demo", "limits.retries")
        if val1 == 7 and val2 == 9:
            results.append("PASS expected=7,9 obtained=" + str(val1) + "," + str(val2))
        else:
            results.append("FAIL expected=7,9 obtained=" + str(val1) + "," + str(val2))
    except Exception as exc:
        results.append("FAIL expected=7,9 obtained=" + str(exc))
    finally:
        os.environ.pop("FRUGALFLOW_EXAMPLES", None)

    # Test 2
    try:
        os.environ.pop("FRUGALFLOW_EXAMPLES", None)
        cd_no_env = config_dir()
        ends_config = cd_no_env.endswith("config")
        no_tmp = tmp not in cd_no_env
        os.environ["FRUGALFLOW_EXAMPLES"] = tmp
        cd_with_env = config_dir()
        equal_tmp = cd_with_env == tmp
        if ends_config and no_tmp and equal_tmp:
            results.append(
                "PASS expected=ends_config,no_tmp,equal_tmp obtained="
                + str(ends_config) + "," + str(no_tmp) + "," + str(equal_tmp)
            )
        else:
            results.append(
                "FAIL expected=ends_config,no_tmp,equal_tmp obtained="
                + str(ends_config) + "," + str(no_tmp) + "," + str(equal_tmp)
            )
    except Exception as exc:
        results.append("FAIL expected=ends_config,no_tmp,equal_tmp obtained=" + str(exc))
    finally:
        os.environ.pop("FRUGALFLOW_EXAMPLES", None)

    # Test 3
    try:
        env = dict(os.environ)
        env["FRUGALFLOW_EXAMPLES"] = tmp
        script = os.path.abspath(__file__)
        proc = subprocess.run(
            [sys.executable, script, "--get", "demo", "limits.mode"],
            capture_output=True, text=True, env=env
        )
        expected_out = '"calm"\n'
        ok = proc.returncode == 0 and proc.stdout == expected_out
        if ok:
            results.append(
                "PASS expected=exit0,stdout=calm obtained=exit"
                + str(proc.returncode) + ",stdout=" + repr(proc.stdout)
            )
        else:
            results.append(
                "FAIL expected=exit0,stdout=calm obtained=exit"
                + str(proc.returncode) + ",stdout=" + repr(proc.stdout)
            )
    except Exception as exc:
        results.append("FAIL expected=exit0,stdout=calm obtained=" + str(exc))

    # Test 4 (exit 3 + exit 2)
    try:
        env = dict(os.environ)
        env["FRUGALFLOW_EXAMPLES"] = tmp
        script = os.path.abspath(__file__)
        proc_err = subprocess.run(
            [sys.executable, script, "--get", "demo", "limits.nothing"],
            capture_output=True, text=True, env=env
        )
        msg_ok = "no example default: demo.limits.nothing" in proc_err.stdout
        proc_usage = subprocess.run(
            [sys.executable, script],
            capture_output=True, text=True
        )
        usage_ok = "usage:" in proc_usage.stdout
        ok = proc_err.returncode == 3 and msg_ok and proc_usage.returncode == 2 and usage_ok
        if ok:
            results.append(
                "PASS expected=exit3+exit2 obtained=exit"
                + str(proc_err.returncode) + "+exit" + str(proc_usage.returncode)
            )
        else:
            results.append(
                "FAIL expected=exit3+exit2 obtained=exit"
                + str(proc_err.returncode) + "+exit" + str(proc_usage.returncode)
            )
    except Exception as exc:
        results.append("FAIL expected=exit3+exit2 obtained=" + str(exc))

    for line in results:
        print(line)

    passed = sum(1 for r in results if r.startswith("PASS"))
    total = len(results)
    print("AUTOTEST " + str(passed) + "/" + str(total))

    if any(r.startswith("FAIL") for r in results):
        return 1
    return 0


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        print(NOTICE, end="")
        return 0
    if len(argv) >= 3 and argv[0] == "--get":
        name = argv[1]
        dotted = argv[2]
        try:
            value = get(name, dotted)
        except ValueError as exc:
            print(str(exc))
            return 3
        print(json.dumps(value))
        return 0
    if len(argv) == 1 and argv[0] == "--autotest":
        return run_autotest()
    print("usage: example_defaults.py --get NAME DOTTED | --notice | --autotest")
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
