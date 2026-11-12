#!/usr/bin/env python3
# e2e_hook_isolated.py - D2: every hook command FrugalFlow writes launches
# python with -I, and a python startup file (.pth, usercustomize.py,
# sitecustomize.py) is protected wherever it sits.
# Each case prints one PASS or FAIL line; exit 1 if any case fails.

import json
import os
import shutil
import subprocess
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
BIN = os.path.join(ROOT, "bin")
HOOK = os.path.join(BIN, "guard_hook.py")

GUARD_BASE = {
    "code_extensions": [".py", ".sh", ".js", ".ts", ".ipynb"],
    "delegation_logs": ["delegations.jsonl"],
    "audit_log": "audit.jsonl",
    "line_threshold": 20,
    "receipt_minutes": 30,
    "delegate_tools": ["delegate.py"],
    "fix_hint": "delegate it.",
}

PREFS = {"schema_version": "1", "switch": {"enabled": True, "mode": "active"}}


def base_env(home_user, ff_home, shim_dir=None):
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("GIT_") or key.startswith("FRUGALFLOW_"):
            del env[key]
    # init changes a setting: frugalflow.py refuses it from a Claude Code session.
    env.pop("CLAUDECODE", None)
    env["HOME"] = home_user
    env["FRUGALFLOW_HOME"] = ff_home
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    path = "/opt/homebrew/bin:/usr/bin:/bin"
    if shim_dir:
        path = shim_dir + ":" + path
    env["PATH"] = path
    return env


def make_shim(shim_dir):
    """A console script named frugalflow, in python: the hooks launch it with -I."""
    os.makedirs(shim_dir, exist_ok=True)
    shim_file = os.path.join(shim_dir, "frugalflow")
    content = (
        "#!" + sys.executable + "\n"
        "import os\nimport sys\n"
        "os.execv(sys.executable, [sys.executable, '-I', "
        + repr(os.path.join(BIN, "frugalflow.py")) + "] + sys.argv[1:])\n"
    )
    with open(shim_file, "w", encoding="utf-8") as fh:
        fh.write(content)
    os.chmod(shim_file, 0o755)
    return shim_file


