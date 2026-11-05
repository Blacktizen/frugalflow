#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
import tempfile
import shutil


def find_repo_root(start_path):
    """Find the repo root by looking for public/bin/init_cmd.py"""
    path = os.path.abspath(start_path)
    while path != "/":
        if os.path.isfile(os.path.join(path, "public", "bin", "init_cmd.py")):
            return path
        path = os.path.dirname(path)
    return None


REPO_ROOT = find_repo_root(__file__)
if REPO_ROOT is None:
    print("FAIL cannot find repo root")
    sys.exit(1)

INIT_CMD = os.path.join(REPO_ROOT, "public", "bin", "init_cmd.py")
DOCTOR_CMD = os.path.join(REPO_ROOT, "public", "bin", "doctor_cmd.py")
SETTINGS_MERGE = os.path.join(REPO_ROOT, "public", "bin", "settings_merge.py")
BIN_DIR = os.path.join(REPO_ROOT, "public", "bin")

# Minimal PATH for isolation
ISOLATED_PATH = "/opt/homebrew/bin:/usr/bin:/bin"


def run(cmd, cwd=None, env=None, input_data=None, capture=True):
    """Run a command and return (returncode, stdout, stderr)"""
    test_env = dict(os.environ)
    test_env["PATH"] = ISOLATED_PATH
    if env:
        test_env.update(env)
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        env=test_env,
        input=input_data,
        capture_output=capture,
        text=True,
    )
    return proc.returncode, proc.stdout, proc.stderr


def read_settings_hook(claude_dir):
    """Read the guard hook command from settings.json"""
    settings_path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(settings_path):
        return None
    with open(settings_path, encoding="utf-8") as f:
        doc = json.load(f)
    hooks = doc.get("hooks", {})
    pre = hooks.get("PreToolUse", [])
    for group in pre:
        entries = group.get("hooks", [])
        for entry in entries:
            cmd = entry.get("command", "")
            if "guard_hook" in cmd and "--hook" in cmd:
                return cmd
    return None


def count_guard_entries(claude_dir):
    """Count the number of guard hook entries in settings.json"""
    settings_path = os.path.join(claude_dir, "settings.json")
    if not os.path.isfile(settings_path):
        return 0
    with open(settings_path, encoding="utf-8") as f:
        doc = json.load(f)
    hooks = doc.get("hooks", {})
    pre = hooks.get("PreToolUse", [])
    count = 0
    for group in pre:
        entries = group.get("hooks", [])
        for entry in entries:
            cmd = entry.get("command", "")
            if "guard_hook" in cmd and "--hook" in cmd:
                count += 1
    return count


