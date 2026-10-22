import os
import sys
import shutil
import subprocess
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
TASKS = ["u01", "u02", "u03", "u04", "u05", "u06", "u07", "u08", "u09", "u10"]


def run_check(task, overlay):
    tmp = tempfile.mkdtemp(prefix="bench_")
    try:
        setup = os.path.join(ROOT, task, "setup")
        for name in os.listdir(setup):
            src = os.path.join(setup, name)
            dst = os.path.join(tmp, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
        if overlay and os.path.isdir(overlay):
            for name in os.listdir(overlay):
                src = os.path.join(overlay, name)
                dst = os.path.join(tmp, name)
                if os.path.isdir(src):
                    if os.path.isdir(dst):
                        shutil.rmtree(dst)
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        env = dict(os.environ)
        env["PYTHONPATH"] = tmp
        visible_ok = True
        if os.path.exists(os.path.join(tmp, "test_visible.py")):
            p = subprocess.run([sys.executable, "test_visible.py"], cwd=tmp,
                               env=env, capture_output=True, text=True)
            visible_ok = p.returncode == 0
        p = subprocess.run([sys.executable, os.path.join(ROOT, task, "check.py")],
                           cwd=tmp, env=env, capture_output=True, text=True)
        return p.returncode == 0, visible_ok, p.stdout, p.stderr
    finally:
        shutil.rmtree(tmp)


all_ok = True
for t in TASKS:
    td = os.path.join(ROOT, t)
    naive_check, naive_vis, _, _ = run_check(t, os.path.join(td, "naive"))
    sol_check, sol_vis, _, _ = run_check(t, os.path.join(td, "solution"))
    naive_color = "RED" if not naive_check else "GREEN"
    sol_color = "GREEN" if sol_check else "RED"
    good = (not naive_check) and sol_check and naive_vis and sol_vis
    print("%s naive=%s solution=%s" % (t, naive_color, sol_color))
    if not good:
        all_ok = False
sys.exit(0 if all_ok else 1)
