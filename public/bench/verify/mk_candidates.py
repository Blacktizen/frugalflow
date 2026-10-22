import sys
import os
import json
import subprocess
import tempfile
import shutil

CASES_IN = [(2, 3), (7, 2), (10, 5)]

TEMPLATE = (
    "import sys\n"
    "\n"
    "CASES = CASES_LITERAL\n"
    "\n"
    "\n"
    "def f(a, b):\n"
    "    return EXPR\n"
    "\n"
    "\n"
    "def autotest():\n"
    "    bad = 0\n"
    "    for a, b, want in CASES:\n"
    "        got = f(a, b)\n"
    "        if got == want:\n"
    "            print(\"PASS f(%d, %d) = %s\" % (a, b, want))\n"
    "        else:\n"
    "            print(\"FAIL f(%d, %d) expected %s got %s\" % (a, b, want, got))\n"
    "            bad += 1\n"
    "    return 1 if bad else 0\n"
    "\n"
    "\n"
    "if __name__ == \"__main__\":\n"
    "    if len(sys.argv) > 1 and sys.argv[1] == \"--autotest\":\n"
    "        sys.exit(autotest())\n"
    "    if len(sys.argv) == 3:\n"
    "        print(f(int(sys.argv[1]), int(sys.argv[2])))\n"
    "        sys.exit(0)\n"
    "    print(\"usage: NAME.py A B | --autotest\")\n"
    "    sys.exit(2)\n"
)

FIXTURE = (
    '[{"name": "addv", "good": "a + b", "bad": "a - b", "desc": "adds"},\n'
    ' {"name": "maxv", "good": "max(a, b)", "bad": "min(a, b)", "desc": "max"}]'
)


def compute_cases(good_expr):
    cases = []
    for a, b in CASES_IN:
        try:
            val = eval(good_expr, {}, {"a": a, "b": b, "max": max, "min": min, "abs": abs})
        except ZeroDivisionError:
            return None
        except Exception as e:
            print("eval error for good expression: %s" % e)
            return None
        cases.append((a, b, val))
    return cases


def render(name, expr, cases):
    return (
        TEMPLATE
        .replace("CASES_LITERAL", repr(cases))
        .replace("EXPR", expr)
        .replace("NAME", name)
    )


def generate(spec_path, out_dir):
    if not os.path.isfile(spec_path):
        sys.stderr.write("SPEC file not found: %s\n" % spec_path)
        return 2
    try:
        with open(spec_path, "r") as fh:
            specs = json.load(fh)
    except (json.JSONDecodeError, ValueError) as e:
        sys.stderr.write("invalid JSON: %s\n" % e)
        return 2
    if not isinstance(specs, list):
        sys.stderr.write("spec must be a JSON list\n")
        return 2

    os.makedirs(out_dir, exist_ok=True)
    os.makedirs(os.path.join(out_dir, "good"), exist_ok=True)
    os.makedirs(os.path.join(out_dir, "bad"), exist_ok=True)

    index = []
    for item in specs:
        name = item.get("name")
        good = item.get("good")
        bad = item.get("bad")
        desc = item.get("desc", "")
        if name is None or good is None or bad is None:
            sys.stderr.write("missing required key in spec entry: %s\n" % item)
            return 2

        cases = compute_cases(good)
        if cases is None:
            sys.stderr.write("eval failure in good expression of spec: %s\n" % name)
            return 3

        good_path = os.path.join(out_dir, "good", "%s.py" % name)
        bad_path = os.path.join(out_dir, "bad", "%s.py" % name)

        with open(good_path, "w") as fh:
            fh.write(render(name, good, cases))
        with open(bad_path, "w") as fh:
            fh.write(render(name, bad, cases))

        index.append({
            "name": name,
            "good_path": os.path.abspath(good_path),
            "bad_path": os.path.abspath(bad_path),
            "desc": desc,
        })

    with open(os.path.join(out_dir, "index.json"), "w") as fh:
        json.dump(index, fh, indent=2)
    return 0