def main():
    repo_root_arg = sys.argv[1] if len(sys.argv) > 1 else REPO_ROOT
    fail_k = 0

    # Case a: init in disposable dirs, guard command ends with " || exit 2"
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = {"HOME": tmp, "FRUGALFLOW_HOME": home}
        rc, out, err = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_a = (rc == 0)
        cmd = read_settings_hook(claude)
        if cmd:
            ok_a = ok_a and cmd.endswith(" || exit 2")
            parts = shlex.split(cmd)
            ok_a = ok_a and len(parts) == 6
        else:
            ok_a = False
        tag_a = "PASS" if ok_a else "FAIL"
        print(f"{tag_a} a init installs guard command ending with ' || exit 2' (6 shlex tokens) | rc={rc} cmd={cmd!r}")
        if not ok_a:
            fail_k += 1

    # Case b: replace interpreter with /nonexistent/python3, run hook with stdin {}, expect exit 2
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = {"HOME": tmp, "FRUGALFLOW_HOME": home}
        rc, out, err = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_b = (rc == 0)
        cmd = read_settings_hook(claude)
        if cmd:
            # Replace the python interpreter with /nonexistent/python3 (first word before space)
            first_space = cmd.find(' ')
            if first_space > 0:
                bad_cmd = "/nonexistent/python3" + cmd[first_space:]
            else:
                bad_cmd = "/nonexistent/python3"
            rc2, out2, err2 = run(["/bin/sh", "-c", bad_cmd], input_data="{}")
            ok_b = ok_b and rc2 == 2
        else:
            ok_b = False
        tag_b = "PASS" if ok_b else "FAIL"
        print(f"{tag_b} b hook with nonexistent interpreter exits 2 | rc={rc2 if ok_b else 'N/A'}")
        if not ok_b:
            fail_k += 1

    # Case c: run init a second time, guard entry count stays 1, settings.json identical byte-for-byte
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = {"HOME": tmp, "FRUGALFLOW_HOME": home}
        rc1, out1, err1 = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_c = (rc1 == 0)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "rb") as f:
            content1 = f.read()
        count1 = count_guard_entries(claude)

        rc2, out2, err2 = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_c = ok_c and (rc2 == 0)
        with open(settings_path, "rb") as f:
            content2 = f.read()
        count2 = count_guard_entries(claude)
        ok_c = ok_c and (count1 == 1) and (count2 == 1) and (content1 == content2)
        tag_c = "PASS" if ok_c else "FAIL"
        print(f"{tag_c} c second init: guard entries={count2}, settings identical={content1 == content2}")
        if not ok_c:
            fail_k += 1

    # Case d: simulate OLD form (remove " || exit 2"), run init again, single entry, now ends with " || exit 2"
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = {"HOME": tmp, "FRUGALFLOW_HOME": home}
        rc1, out1, err1 = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_d = (rc1 == 0)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Replace the guard command to remove " || exit 2"
        new_content = content.replace(" || exit 2", "")
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        # Verify it's the old form
        cmd = read_settings_hook(claude)
        ok_d = ok_d and cmd is not None and not cmd.endswith(" || exit 2")

        # Run init again
        rc2, out2, err2 = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_d = ok_d and (rc2 == 0)
        count = count_guard_entries(claude)
        cmd = read_settings_hook(claude)
        ok_d = ok_d and (count == 1) and cmd is not None and cmd.endswith(" || exit 2")
        tag_d = "PASS" if ok_d else "FAIL"
        print(f"{tag_d} d old form upgraded: guard entries={count}, cmd ends with ' || exit 2'={cmd.endswith(' || exit 2') if cmd else False}")
        if not ok_d:
            fail_k += 1

    # Case e: doctor on settings.json with /nonexistent/python3 interpreter -> FAIL line
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        claude = os.path.join(tmp, "claude")
        env = {"HOME": tmp, "FRUGALFLOW_HOME": home}
        rc1, out1, err1 = run(
            [sys.executable, INIT_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_e = (rc1 == 0)
        settings_path = os.path.join(claude, "settings.json")
        with open(settings_path, "r", encoding="utf-8") as f:
            content = f.read()
        # Replace the python interpreter with /nonexistent/python3
        new_content = content.replace(sys.executable, "/nonexistent/python3", 1)
        with open(settings_path, "w", encoding="utf-8") as f:
            f.write(new_content)

        rc2, out2, err2 = run(
            [sys.executable, DOCTOR_CMD, "--home", home, "--claude-dir", claude,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            env=env
        )
        ok_e = ok_e and (rc2 == 1) and ("FAIL hook interpreter does not exist: /nonexistent/python3" in out2)
        tag_e = "PASS" if ok_e else "FAIL"
        print(f"{tag_e} e doctor fails on nonexistent interpreter | rc={rc2} fail_line={'FAIL hook interpreter does not exist' in out2}")
        if not ok_e:
            fail_k += 1

    if fail_k == 0:
        print("E2E HOOK FAIL CLOSED OK")
        sys.exit(0)
    else:
        print(f"E2E HOOK FAIL CLOSED FAILED {fail_k}")
        sys.exit(1)


if __name__ == "__main__":
    main()