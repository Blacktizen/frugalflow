import shutil, subprocess, sys
from pathlib import Path
S = Path(sys.argv[1]); tool = sys.argv[2]
shutil.copytree(S / "root_c0", S / "root_c3", dirs_exist_ok=True)
for i in range(1, 11):
    m = "m%02d" % i
    out = subprocess.run([sys.executable, tool, "--vault", str(S / "root_c1" / m / "setup" / "vault")], capture_output=True, text=True, check=True).stdout.splitlines()
    out[0] = "RESUME of the previous session"
    lines = (S / "root_c0" / m / "task.md").read_text().splitlines()
    body = lines[:2] + ["The previous session left this resume (there is no other memory to look for):", ""] + out + ["", lines[-1]]
    (S / "root_c3" / m / "task.md").write_text("\n".join(body) + "\n")
