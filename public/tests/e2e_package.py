import os
import sys
import shutil
import subprocess
import tempfile
import tomllib

UNAVAILABLE = ["No matching distribution", "Could not find a version", "Connection", "Temporary failure", "No module named pip"]


def main():
    env_root = os.environ.get("FRUGALFLOW_ROOT", "")
    if env_root:
        root = env_root
    else:
        root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    passes = 0
    tmp_dirs = []
    wheel_path = None
    tmp_venv = None

    try:
        # --- Epreuve 1 ---
        if True:
            try:
                with open(os.path.join(root, "pyproject.toml"), "rb") as f:
                    data = tomllib.load(f)
                proj = data["project"]
                if proj.get("name") != "frugalflow":
                    raise AssertionError("project.name != frugalflow")
                if proj.get("requires-python") != ">=3.11":
                    raise AssertionError("project.requires-python != >=3.11")
                if proj.get("dependencies") != []:
                    raise AssertionError("project.dependencies != []")
                if proj.get("license") != "MIT":
                    raise AssertionError("project.license != MIT")
                if "frugalflow" not in proj.get("scripts", {}):
                    raise AssertionError("project.scripts missing key frugalflow")
                print("PASS 1 pyproject fields")
                passes += 1
            except Exception as e:
                print("FAIL 1 " + repr(e))
                tmp_venv = None

        # --- Epreuve 2 ---
        if tmp_venv is None and passes < 1:
            print("FAIL skipped: 1")
        elif passes >= 1:
            try:
                tmp_src = tempfile.mkdtemp()
                tmp_dist = tempfile.mkdtemp()
                tmp_dirs.extend([tmp_src, tmp_dist])
                src_dir = os.path.join(tmp_src, "src")
                shutil.copytree(root, src_dir, ignore=shutil.ignore_patterns(".git", "__pycache__", "*.pyc"))
                res = subprocess.run(
                    [sys.executable, "-m", "pip", "wheel", "--no-deps", "-q", "-w", tmp_dist, src_dir],
                    timeout=600,
                    capture_output=True,
                )
                if res.returncode != 0:
                    combined = res.stdout.decode("utf-8", errors="replace") + res.stderr.decode("utf-8", errors="replace")
                    if any(s in combined for s in UNAVAILABLE):
                        print("SKIP no index or pip available for the build backend")
                        print("E2E PACKAGE SKIPPED")
                        return 0
                    raise AssertionError("pip wheel exit " + str(res.returncode))
                wheels = [f for f in os.listdir(tmp_dist) if f.endswith(".whl")]
                if len(wheels) != 1:
                    raise AssertionError("expected 1 .whl got " + str(len(wheels)))
                wheel_path = os.path.join(tmp_dist, wheels[0])
                print("PASS 2 wheel built")
                passes += 1
            except Exception as e:
                print("FAIL 2 " + repr(e))
                passes -= 0  # already not incremented
                wheel_path = None

        # --- Epreuve 3 ---
        if wheel_path is None and passes < 2:
            print("FAIL skipped: 2")
        elif passes >= 2:
            try:
                tmp_venv = tempfile.mkdtemp()
                tmp_dirs.append(tmp_venv)
                res = subprocess.run([sys.executable, "-m", "venv", tmp_venv], timeout=120)
                if res.returncode != 0:
                    raise AssertionError("venv exit " + str(res.returncode))
                if os.name == "nt":
                    pip_bin = os.path.join(tmp_venv, "Scripts", "pip.exe")
                else:
                    pip_bin = os.path.join(tmp_venv, "bin", "pip")
                res = subprocess.run([pip_bin, "install", "-q", "--no-index", "--no-deps", wheel_path], timeout=120)
                if res.returncode != 0:
                    raise AssertionError("pip install exit " + str(res.returncode))
                print("PASS 3 installed in a fresh venv")
                passes += 1
            except Exception as e:
                print("FAIL 3 " + repr(e))
                tmp_venv = None

        # --- Epreuve 4 ---
        if tmp_venv is None and passes < 3:
            print("FAIL skipped: 3")
        elif passes >= 3:
            try:
                if os.name == "nt":
                    FRUGAL = os.path.join(tmp_venv, "Scripts", "frugalflow.exe")
                else:
                    FRUGAL = os.path.join(tmp_venv, "bin", "frugalflow")
                tmp_home = tempfile.mkdtemp()
                tmp_dirs.append(tmp_home)
                H = os.path.join(tmp_home, "ff")
                C = os.path.join(tmp_home, "cl")
                os.makedirs(H, exist_ok=True)
                os.makedirs(C, exist_ok=True)

                env = os.environ.copy()
                env["HOME"] = tmp_home
                env["USERPROFILE"] = tmp_home
                env.pop("FRUGALFLOW_HOME", None)

                CMD_A = [FRUGAL, "--help"]
                CMD_B = [FRUGAL, "init", "--home", H, "--claude-dir", C, "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"]
                CMD_C = [FRUGAL, "doctor", "--home", H, "--claude-dir", C, "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"]

                r = subprocess.run(CMD_A, timeout=120, capture_output=True, env=env)
                if r.returncode != 0 or "usage: frugalflow" not in r.stdout.decode("utf-8", errors="replace"):
                    raise AssertionError("4a code=" + str(r.returncode))

                r = subprocess.run(CMD_B, timeout=120, capture_output=True, env=env)
                if r.returncode != 0 or not os.path.isfile(os.path.join(H, "models.json")):
                    raise AssertionError("4b code=" + str(r.returncode))

                r = subprocess.run(CMD_C, timeout=120, capture_output=True, env=env)
                if r.returncode != 0:
                    raise AssertionError("4c code=" + str(r.returncode))

                print("PASS 4 frugalflow --help, init, doctor in a blank HOME")
                passes += 1
            except Exception as e:
                print("FAIL 4 " + repr(e))

        print("E2E PACKAGE " + str(passes) + "/4")
        return 0 if passes == 4 else 1

    finally:
        for d in tmp_dirs:
            shutil.rmtree(d, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
