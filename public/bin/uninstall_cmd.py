import sys
import os
import subprocess
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import setup_manifest
import init_cmd

USAGE = "usage: uninstall_cmd.py [--home DIR] [--claude-dir DIR] | --notice | --autotest"

NOTICE = (
    "NAME      uninstall_cmd.py - the frugalflow uninstall subcommand: "
    "puts every file touched by the guided setup back as it was.\n"
    "READS     home/setup-manifest.json and the backups in home/setup-backups; "
    "the files named in the manifest.\n"
    "WRITES    restores the saved CLAUDE.md, settings.json and settings files, "
    "deletes the ones setup created, removes the backups and the manifest. "
    "A file edited since setup is kept and only the FrugalFlow block and hook "
    "are cut out of it.\n"
    "EXAMPLE   python3 uninstall_cmd.py --home ~/.frugalflow\n"
    "PITFALLS  2026-10-25 restoring a saved CLAUDE.md over one the user had "
    "edited since setup would have lost their lines; such a file is now kept "
    "and cut precisely.\n"
    "          2026-10-25 an uninstall with no record of a setup used to fail; "
    "it now removes the block and the hook only."
)


def _has_editable_target(lines):
    for line in lines:
        if not line.startswith("KEPT "):
            continue
        rest = line[5:]
        path = rest.split(" (changed")[0] if " (changed" in rest else rest
        if path.endswith("CLAUDE.md") or "settings.json" in path:
            return True
    return False


def main(argv):
    if len(argv) == 1 and argv[0] == "--notice":
        print(NOTICE)
        return 0
    if len(argv) == 1 and argv[0] == "--autotest":
        return _autotest()

    home = os.environ.get("FRUGALFLOW_HOME") or ""
    if not home:
        home = os.path.expanduser("~/.frugalflow")
    claude_dir = os.path.expanduser("~/.claude")

    i = 0
    while i < len(argv):
        if argv[i] == "--home":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            home = argv[i + 1]
            i += 2
        elif argv[i] == "--claude-dir":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            claude_dir = argv[i + 1]
            i += 2
        elif argv[i] in ("--notice", "--autotest"):
            print(USAGE)
            return 2
        else:
            print(USAGE)
            return 2

    lines, code = setup_manifest.restore(home)

    if code == 3:
        print("NO SETUP RECORD, removing the FrugalFlow block and hook only")
        return init_cmd.main(
            ["--remove", "--home", home, "--claude-dir", claude_dir]
        )

    for line in lines:
        print(line)

    if _has_editable_target(lines):
        init_cmd.main(
            ["--remove", "--home", home, "--claude-dir", claude_dir]
        )

    print("UNINSTALL DONE")
    return 0


def _make_env(tmp):
    env = dict(os.environ)
    env["HOME"] = tmp
    env["USERPROFILE"] = tmp
    env.pop("FRUGALFLOW_HOME", None)
    for k in list(env):
        if k.startswith("GIT_"):
            del env[k]
    pycache = os.path.join(tmp, "_pyc")
    os.makedirs(pycache, exist_ok=True)
    env["PYTHONPYCACHEPREFIX"] = pycache
    return env


