#!/usr/bin/env python3
"""End-to-end test of the INSTALLED package: copy the repo, pip install the copy
into a venv, then replay the three launch criteria against the venv, never the repo.

Exit 0 when the three criteria pass, 1 when one fails, 2 when the montage fails.
"""

import glob
import os
import re
import shutil
import subprocess
import sys
import tempfile

FAIL_RE = re.compile(r"(^|\W)FAIL(\W|$)")

NOTICE = (
    "NAME      e2e_installed.py - end-to-end test of the installed package: the repo is copied, pip installed into a venv, and the three launch criteria (every tool answers --notice; new-project then resume from a throwaway home; doctor without a FAIL line) are replayed against the venv.\n"
    "READS     ROOT (argument, else the repo folder above tests/); the copy, never ROOT itself.\n"
    "WRITES    a temp folder (venv, copy, throwaway home), deleted at the end; the OK/KO verdict lines on stdout.\n"
    "EXAMPLE   python3 e2e_installed.py /opt/ff/frugalflow\n"
    "PITFALLS  2026-11-14 the repo clone runs with its folder on sys.path while the installed tools run python -I without it: only the installed copy can prove the packaging, so this test never judges the clone.\n"
    "          2026-11-14 every frugalflow call runs with a clean environment (HOME, FRUGALFLOW_HOME, PATH, LANG, TERM set here, nothing inherited): a variable of the runner must not steer the verdict.\n"
)


def make_env(venv_bin, home):
    """Exact environment for every call to the installed package."""
    return {
        "HOME": home,
        "FRUGALFLOW_HOME": os.path.join(home, ".frugalflow"),
        "PATH": venv_bin + ":/usr/bin:/bin",
        "LANG": "en_US.UTF-8",
        "TERM": "dumb",
    }


def run_quiet(cmd, env=None, cwd=None):
    """Run a command with DEVNULL stdin and captured utf-8 text output."""
    return subprocess.run(
        cmd,
        env=env,
        cwd=cwd,
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )


def setup_montage(root, tmp):
    """Copy ROOT, build the venv, pip install the copy. None on any failure."""
    src = os.path.join(tmp, "src")
    shutil.copytree(
        root,
        src,
        ignore=shutil.ignore_patterns(".git", "__pycache__", "build", "*.egg-info"),
    )
    venv = os.path.join(tmp, "venv")
    result = run_quiet([sys.executable, "-m", "venv", venv])
    if result.returncode != 0:
        return None
    pip = os.path.join(venv, "bin", "pip")
    if not os.path.exists(pip):
        return None
    pip_env = dict(os.environ)
    pip_env["PIP_CACHE_DIR"] = os.path.join(tmp, "pipcache")
    result = run_quiet([pip, "install", src], env=pip_env)
    if result.returncode != 0:
        return None
    frugalflow = os.path.join(venv, "bin", "frugalflow")
    if not os.path.exists(frugalflow):
        return None
    pattern = os.path.join(
        venv, "lib", "*", "site-packages", "frugalflow_app", "bin", "*.py"
    )
    tools = []
    for path in sorted(glob.glob(pattern)):
        tool_name = os.path.basename(path)[:-3]
        if tool_name == "__init__":
            continue
        tools.append(tool_name)
    if not tools:
        return None
    home = os.path.join(tmp, "home")
    os.makedirs(home, exist_ok=True)
    env = make_env(os.path.join(venv, "bin"), home)
    return frugalflow, tools, home, env


def criterion_a(frugalflow, tools, env, home):
    """run --notice on every installed tool; floor of 60 tools."""
    count = len(tools)
    failures = 0
    for tool_name in tools:
        result = run_quiet([frugalflow, "run", tool_name, "--notice"], env=env, cwd=home)
        if result.returncode != 0:
            failures += 1
            first = (result.stderr or "").splitlines()
            detail = first[0] if first else "empty stderr"
            print("    failing tool: %s rc=%d | %s" % (tool_name, result.returncode, detail))
    if count >= 60 and failures == 0:
        print("OK  a run --notice: %d tools, 0 failures" % count)
        return True
    print("KO  a run --notice: %d tools, %d failures" % (count, failures))
    return False


def criterion_b(frugalflow, env, home):
    """The two README quickstart commands, replayed verbatim through /bin/sh -c."""
    first = run_quiet(["/bin/sh", "-c", "frugalflow new-project myapp --root ~/projects"],
                      env=env, cwd=home)
    second = run_quiet(["/bin/sh", "-c", "frugalflow resume"], env=env, cwd=home)
    if first.returncode == 0 and second.returncode == 0:
        print("OK  b quickstart: new-project=%d resume=%d"
              % (first.returncode, second.returncode))
        return True
    print("KO  b quickstart: new-project=%d resume=%d"
          % (first.returncode, second.returncode))
    return False


def criterion_c(frugalflow, env, home):
    """doctor output: non-empty and zero isolated FAIL lines."""
    result = run_quiet([frugalflow, "doctor"], env=env, cwd=home)
    lines = (result.stdout or "").splitlines() + (result.stderr or "").splitlines()
    total = len(lines)
    fails = 0
    for line in lines:
        if FAIL_RE.search(line):
            fails += 1
    if total > 0 and fails == 0:
        print("OK  c doctor: 0 FAIL lines, %d lines" % total)
        return True
    print("KO  c doctor: %d FAIL lines, %d lines" % (fails, total))
    return False


def main(argv):
    if argv == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if argv:
        root = os.path.abspath(argv[0])
    else:
        root = os.path.dirname(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
    if not os.path.isdir(root) or not os.path.isfile(os.path.join(root, "pyproject.toml")):
        print("KO  montage: no repo with pyproject.toml at " + root)
        return 2
    tmp = tempfile.mkdtemp(prefix="e2e-installed-")
    try:
        montage = setup_montage(root, tmp)
        if montage is None:
            print("KO  montage: copy, venv or pip install failed")
            return 2
        frugalflow, tools, home, env = montage
        ok_a = criterion_a(frugalflow, tools, env, home)
        ok_b = criterion_b(frugalflow, env, home)
        ok_c = criterion_c(frugalflow, env, home)
        if ok_a and ok_b and ok_c:
            print("E2E INSTALLED OK 3/3")
            return 0
        print("E2E INSTALLED FAILED")
        return 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