def run_autotest():
    tmp = tempfile.mkdtemp()
    try:
        results = []

        spec_path = os.path.join(tmp, "spec.json")
        out_dir = os.path.join(tmp, "out")
        with open(spec_path, "w") as fh:
            fh.write(FIXTURE)
        proc = subprocess.run(
            [sys.executable, __file__, "--spec", spec_path, "--out", out_dir],
            capture_output=True, text=True,
        )
        rc1 = proc.returncode
        expected_files = [
            os.path.join(out_dir, "good", "addv.py"),
            os.path.join(out_dir, "bad", "addv.py"),
            os.path.join(out_dir, "good", "maxv.py"),
            os.path.join(out_dir, "bad", "maxv.py"),
            os.path.join(out_dir, "index.json"),
        ]
        all_exist = all(os.path.isfile(p) for p in expected_files)
        idx_ok = False
        if os.path.isfile(expected_files[-1]):
            try:
                with open(expected_files[-1], "r") as fh:
                    idx = json.load(fh)
                idx_ok = isinstance(idx, list) and len(idx) == 2
            except Exception:
                idx_ok = False
        if rc1 == 0 and all_exist and idx_ok:
            results.append("PASS test1 expected exit 0 + 5 files + index len 2; got exit %d exist=%s idx=%s" % (rc1, all_exist, idx_ok))
        else:
            results.append("FAIL test1 expected exit 0 + 5 files + index len 2; got exit %d exist=%s idx=%s" % (rc1, all_exist, idx_ok))

        p1 = subprocess.run(
            [sys.executable, os.path.join(out_dir, "good", "addv.py"), "--autotest"],
            capture_output=True, text=True,
        )
        p2 = subprocess.run(
            [sys.executable, os.path.join(out_dir, "bad", "addv.py"), "--autotest"],
            capture_output=True, text=True,
        )
        good_pass = p1.returncode == 0 and p1.stdout.count("PASS") == 3
        bad_fail = p2.returncode == 1 and p2.stdout.count("FAIL") >= 1
        if good_pass and bad_fail:
            results.append("PASS test2 expected good rc=0 3PASS bad rc=1 >=1FAIL; got good rc=%d pass=%d bad rc=%d fail=%d" % (p1.returncode, p1.stdout.count("PASS"), p2.returncode, p2.stdout.count("FAIL")))
        else:
            results.append("FAIL test2 expected good rc=0 3PASS bad rc=1 >=1FAIL; got good rc=%d pass=%d bad rc=%d fail=%d" % (p1.returncode, p1.stdout.count("PASS"), p2.returncode, p2.stdout.count("FAIL")))

        p3 = subprocess.run(
            [sys.executable, os.path.join(out_dir, "good", "maxv.py"), "7", "2"],
            capture_output=True, text=True,
        )
        p4 = subprocess.run(
            [sys.executable, os.path.join(out_dir, "bad", "maxv.py"), "7", "2"],
            capture_output=True, text=True,
        )
        ok3 = (p3.returncode == 0 and p3.stdout.strip() == "7")
        ok4 = (p4.returncode == 0 and p4.stdout.strip() == "2")
        if ok3 and ok4:
            results.append("PASS test3 expected good=maxv 7->7 bad=maxv 7->2; got good='%s' rc=%d bad='%s' rc=%d" % (p3.stdout.strip(), p3.returncode, p4.stdout.strip(), p4.returncode))
        else:
            results.append("FAIL test3 expected good=maxv 7->7 bad=maxv 7->2; got good='%s' rc=%d bad='%s' rc=%d" % (p3.stdout.strip(), p3.returncode, p4.stdout.strip(), p4.returncode))

        proc2 = subprocess.run(
            [sys.executable, __file__, "--spec", os.path.join(tmp, "no_such.json"), "--out", os.path.join(tmp, "out2")],
            capture_output=True, text=True,
        )
        spec_bad = os.path.join(tmp, "spec_bad.json")
        with open(spec_bad, "w") as fh:
            fh.write('[{"name": "divz", "good": "1 // (a - a)", "bad": "a + b", "desc": "zero div"}]')
        proc3 = subprocess.run(
            [sys.executable, __file__, "--spec", spec_bad, "--out", os.path.join(tmp, "out3")],
            capture_output=True, text=True,
        )
        ok_missing = proc2.returncode == 2
        ok_divz = proc3.returncode == 3
        if ok_missing and ok_divz:
            results.append("PASS test4 expected missing=2 divzero=3; got missing=%d divzero=%d" % (proc2.returncode, proc3.returncode))
        else:
            results.append("FAIL test4 expected missing=2 divzero=3; got missing=%d divzero=%d" % (proc2.returncode, proc3.returncode))

        for line in results:
            print(line)

        all_ok = all(line.startswith("PASS") for line in results)
        return 0 if all_ok else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    if len(sys.argv) >= 2 and sys.argv[1] == "--autotest":
        sys.exit(run_autotest())

    spec_path = None
    out_dir = None
    i = 1
    while i < len(sys.argv):
        if sys.argv[i] == "--spec" and i + 1 < len(sys.argv):
            spec_path = sys.argv[i + 1]
            i += 2
        elif sys.argv[i] == "--out" and i + 1 < len(sys.argv):
            out_dir = sys.argv[i + 1]
            i += 2
        else:
            i += 1

    if spec_path is None or out_dir is None:
        sys.stderr.write("usage: mk_candidates.py --spec SPEC.json --out DIR\n")
        sys.exit(2)

    rc = generate(spec_path, out_dir)
    sys.exit(rc)


if __name__ == "__main__":
    main()
