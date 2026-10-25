#!/usr/bin/env python3
import json
import os
import shutil
import subprocess
import sys
import tempfile

NOTICE = (
    "NAME      e2e_portable_hooks.py - end-to-end test that the hooks "
    "and the commit gate written by new-project and init hold no clone "
    "path, survive a move, and that the commit gate refuses a leak.\n"
    "READS     the tools in ../bin, copied to a temporary folder; "
    "nothing from the real home.\n"
    "WRITES    only in temporary folders, always removed. Exit 0 all "
    "steps pass, 1 a step failed, 2 usage.\n"
    "EXAMPLE   python3 e2e_portable_hooks.py\n"
    "PITFALLS  2026-10-25 hooks held the absolute path of the clone: "
    "moving it broke every hook without a word, and the commit gate "
    "never scanned for leaks.\n"
)

CLEAN_PY = "def add(a, b):\n    return a + b\n"

GIT_FLAGS = [
    "-c", "user.email=t@exemple.org",
    "-c", "user.name=tester",
    "-c", "commit.gpgsign=false",
]

EXCLUDE_DIRS = {"__pycache__", "tests", "bench"}


def copy_tree(src, dst):
    os.makedirs(dst, exist_ok=True)
    for name in os.listdir(src):
        if name in EXCLUDE_DIRS:
            continue
        src_path = os.path.join(src, name)
        dst_path = os.path.join(dst, name)
        if os.path.isdir(src_path):
            copy_tree(src_path, dst_path)
        else:
            shutil.copy2(src_path, dst_path)


def build_base_env(home_dir, pycache_dir):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_") or key.startswith("FRUGALFLOW_"):
            del env[key]
    env["HOME"] = home_dir
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONPYCACHEPREFIX"] = pycache_dir
    env["LC_ALL"] = "C"
    return env


def make_shim(shim_dir, clone_bin_path):
    os.makedirs(shim_dir, exist_ok=True)
    shim_file = os.path.join(shim_dir, "frugalflow")
    content = (
        "#!/bin/sh\n"
        "exec '" + sys.executable + "' '"
        + os.path.join(clone_bin_path, "frugalflow.py")
        + "' \"$@\"\n"
    )
    with open(shim_file, "w") as fh:
        fh.write(content)
    os.chmod(shim_file, 0o755)
    return shim_file


def env_with_cmd(base_env, shim_dir):
    env = dict(base_env)
    env["PATH"] = shim_dir + ":" + os.defpath
    return env


def env_no_cmd(base_env):
    env = dict(base_env)
    env["PATH"] = os.defpath
    return env


def run_sub(cmd, cwd, env, input_bytes=None, timeout=60):
    try:
        res = subprocess.run(
            cmd,
            cwd=cwd,
            env=env,
            input=input_bytes,
            capture_output=True,
            timeout=timeout,
        )
        return (
            res.returncode,
            res.stdout.decode("utf-8", errors="replace"),
            res.stderr.decode("utf-8", errors="replace"),
        )
    except subprocess.TimeoutExpired:
        return (-1, "", "TIMEOUT")
    except FileNotFoundError:
        return (127, "", "NOT FOUND")


def collect_commands(obj):
    cmds = []
    if isinstance(obj, dict):
        for key, val in obj.items():
            if key == "command" and isinstance(val, str):
                cmds.append(val)
            elif isinstance(val, (dict, list)):
                cmds.extend(collect_commands(val))
    elif isinstance(obj, list):
        for item in obj:
            cmds.extend(collect_commands(item))
    return cmds


def file_content(path):
    if not os.path.isfile(path):
        return None
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return fh.read()
    except (IOError, OSError):
        return None


