import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile

MANIFEST_NAME = "setup-manifest.json"
BACKUP_DIR = "setup-backups"

NOTICE = (
    "NAME      setup_manifest.py - remembers what setup touched so that uninstall "
    "can put every file back.\n"
    "READS     the files to be touched (to copy them), home/setup-manifest.json "
    "when it exists.\n"
    "WRITES    copies in home/setup-backups, then home/setup-manifest.json; "
    "restore removes them again and restores or deletes the touched files.\n"
    "EXAMPLE   python3 setup_manifest.py --autotest\n"
    "PITFALLS  2026-10-25 a second setup would have saved the already configured "
    "file over the original; the first backup of each file now wins.\n"
    "          2026-10-25 a file edited by the user after setup is never "
    "overwritten by a restore; it is reported as KEPT."
)


def sha256_file(path):
    if not os.path.isfile(path):
        return None
    h = hashlib.sha256()
    with open(path, "rb") as f:
        h.update(f.read())
    return h.hexdigest()


def snapshot(home, paths):
    manifest_path = os.path.join(home, MANIFEST_NAME)
    if os.path.isfile(manifest_path):
        with open(manifest_path, "r", encoding="utf-8") as f:
            base = json.load(f)
    else:
        base = {"version": 1, "entries": []}

    entries = list(base["entries"])
    existing_paths = set(e["path"] for e in entries)

    for p in paths:
        if p in existing_paths:
            continue
        entry = {"path": p, "existed": False, "backup": None, "after_sha": None}
        if os.path.isfile(p):
            entry["existed"] = True
            backup_dir = os.path.join(home, BACKUP_DIR)
            os.makedirs(backup_dir, exist_ok=True)
            n = len(entries) + 1
            fname = os.path.basename(p)
            backup_name = str(n) + "-" + fname
            shutil.copyfile(p, os.path.join(backup_dir, backup_name))
            entry["backup"] = backup_name
        entries.append(entry)
        existing_paths.add(p)

    return {"version": 1, "entries": entries}


def finish(home, manifest):
    os.makedirs(home, exist_ok=True)
    for entry in manifest["entries"]:
        entry["after_sha"] = sha256_file(entry["path"])
    manifest_path = os.path.join(home, MANIFEST_NAME)
    fd, tmp_path = tempfile.mkstemp(dir=home)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=2)
        os.replace(tmp_path, manifest_path)
    except BaseException:
        if os.path.exists(tmp_path):
            os.unlink(tmp_path)
        raise
    return manifest_path


def restore(home):
    manifest_path = os.path.join(home, MANIFEST_NAME)
    if not os.path.isfile(manifest_path):
        return (["NO MANIFEST " + manifest_path], 3)

    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    lines = []
    kept_count = 0

    for entry in manifest["entries"]:
        path = entry["path"]
        cur = sha256_file(path)
        existed = entry["existed"]
        after_sha = entry["after_sha"]

        if cur is None and not existed:
            lines.append("GONE " + path)
        elif cur is not None and cur != after_sha:
            lines.append("KEPT " + path + " (changed since setup)")
            kept_count += 1
        else:
            if existed:
                backup_full = os.path.join(
                    home, BACKUP_DIR, entry["backup"]
                )
                shutil.copyfile(backup_full, path)
                lines.append("RESTORED " + path)
            else:
                os.remove(path)
                lines.append("REMOVED " + path)

    if kept_count == 0:
        backup_dir = os.path.join(home, BACKUP_DIR)
        if os.path.isdir(backup_dir):
            for fname in os.listdir(backup_dir):
                os.remove(os.path.join(backup_dir, fname))
            os.rmdir(backup_dir)
        os.remove(manifest_path)
        try:
            os.rmdir(home)
        except OSError:
            pass
    else:
        lines.append(
            "KEPT " + str(kept_count) + " file(s): edit them by hand "
            "or run the surgical removal"
        )

    return (lines, 0)


ORIGINAL = b"original notes\n"
CHANGED = b"changed by setup\n"
EDITED = b"edited later by the user\n"


