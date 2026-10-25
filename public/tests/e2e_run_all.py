import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
RUN = os.path.join(HERE, "run_all.py")

OKTOOL = 'import sys\nif "--autotest" in sys.argv:\n    print("PASS 1 fine")\n    sys.exit(0)\n'
BADTOOL = 'import sys\nif "--autotest" in sys.argv:\n    print("PASS 1 looks fine")\n    sys.exit(1)\n'
OKE2E = 'print("E2E OK")\n'
BADE2E = 'import sys\nprint("E2E FAILED")\nsys.exit(1)\n'

NOTICE = (
    "NAME      e2e_run_all.py - proves run_all.py exits non-zero whenever an autotest or an E2E fails.\n"
    "READS     run_all.py next to this file; builds fake trees in temporary folders.\n"
    "WRITES    temporary folders only; one PASS or FAIL line per case, then E2E RUN_ALL OK (0) or FAILED (1).\n"
    "EXAMPLE   python3 e2e_run_all.py\n"
    "PITFALLS  2026-10-25 the README loop ended with echo and exited 0 on a failed suite."
)


def tree(files):
    d = tempfile.mkdtemp()
    for rel, txt in files.items():
        p = os.path.join(d, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w") as f:
            f.write(txt)
    return d


def run(root, *extra):
    try:
        p = subprocess.run([sys.executable, RUN, "--root", root] + list(extra),
                           capture_output=True, text=True, timeout=120)
        return p.returncode, p.stdout + p.stderr
    except Exception as e:
        return 99, "crash: " + str(e)


def main():
    results = []

    d = tree({"bin/z_ok.py": OKTOOL, "tests/e2e_ok.py": OKE2E})
    rc, out = run(d)
    results.append(("all good: exit 0 and RUN ALL OK", rc == 0 and "RUN ALL OK" in out))
    shutil.rmtree(d, ignore_errors=True)

    d = tree({"bin/a_bad.py": BADTOOL, "bin/z_ok.py": OKTOOL, "tests/e2e_ok.py": OKE2E})
    rc, out = run(d)
    results.append(("bad autotest (prints PASS, exits 1): non-zero, FAIL names it, the rest still ran",
                    rc != 0 and "FAIL" in out and "a_bad.py" in out and "z_ok.py" in out and "e2e_ok.py" in out))
    shutil.rmtree(d, ignore_errors=True)

    d = tree({"bin/z_ok.py": OKTOOL, "tests/e2e_bad.py": BADE2E})
    rc, out = run(d)
    results.append(("bad E2E: non-zero and FAIL names it", rc != 0 and "FAIL" in out and "e2e_bad.py" in out))
    shutil.rmtree(d, ignore_errors=True)

    d = tree({"bin/a_bad.py": BADTOOL, "bin/z_ok.py": OKTOOL})
    rc, out = run(d, "--fail-fast")
    results.append(("--fail-fast: non-zero and the item after the failure is not run",
                    rc != 0 and "a_bad.py" in out and "z_ok.py" not in out))
    shutil.rmtree(d, ignore_errors=True)

    rc, out = run(os.path.join(tempfile.gettempdir(), "no-such-root-xyz"))
    results.append(("missing root: non-zero", rc not in (0, 99)))

    ok = True
    for i, (name, good) in enumerate(results, 1):
        print(("PASS " if good else "FAIL ") + str(i) + " " + name)
        ok = ok and good
    print("E2E RUN_ALL OK" if ok else "E2E RUN_ALL FAILED")
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    if "--notice" in sys.argv:
        print(NOTICE)
        sys.exit(0)
    main()