def step1(tmp, clone_bin_a, env_cmd_a):
    expected = "exit 0, 0 occurrences of clone path, >=6 commands starting 'frugalflow run '"
    projects_dir = os.path.join(tmp, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    cmd = [sys.executable, os.path.join(clone_bin_a, "frugalflow.py"),
           "new-project", "demo", "--root", projects_dir]
    rc, out, err = run_sub(cmd, cwd=tmp, env=env_cmd_a, timeout=120)
    if rc != 0:
        return "FAIL " + expected + " | got exit=" + str(rc) + " err=" + err[:200], [], None

    demo_dir = os.path.join(projects_dir, "demo")
    settings_path = os.path.join(demo_dir, ".claude", "settings.json")
    hooks_path = os.path.join(demo_dir, ".githooks", "pre-commit")

    settings_text = file_content(settings_path)
    if settings_text is None or settings_text.strip() == "":
        return "FAIL " + expected + " | settings.json empty or missing", [], demo_dir
    hooks_text = file_content(hooks_path)
    if hooks_text is None or hooks_text.strip() == "":
        return "FAIL " + expected + " | pre-commit empty or missing", [], demo_dir

    if clone_bin_a in settings_text or "clone_a" in settings_text:
        return "FAIL " + expected + " | clone path in settings.json", [], demo_dir
    if clone_bin_a in hooks_text or "clone_a" in hooks_text:
        return "FAIL " + expected + " | clone path in pre-commit", [], demo_dir

    settings_obj = json.loads(settings_text)
    commands = collect_commands(settings_obj)
    if len(commands) < 6:
        return "FAIL " + expected + " | only " + str(len(commands)) + " commands", commands, demo_dir
    for c in commands:
        if not c.startswith("frugalflow run "):
            return "FAIL " + expected + " | command not starting 'frugalflow run ': " + c, commands, demo_dir

    return "PASS " + expected + " | exit=0, 0 clone paths, " + str(len(commands)) + " commands", commands, demo_dir


def step2(tmp, clone_bin_b, env_cmd_b, commands_list, project_dir):
    expected = "exit !=127, no 'No such file'/'can't open file'/'command not found'"
    seen = set()
    distinct = []
    for c in commands_list:
        if c not in seen:
            seen.add(c)
            distinct.append(c)
    if not distinct:
        return "FAIL " + expected + " | no commands to test"
    for cmd_str in distinct:
        rc, out, err = run_sub(["sh", "-c", cmd_str], cwd=project_dir,
                               env=env_cmd_b, input_bytes=b"{}", timeout=60)
        if rc == 127:
            return "FAIL " + expected + " | exit 127 for: " + cmd_str[:120]
        combined = out + err
        if "No such file" in combined or "can't open file" in combined:
            return "FAIL " + expected + " | file error for: " + cmd_str[:120]
        if "command not found" in combined:
            return "FAIL " + expected + " | not found for: " + cmd_str[:120]
    return "PASS " + expected + " | " + str(len(distinct)) + " commands ok"


def step3(project_dir, env_cmd_b):
    expected = "leak commit nonzero+FOUND, clean commit exit 0"
    leak_content = "api" + "_key = " + chr(34) + "abcd1234efgh5678ijkl" + chr(34)
    leak_path = os.path.join(project_dir, "leak.py")
    with open(leak_path, "w") as fh:
        fh.write(leak_content + "\n")

    rc1, out1, err1 = run_sub(["git"] + GIT_FLAGS + ["add", "leak.py"],
                              cwd=project_dir, env=env_cmd_b, timeout=30)
    if rc1 != 0:
        return "FAIL " + expected + " | git add failed: " + err1[:120]
    rc2, out2, err2 = run_sub(["git"] + GIT_FLAGS + ["commit", "-m", "leak"],
                              cwd=project_dir, env=env_cmd_b, timeout=30)
    if rc2 == 0:
        return "FAIL " + expected + " | leak commit should be nonzero but got 0"
    combined2 = out2 + err2
    if "FOUND" not in combined2:
        return "FAIL " + expected + " | no FOUND in commit output: " + combined2[:200]

    run_sub(["git"] + GIT_FLAGS + ["rm", "--cached", "-q", "leak.py"],
            cwd=project_dir, env=env_cmd_b, timeout=30)
    os.remove(leak_path)

    clean_path = os.path.join(project_dir, "clean.py")
    with open(clean_path, "w") as fh:
        fh.write(CLEAN_PY)
    rc3, out3, err3 = run_sub(["git"] + GIT_FLAGS + ["add", "clean.py"],
                              cwd=project_dir, env=env_cmd_b, timeout=30)
    if rc3 != 0:
        return "FAIL " + expected + " | git add clean failed: " + err3[:120]
    rc4, out4, err4 = run_sub(["git"] + GIT_FLAGS + ["commit", "-m", "clean"],
                              cwd=project_dir, env=env_cmd_b, timeout=30)
    if rc4 != 0:
        return "FAIL " + expected + " | clean commit got " + str(rc4) + " err: " + err4[:200]
    return "PASS " + expected + " | leak blocked, clean ok"


def step4(tmp, clone_bin_b, env_cmd_b):
    expected = "init exit 0, no clone path, has guard_hook; --remove exits 0, no guard_hook"
    claude_dir = os.path.join(tmp, "claude_dir_test4")
    os.makedirs(claude_dir, exist_ok=True)
    ff_home = os.path.join(tmp, "ffhome")
    os.makedirs(ff_home, exist_ok=True)

    init_cmd = [sys.executable, os.path.join(clone_bin_b, "frugalflow.py"),
                "init", "--home", ff_home, "--claude-dir", claude_dir,
                "--ollama-url", "http://127.0.0.1:1",
                "--lmstudio-url", "http://127.0.0.1:1"]
    rc, out, err = run_sub(init_cmd, cwd=tmp, env=env_cmd_b, timeout=120)
    if rc != 0:
        return "FAIL " + expected + " | init exit=" + str(rc) + " err=" + err[:200]

    settings_file = os.path.join(claude_dir, "settings.json")
    stext = file_content(settings_file)
    if stext is None or stext.strip() == "":
        return "FAIL " + expected + " | settings.json empty after init"
    if clone_bin_b in stext or "clone_b" in stext:
        return "FAIL " + expected + " | clone path in init settings"
    if "frugalflow run guard_hook --hook" not in stext:
        return "FAIL " + expected + " | guard_hook --hook not found in settings"

    remove_cmd = init_cmd + ["--remove"]
    rc2, out2, err2 = run_sub(remove_cmd, cwd=tmp, env=env_cmd_b, timeout=120)
    if rc2 != 0:
        return "FAIL " + expected + " | init --remove exit=" + str(rc2) + " err=" + err2[:200]
    stext2 = file_content(settings_file)
    if stext2 is None:
        return "PASS " + expected + " | guard_hook removed (file gone)"
    if "guard_hook" in stext2:
        return "FAIL " + expected + " | guard_hook still in settings after --remove"
    return "PASS " + expected + " | init and --remove ok"


def step5(tmp, clone_bin_b, env_no_cmd_b, script_path):
    expected = "no-cmd fallback has clone path no 'frugalflow run'; --bogus exit 2; --notice exit 0"
    projects_dir = os.path.join(tmp, "projects")
    os.makedirs(projects_dir, exist_ok=True)
    cmd = [sys.executable, os.path.join(clone_bin_b, "frugalflow.py"),
           "new-project", "plain", "--root", projects_dir]
    rc, out, err = run_sub(cmd, cwd=tmp, env=env_no_cmd_b, timeout=120)
    if rc != 0:
        return "FAIL " + expected + " | new-project plain exit=" + str(rc) + " err=" + err[:200]

    plain_settings = os.path.join(projects_dir, "plain", ".claude", "settings.json")
    stext = file_content(plain_settings)
    if stext is None or stext.strip() == "":
        return "FAIL " + expected + " | plain settings.json empty"
    if clone_bin_b not in stext:
        return "FAIL " + expected + " | clone path NOT in fallback settings"
    if "frugalflow run" in stext:
        return "FAIL " + expected + " | 'frugalflow run' present but should be absent"

    rc_bogus, out_bogus, err_bogus = run_sub(
        [sys.executable, script_path, "--bogus"], cwd=tmp,
        env=env_no_cmd_b, timeout=10)
    if rc_bogus != 2:
        return "FAIL " + expected + " | --bogus exit=" + str(rc_bogus) + " expected 2"

    rc_notice, out_notice, err_notice = run_sub(
        [sys.executable, script_path, "--notice"], cwd=tmp,
        env=env_no_cmd_b, timeout=10)
    if rc_notice != 0:
        return "FAIL " + expected + " | --notice exit=" + str(rc_notice) + " expected 0"

    return "PASS " + expected + " | fallback ok, usage exit 2, notice exit 0"


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        sys.stdout.write(NOTICE)
        return 0
    if len(argv) > 0:
        sys.stderr.write("usage: e2e_portable_hooks.py [--notice]\n")
        return 2

    script_path = os.path.abspath(__file__)
    here = os.path.dirname(script_path)
    public = os.path.dirname(here)

    tmp = tempfile.mkdtemp(prefix="e2eph_")
    results = []
    try:
        clone_a_dir = os.path.join(tmp, "clone_a")
        public_copy = os.path.join(clone_a_dir, "public")
        copy_tree(public, public_copy)
        clone_bin_a = os.path.join(public_copy, "bin")

        home_dir = os.path.join(tmp, "home")
        os.makedirs(home_dir, exist_ok=True)
        pycache_dir = tempfile.mkdtemp(prefix="e2eph_pyc_", dir=tmp)

        base_env = build_base_env(home_dir, pycache_dir)

        shim_a_dir = os.path.join(tmp, "shim_a")
        make_shim(shim_a_dir, clone_bin_a)
        env_cmd_a = env_with_cmd(base_env, shim_a_dir)

        result1, commands_list, project_dir = step1(tmp, clone_bin_a, env_cmd_a)
        results.append(result1)

        clone_b_dir = os.path.join(tmp, "clone_b")
        os.rename(clone_a_dir, clone_b_dir)
        clone_bin_b = os.path.join(clone_b_dir, "public", "bin")

        shim_b_dir = os.path.join(tmp, "shim_b")
        make_shim(shim_b_dir, clone_bin_b)
        env_cmd_b = env_with_cmd(base_env, shim_b_dir)
        env_no_cmd_b = env_no_cmd(base_env)

        result2 = step2(tmp, clone_bin_b, env_cmd_b, commands_list, project_dir)
        results.append(result2)

        result3 = step3(project_dir, env_cmd_b)
        results.append(result3)

        result4 = step4(tmp, clone_bin_b, env_cmd_b)
        results.append(result4)

        result5 = step5(tmp, clone_bin_b, env_no_cmd_b, script_path)
        results.append(result5)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    fail_count = 0
    for line in results:
        print(line)
        if line.startswith("FAIL "):
            fail_count += 1

    if fail_count == 0:
        print("E2E PORTABLE HOOKS OK")
        return 0
    else:
        print("E2E PORTABLE HOOKS FAILED " + str(fail_count))
        return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