def _autotest():
    results = []

    # Test 1: restore
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        os.makedirs(home)
        os.makedirs(work)
        a = os.path.join(work, "a.txt")
        with open(a, "wb") as f:
            f.write(ORIGINAL)
        m = snapshot(home, [a])
        with open(a, "wb") as f:
            f.write(CHANGED)
        finish(home, m)
        lines, code = restore(home)
        content = open(a, "rb").read() if os.path.isfile(a) else None
        manifest_exists = os.path.isfile(os.path.join(home, MANIFEST_NAME))
        backup_exists = os.path.isdir(os.path.join(home, BACKUP_DIR))
        ok = (
            code == 0
            and lines == ["RESTORED " + a]
            and content == ORIGINAL
            and not manifest_exists
            and not backup_exists
        )
        results.append(
            ("1", ok, "code=0 RESTORED+content=ORIGINAL no-manifest no-backup",
             "code=" + str(code) + " lines=" + str(lines) + " content=" + str(content)
             + " manifest=" + str(manifest_exists) + " backup=" + str(backup_exists))
        )

    # Test 2: file created by setup removed
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        os.makedirs(home)
        os.makedirs(work)
        b = os.path.join(work, "b.txt")
        m = snapshot(home, [b])
        with open(b, "wb") as f:
            f.write(CHANGED)
        finish(home, m)
        lines, code = restore(home)
        exists_after = os.path.isfile(b)
        ok = (
            code == 0
            and lines == ["REMOVED " + b]
            and not exists_after
        )
        results.append(
            ("2", ok, "code=0 REMOVED+gone",
             "code=" + str(code) + " lines=" + str(lines) + " exists=" + str(exists_after))
        )

    # Test 3: file edited by user after setup -> KEPT
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        os.makedirs(home)
        os.makedirs(work)
        a = os.path.join(work, "a.txt")
        with open(a, "wb") as f:
            f.write(ORIGINAL)
        m = snapshot(home, [a])
        with open(a, "wb") as f:
            f.write(CHANGED)
        finish(home, m)
        with open(a, "wb") as f:
            f.write(EDITED)
        lines, code = restore(home)
        content = open(a, "rb").read()
        manifest_exists = os.path.isfile(os.path.join(home, MANIFEST_NAME))
        expected_lines = [
            "KEPT " + a + " (changed since setup)",
            "KEPT 1 file(s): edit them by hand or run the surgical removal",
        ]
        ok = (
            code == 0
            and set(lines) == set(expected_lines)
            and content == EDITED
            and manifest_exists
        )
        results.append(
            ("3", ok, "code=0 KEPT+summary content=EDITED manifest-exists",
             "code=" + str(code) + " lines=" + str(lines) + " content=" + str(content)
             + " manifest=" + str(manifest_exists))
        )

    # Test 4: second install keeps original backup
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        work = os.path.join(tmp, "work")
        os.makedirs(home)
        os.makedirs(work)
        a = os.path.join(work, "a.txt")
        with open(a, "wb") as f:
            f.write(ORIGINAL)
        m1 = snapshot(home, [a])
        with open(a, "wb") as f:
            f.write(CHANGED)
        finish(home, m1)
        m2 = snapshot(home, [a])
        with open(a, "wb") as f:
            f.write(EDITED)
        finish(home, m2)
        lines, code = restore(home)
        content = open(a, "rb").read() if os.path.isfile(a) else None
        ok = code == 0 and content == ORIGINAL
        results.append(
            ("4", ok, "code=0 content=ORIGINAL",
             "code=" + str(code) + " content=" + str(content))
        )

    # Test 5: no manifest + subprocess usage
    with tempfile.TemporaryDirectory() as tmp:
        home = os.path.join(tmp, "home")
        os.makedirs(home)
        lines, code = restore(home)
        expected_manifest = os.path.join(home, MANIFEST_NAME)
        ok5a = (
            code == 3
            and lines == ["NO MANIFEST " + expected_manifest]
        )

        pycache_dir = tempfile.mkdtemp()
        env = os.environ.copy()
        env["PYTHONPYCACHEPREFIX"] = pycache_dir
        script_path = os.path.abspath(__file__)
        proc = subprocess.run(
            [sys.executable, script_path],
            capture_output=True,
            text=True,
            env=env,
        )
        ok5b = (
            proc.returncode == 2
            and proc.stdout.strip() == "usage: setup_manifest.py --notice | --autotest"
        )
        shutil.rmtree(pycache_dir, ignore_errors=True)

        ok = ok5a and ok5b
        results.append(
            ("5", ok, "code=3 NO-MANIFEST-line + subprocess exit-2 usage",
             "code=" + str(code) + " lines=" + str(lines)
             + " subprocess=" + str(proc.returncode) + ":" + proc.stdout.strip())
        )

    pass_count = 0
    for (num, ok, expected, got) in results:
        if ok:
            pass_count += 1
            print("PASS " + num + " expected=" + expected + " got=" + got)
        else:
            print("FAIL " + num + " expected=" + expected + " got=" + got)

    print("AUTOTEST " + str(pass_count) + "/5")
    return 0 if pass_count == 5 else 1


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    elif len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    else:
        print("usage: setup_manifest.py --notice | --autotest")
        sys.exit(2)


if __name__ == "__main__":
    main()