def run_hook(home_ff, home_user, work, payload):
    with open(os.path.join(home_ff, "guard.json"), "w", encoding="utf-8") as f:
        json.dump(GUARD_BASE, f)
    with open(os.path.join(home_ff, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    with open(os.path.join(home_user, "preferences.json"), "w", encoding="utf-8") as f:
        json.dump(PREFS, f)
    open(os.path.join(home_ff, "delegations.jsonl"), "w", encoding="utf-8").close()
    env = base_env(home_user, home_ff)
    r = subprocess.run(
        [sys.executable, HOOK, "--hook"],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        cwd=work,
        timeout=30,
    )
    return r.returncode, r.stdout.strip()


def last_output(stdout):
    if not stdout:
        return {}
    try:
        return json.loads(stdout.splitlines()[-1]).get("hookSpecificOutput", {})
    except (json.JSONDecodeError, KeyError, TypeError, IndexError):
        return {}


def decision(stdout):
    return last_output(stdout).get("permissionDecision", "allow")


def reason(stdout):
    return last_output(stdout).get("permissionDecisionReason", "")


def user_site(home, userbase=None):
    """Return (user site-packages folder, is the user site enabled) for a HOME.

    With userbase set, the folder is the one PYTHONUSERBASE points python at.
    """
    env = dict(os.environ)
    env["HOME"] = home
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    if userbase:
        env["PYTHONUSERBASE"] = userbase
    r = subprocess.run(
        [sys.executable, "-c",
         "import site; print(site.getusersitepackages()); print(site.ENABLE_USER_SITE)"],
        capture_output=True, text=True, env=env, timeout=30)
    lines = r.stdout.split()
    if len(lines) < 2:
        return None, False
    return lines[0], lines[-1] == "True"


def plant_pth(directory):
    """A .pth file whose one line ends python at once: the D2 attack."""
    os.makedirs(directory, exist_ok=True)
    with open(os.path.join(directory, "zz.pth"), "w", encoding="utf-8") as f:
        # Only a line starting with "import" is executed by the site module.
        f.write("import os; os._exit(0)\n")


def settings_commands(settings_path):
    with open(settings_path, encoding="utf-8") as f:
        doc = json.load(f)
    cmds = []
    hooks = doc.get("hooks")
    if isinstance(hooks, dict):
        for event in hooks.values():
            if not isinstance(event, list):
                continue
            for group in event:
                if not isinstance(group, dict):
                    continue
                entries = group.get("hooks")
                if not isinstance(entries, list):
                    continue
                for entry in entries:
                    if isinstance(entry, dict) and isinstance(entry.get("command"), str):
                        cmds.append(entry["command"])
    line = doc.get("statusLine")
    if isinstance(line, dict) and isinstance(line.get("command"), str):
        cmds.append(line["command"])
    return cmds


def main():
    tmp = tempfile.mkdtemp(prefix="e2e-hook-iso-")
    failures = 0
    cases = []
    try:
        # ---- (a) startup files are protected: Write, Edit and Bash writes refused
        home_a = os.path.join(tmp, "home_a")
        ff_a = os.path.join(tmp, "ff_a")
        work_a = os.path.join(tmp, "work_a")
        for d in (home_a, ff_a, work_a):
            os.makedirs(d)
        site_a, _ = user_site(home_a)
        targets = [os.path.join(work_a, "evil.pth"),
                   os.path.join(work_a, "usercustomize.py"),
                   os.path.join(work_a, "sitecustomize.py")]
        if site_a:
            targets.insert(0, os.path.join(site_a, "zz.pth"))
        for path in targets:
            _, out = run_hook(ff_a, home_a, work_a,
                              {"tool_name": "Write", "tool_input": {"file_path": path, "content": "import os\n"}})
            got = decision(out)
            ok = got == "deny" and "by hand" in reason(out)
            cases.append(("A Write of " + os.path.basename(path) + " refuses with the by-hand line", ok,
                          "expected deny + by hand, got " + got))
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Edit", "tool_input": {"file_path": os.path.join(work_a, "sitecustomize.py"),
                                                               "old_string": "a", "new_string": "b"}})
        cases.append(("A Edit of sitecustomize.py refuses", decision(out) == "deny",
                      "expected deny, got " + decision(out)))
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Bash", "tool_input": {"command": "echo x > " + os.path.join(work_a, "evil2.pth")}})
        cases.append(("A Bash write to a .pth file refuses", decision(out) == "deny",
                      "expected deny, got " + decision(out)))
        # 2026-11-12 (G2): a copy into a directory writes DEST/source-name; that
        # joined path is judged. Nothing is actually written here: the hook only judges.
        dest_dir = os.path.join(work_a, "DEST")
        os.makedirs(dest_dir, exist_ok=True)
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Bash", "tool_input": {"command": "cp /tmp/x.pth " + dest_dir + "/"}})
        cases.append(("A Bash cp of x.pth into a folder refuses", decision(out) == "deny",
                      "expected deny, got " + decision(out)))
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Bash", "tool_input": {"command": "cp x.pth /usr/local/lib/python3.11/dist-packages/"}})
        cases.append(("A Bash cp of x.pth into dist-packages refuses", decision(out) == "deny",
                      "expected deny, got " + decision(out)))
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Bash", "tool_input": {"command": "cp /tmp/x.txt " + dest_dir + "/"}})
        cases.append(("OK control: a Bash cp of x.txt into a folder allows", decision(out) == "allow",
                      "expected allow, got " + decision(out)))
        _, out = run_hook(ff_a, home_a, work_a,
                          {"tool_name": "Write", "tool_input": {"file_path": os.path.join(work_a, "ok.py"), "content": "a = 1\n"}})
        cases.append(("OK control: a small ordinary .py in the work folder allows", decision(out) == "allow",
                      "expected allow, got " + decision(out)))

        # ---- (b) an init in a throwaway HOME writes hook commands that all carry -I
        home_user = os.path.join(tmp, "home")
        ff_home = os.path.join(tmp, "ff")
        claude_dir = os.path.join(tmp, ".claude")
        work = os.path.join(tmp, "work")
        shim_dir = os.path.join(tmp, "shim")
        for d in (home_user, ff_home, claude_dir, work):
            os.makedirs(d)
        make_shim(shim_dir)
        env = base_env(home_user, ff_home, shim_dir)
        r = subprocess.run(
            [sys.executable, os.path.join(BIN, "frugalflow.py"), "init",
             "--home", ff_home, "--claude-dir", claude_dir,
             "--ollama-url", "http://127.0.0.1:1", "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=env, cwd=tmp, timeout=120)
        settings_path = os.path.join(claude_dir, "settings.json")
        cmds = settings_commands(settings_path) if r.returncode == 0 else []
        no_iso = [c for c in cmds if " -I " not in c]
        # init writes the guard hook, the banner hook and the status line.
        ok_b = r.returncode == 0 and len(cmds) >= 3 and not no_iso
        cases.append(("B init writes " + str(len(cmds)) + " hook commands, all with -I", ok_b,
                      "init rc=%d, commands=%d, without -I=%d" % (r.returncode, len(cmds), len(no_iso))))

        guard_cmd = None
        for c in cmds:
            if "run guard_hook" in c:
                guard_cmd = c
                break

        # ---- (c) the planted .pth attack: the exact init command, with and without -I
        # Compute both user-site folders before planting: a planted .pth would
        # end the very python that computes them.
        site_user, enabled = user_site(home_user)
        userbase = os.path.join(tmp, "userbase")
        site_base, _ = user_site(home_user, userbase)
        if site_user:
            plant_pth(site_user)
        if site_base:
            plant_pth(site_base)
        payload = json.dumps({"tool_name": "Write",
                              "tool_input": {"file_path": os.path.join(claude_dir, "settings.json"),
                                             "content": "{}"}})
        if guard_cmd:
            rc, out = run_sh(guard_cmd, payload, env, work)
            isolated_decision = decision(out)
            cases.append(("C with -I, the guard refuses a Write to settings.json despite the planted .pth",
                          isolated_decision == "deny", "expected deny, got " + isolated_decision))
            control_env = dict(env)
            control_env["PYTHONUSERBASE"] = userbase
            rc2, out2 = run_sh(guard_cmd.replace(" -I ", " "), payload, control_env, work)
            control_decision = decision(out2)
            cases.append(("C control without -I: the planted .pth ends python before the guard",
                          control_decision != "deny", "expected no deny, got " + control_decision
                          + (" (user site enabled: " + str(enabled) + ")" if control_decision == "deny" else "")))
        else:
            cases.append(("C with -I, the guard refuses a Write to settings.json despite the planted .pth",
                          False, "no guard_hook command found in settings.json"))

        # ---- (d) doctor fails when -I is removed from a hook command
        # A clean HOME: the planted .pth of case C would end the doctor's python.
        home_d = os.path.join(tmp, "home_d")
        os.makedirs(home_d)
        d0 = subprocess.run(
            [sys.executable, os.path.join(BIN, "doctor_cmd.py"), "--home", ff_home,
             "--claude-dir", claude_dir, "--ollama-url", "http://127.0.0.1:1",
             "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=base_env(home_d, ff_home), cwd=tmp, timeout=120)
        with open(settings_path, encoding="utf-8") as f:
            doc = json.load(f)
        stripped = 0
        for group in doc.get("hooks", {}).get("PreToolUse", []):
            for entry in group.get("hooks", []):
                if " -I " in entry.get("command", ""):
                    entry["command"] = entry["command"].replace(" -I ", " ")
                    stripped += 1
        with open(settings_path, "w", encoding="utf-8") as f:
            json.dump(doc, f)
        d1 = subprocess.run(
            [sys.executable, os.path.join(BIN, "doctor_cmd.py"), "--home", ff_home,
             "--claude-dir", claude_dir, "--ollama-url", "http://127.0.0.1:1",
             "--lmstudio-url", "http://127.0.0.1:1"],
            capture_output=True, text=True, env=base_env(home_d, ff_home), cwd=tmp, timeout=120)
        ok_d = d0.returncode == 0 and stripped > 0 and d1.returncode == 1 and "without -I" in d1.stdout
        cases.append(("D doctor fails when a hook command lost -I", ok_d,
                      "before rc=%d, stripped=%d, after rc=%d, line=%s"
                      % (d0.returncode, stripped, d1.returncode, "without -I" in d1.stdout)))

        for name, ok, detail in cases:
            if not ok:
                failures += 1
            print("%s  %s  (%s)" % ("PASS" if ok else "FAIL", name, detail))
        print("SUMMARY %d / %d" % (len(cases) - failures, len(cases)))
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    return 1 if failures else 0


def run_sh(command, payload, env, cwd):
    r = subprocess.run(["sh", "-c", command], input=payload, capture_output=True,
                       text=True, env=env, cwd=cwd, timeout=60)
    return r.returncode, r.stdout.strip()


if __name__ == "__main__":
    sys.exit(main())