def _autotest():
    import subprocess

    ORIGINAL = "# my notes\n"
    USER_LINE = "my own line\n"
    BEGIN_MARK = "<!-- FRUGALFLOW begin -->"
    DEAD = "http://127.0.0.1:1"

    script = os.path.abspath(__file__)
    folder = os.path.dirname(script)
    results = []
    passes = 0

    # --- Test 1: restore from backup ---
    try:
        tmp = tempfile.mkdtemp()
        ff = os.path.join(tmp, "ff")
        cl = os.path.join(tmp, "cl")
        os.makedirs(ff)
        os.makedirs(cl)
        claude_md = os.path.join(cl, "CLAUDE.md")
        with open(claude_md, "w", encoding="utf-8", newline="") as f:
            f.write(ORIGINAL)
        m = setup_manifest.snapshot(ff, [claude_md])
        env = _make_env(tmp)
        subprocess.run(
            [sys.executable, os.path.join(folder, "init_cmd.py"),
             "--home", ff, "--claude-dir", cl,
             "--ollama-url", DEAD, "--lmstudio-url", DEAD],
            capture_output=True, text=True, env=env, timeout=300
        )
        setup_manifest.finish(ff, m)
        r = subprocess.run(
            [sys.executable, script, "--home", ff, "--claude-dir", cl],
            capture_output=True, text=True, env=env, timeout=300
        )
        content = open(claude_md, encoding="utf-8").read()
        ok = (
            r.returncode == 0
            and "RESTORED " in r.stdout
            and "UNINSTALL DONE" in r.stdout
            and content == ORIGINAL
        )
        if ok:
            results.append(
                "PASS test1: expect code=0 RESTORED DONE content=ORIGINAL, "
                "got code=0 RESTORED DONE content=ORIGINAL"
            )
            passes += 1
        else:
            results.append(
                "FAIL test1: expect code=0 RESTORED DONE content=ORIGINAL, "
                "got code=%d out=%r content=%r"
                % (r.returncode, r.stdout[:120], content[:120])
            )
    except Exception as exc:
        results.append("FAIL test1: expect code=0 RESTORED DONE content=ORIGINAL, got %s" % exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 2: nothing to remove ---
    try:
        tmp = tempfile.mkdtemp()
        ff = os.path.join(tmp, "ff")
        cl = os.path.join(tmp, "cl")
        os.makedirs(ff)
        os.makedirs(cl)
        env = _make_env(tmp)
        r = subprocess.run(
            [sys.executable, script, "--home", ff, "--claude-dir", cl],
            capture_output=True, text=True, env=env, timeout=300
        )
        ok = (
            r.returncode == 0
            and "NO SETUP RECORD" in r.stdout
            and "NOTHING TO REMOVE" in r.stdout
        )
        if ok:
            results.append(
                "PASS test2: expect code=0 NO SETUP RECORD NOTHING TO REMOVE, "
                "got code=0 NO SETUP RECORD NOTHING TO REMOVE"
            )
            passes += 1
        else:
            results.append(
                "FAIL test2: expect code=0 NO SETUP RECORD NOTHING TO REMOVE, "
                "got code=%d out=%r"
                % (r.returncode, r.stdout[:120])
            )
    except Exception as exc:
        results.append("FAIL test2: expect code=0 NO SETUP RECORD NOTHING TO REMOVE, got %s" % exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 3: file edited since setup ---
    try:
        tmp = tempfile.mkdtemp()
        ff = os.path.join(tmp, "ff")
        cl = os.path.join(tmp, "cl")
        os.makedirs(ff)
        os.makedirs(cl)
        claude_md = os.path.join(cl, "CLAUDE.md")
        with open(claude_md, "w", encoding="utf-8", newline="") as f:
            f.write(ORIGINAL)
        m = setup_manifest.snapshot(ff, [claude_md])
        env = _make_env(tmp)
        subprocess.run(
            [sys.executable, os.path.join(folder, "init_cmd.py"),
             "--home", ff, "--claude-dir", cl,
             "--ollama-url", DEAD, "--lmstudio-url", DEAD],
            capture_output=True, text=True, env=env, timeout=300
        )
        setup_manifest.finish(ff, m)
        with open(claude_md, "a", encoding="utf-8") as f:
            f.write(USER_LINE)
        r = subprocess.run(
            [sys.executable, script, "--home", ff, "--claude-dir", cl],
            capture_output=True, text=True, env=env, timeout=300
        )
        content = open(claude_md, encoding="utf-8").read()
        ok = (
            r.returncode == 0
            and "KEPT " in r.stdout
            and "UNINSTALL DONE" in r.stdout
            and USER_LINE in content
            and BEGIN_MARK not in content
        )
        if ok:
            results.append(
                "PASS test3: expect code=0 KEPT DONE USER_LINE no_mark, "
                "got code=0 KEPT DONE USER_LINE no_mark"
            )
            passes += 1
        else:
            results.append(
                "FAIL test3: expect code=0 KEPT DONE USER_LINE no_mark, "
                "got code=%d out=%r content=%r"
                % (r.returncode, r.stdout[:120], content[:120])
            )
    except Exception as exc:
        results.append("FAIL test3: expect code=0 KEPT DONE USER_LINE no_mark, got %s" % exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    # --- Test 4: usage and notice ---
    try:
        tmp = tempfile.mkdtemp()
        env = _make_env(tmp)
        r = subprocess.run(
            [sys.executable, script, "--bogus"],
            capture_output=True, text=True, env=env, timeout=300
        )
        ok_bogus = r.returncode == 2 and "usage: uninstall_cmd.py" in r.stdout
        r2 = subprocess.run(
            [sys.executable, script, "--notice"],
            capture_output=True, text=True, env=env, timeout=300
        )
        ok_notice = r2.returncode == 0 and r2.stdout.startswith("NAME      uninstall_cmd.py")
        ok = ok_bogus and ok_notice
        if ok:
            results.append(
                "PASS test4: expect code2+code0 usage+notice, "
                "got code2+code0 usage+notice"
            )
            passes += 1
        else:
            results.append(
                "FAIL test4: expect code2+code0 usage+notice, "
                "got code%d+code%d bogus_ok=%s notice_ok=%s"
                % (r.returncode, r2.returncode, ok_bogus, ok_notice)
            )
    except Exception as exc:
        results.append("FAIL test4: expect code2+code0 usage+notice, got %s" % exc)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    for line in results:
        print(line)
    print("AUTOTEST %d/4" % passes)
    return 0 if passes == 4 else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
