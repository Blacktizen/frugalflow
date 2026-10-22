import sys, os, subprocess, tempfile, time, shutil

NOTICE = (
    "NAME      install_hooks.py - installs the repository pre-commit hook from its template, or checks that it is in place.\n"
    "READS     public/hooks/pre-commit in --repo (default: the repository holding this file), and .git/hooks/pre-commit.\n"
    "WRITES    .git/hooks/pre-commit, executable; a differing hook is first copied to pre-commit.before-<timestamp>. --check writes nothing.\n"
    "EXAMPLE   python3 install_hooks.py --check\n"
    "PITFALLS  2026-09-22 the hook lived only in .git/hooks, outside git: a fresh clone had no gate at all.\n"
)

USAGE = "usage: install_hooks.py [--repo DIR] [--check] | --notice | --autotest"


def main(argv):
    repo = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    check = False
    i = 0
    while i < len(argv):
        if argv[i] == "--repo":
            if i + 1 >= len(argv):
                print(USAGE)
                return 2
            repo = argv[i + 1]
            i += 2
        elif argv[i] == "--check":
            check = True
            i += 1
        elif argv[i] == "--notice":
            sys.stdout.write(NOTICE)
            return 0
        elif argv[i] == "--autotest":
            return autotest()
        else:
            print(USAGE)
            return 2

    template = os.path.join(repo, "public", "hooks", "pre-commit")
    hooks_dir = os.path.join(repo, ".git", "hooks")
    hook = os.path.join(hooks_dir, "pre-commit")

    if not os.path.isfile(template):
        print("missing file: " + template)
        return 2
    if not os.path.isdir(hooks_dir):
        print("missing file: " + hooks_dir)
        return 2

    with open(template, "rb") as f:
        model = f.read()

    if check:
        if not os.path.isfile(hook):
            print("HOOK MISSING: " + hook)
            return 11
        with open(hook, "rb") as f:
            content = f.read()
        if content != model:
            print("HOOK DIFFERS: " + hook + " is not the template")
            return 11
        if not os.access(hook, os.X_OK):
            print("HOOK NOT EXECUTABLE: " + hook)
            return 11
        print("HOOK OK")
        return 0

    if os.path.isfile(hook):
        with open(hook, "rb") as f:
            existing = f.read()
        if existing == model and os.access(hook, os.X_OK):
            print("HOOK OK")
            return 0
        if existing != model:
            ts = time.strftime("%Y%m%d-%H%M%S")
            backup_path = hook + ".before-" + ts
            shutil.copy2(hook, backup_path)
            print("BACKUP: " + backup_path)

    with open(hook, "wb") as f:
        f.write(model)
    os.chmod(hook, 0o755)
    print("HOOK INSTALLED: " + hook)
    return 0


def autotest():
    R = tempfile.mkdtemp()
    os.makedirs(os.path.join(R, ".git", "hooks"))
    os.makedirs(os.path.join(R, "public", "hooks"))
    with open(os.path.join(R, "public", "hooks", "pre-commit"), "wb") as f:
        f.write(b"#!/bin/sh\nexit 0\n")

    self = os.path.abspath(__file__)
    hook_path = os.path.join(R, ".git", "hooks", "pre-commit")
    results = []

    # Test 1
    r = subprocess.run([sys.executable, self, "--repo", R, "--check"], capture_output=True, text=True)
    lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
    ok = r.returncode == 11 and any(l.startswith("HOOK MISSING: ") for l in lines)
    results.append(("1 --repo R --check: rc=11, HOOK MISSING", ok,
                    "rc=%d stdout=%r" % (r.returncode, r.stdout)))

    # Test 2
    r = subprocess.run([sys.executable, self, "--repo", R], capture_output=True, text=True)
    lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
    with open(hook_path, "rb") as f:
        hc = f.read()
    he = os.access(hook_path, os.X_OK)
    ok1 = (r.returncode == 0 and any(l.startswith("HOOK INSTALLED: ") for l in lines)
           and hc == b"#!/bin/sh\nexit 0\n" and he)
    r2 = subprocess.run([sys.executable, self, "--repo", R, "--check"], capture_output=True, text=True)
    lines2 = r2.stdout.rstrip("\n").split("\n") if r2.stdout else []
    ok2 = r2.returncode == 0 and "HOOK OK" in lines2
    ok = ok1 and ok2
    results.append(("2 --repo R: rc=0 HOOK INSTALLED; then --check rc=0 HOOK OK", ok,
                    "rc=%d rc2=%d out=%r out2=%r" % (r.returncode, r2.returncode, r.stdout, r2.stdout)))

    # Test 3
    with open(hook_path, "wb") as f:
        f.write(b"old\n")
    r = subprocess.run([sys.executable, self, "--repo", R], capture_output=True, text=True)
    lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
    backup_lines = [l for l in lines if l.startswith("BACKUP: ")]
    backup_path = backup_lines[0][len("BACKUP: "):] if backup_lines else ""
    backup_ok = os.path.isfile(backup_path)
    backup_content = b""
    if backup_ok:
        with open(backup_path, "rb") as f:
            backup_content = f.read()
    with open(hook_path, "rb") as f:
        hc = f.read()
    backup_files = [fn for fn in os.listdir(os.path.join(R, ".git", "hooks"))
                    if fn.startswith("pre-commit.before-")]
    ok = (r.returncode == 0 and len(backup_lines) == 1 and len(backup_files) == 1
          and backup_content == b"old\n" and hc == b"#!/bin/sh\nexit 0\n")
    results.append(("3 write old, --repo R: rc=0 BACKUP, 1 backup file, hook=template", ok,
                    "rc=%d out=%r backups=%d bcontent=%r hook=%r" % (r.returncode, r.stdout, len(backup_files), backup_content, hc)))

    # Test 4
    with open(hook_path, "wb") as f:
        f.write(b"#!/bin/sh\nexit 1\n")
    r = subprocess.run([sys.executable, self, "--repo", R, "--check"], capture_output=True, text=True)
    lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
    ok = r.returncode == 11 and any(l.startswith("HOOK DIFFERS: ") for l in lines)
    results.append(("4 write exit 1, --repo R --check: rc=11 HOOK DIFFERS", ok,
                    "rc=%d stdout=%r" % (r.returncode, r.stdout)))

    # Test 5
    r = subprocess.run([sys.executable, self, "--repo", os.path.join(R, "absent"), "--check"],
                       capture_output=True, text=True)
    lines = r.stdout.rstrip("\n").split("\n") if r.stdout else []
    ok1 = r.returncode == 2 and any(l.startswith("missing file: ") for l in lines)
    r2 = subprocess.run([sys.executable, self, "--notice"], capture_output=True, text=True)
    ok2 = r2.returncode == 0 and r2.stdout.startswith("NAME      install_hooks.py")
    ok = ok1 and ok2
    results.append(("5 --repo absent --check: rc=2 missing file; --notice: rc=0 NAME", ok,
                    "rc=%d rc2=%d out=%r out2=%r" % (r.returncode, r2.returncode, r.stdout, r2.stdout)))

    all_pass = True
    for desc, passed, detail in results:
        if passed:
            print("PASS " + desc)
        else:
            print("FAIL " + desc + " | " + detail)
            all_pass = False
    return 0 if all_pass else 1


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "install_hooks", sys.argv[1:])
