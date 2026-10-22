#!/usr/bin/env python3
"""Hard closing pass for a memory vault: verifies that what is written is true."""

import os
import sys
import tempfile
import shutil
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import page_rules
import chain_rules
import commit_claims

USAGE = "usage: vault_check.py --vault DIR [--repo DIR ...] [--declared ID ...] | --notice | --autotest"

NOTICE = (
    "NAME      vault_check.py - the vault's hard closing pass: checks that what is written is true.\n"
    "READS     --vault; --repo (read only, several allowed); --declared (hex ids that are not commits, several allowed).\n"
    "WRITES    nothing: one PASS, FAIL or SKIP line per check (PAGES, LOG, INDEX, SOURCES, COMMITS), then VAULT OK or VAULT FAILED <n> checks. Exit 0 ok, 2 usage, 6 failed.\n"
    "EXAMPLE   python3 vault_check.py --vault ~/projects/demo/vault --repo ~/projects/demo\n"
    "PITFALLS  2026-09-22 a gist revision cited as proof was checked as a local commit: commit_claims.py now sets it apart, and the count is printed.\n"
    "          2026-09-22 a page moved into a subfolder was reported missing: every page is found by name.\n"
)


def vault_files(vault):
    """Return sorted relative file paths under vault, skipping hidden directories."""
    result = []
    for dirpath, dirnames, filenames in os.walk(vault):
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for filename in filenames:
            full_path = os.path.join(dirpath, filename)
            rel_path = os.path.relpath(full_path, vault).replace(os.sep, "/")
            result.append(rel_path)
    return sorted(result)


def read(vault, rel):
    """Read a file from vault and return its content as a utf-8 string."""
    with open(os.path.join(vault, rel), "r", encoding="utf-8", errors="replace") as handle:
        return handle.read()


def check_pages(vault, files):
    """Verify all required pages are present."""
    schema_text = read(vault, "SCHEMA.md") if "SCHEMA.md" in files else None
    paths, errors = page_rules.required_pages(schema_text, files)
    if errors:
        return (False, "FAIL PAGES " + "; ".join(errors))
    return (True, "PASS PAGES " + str(len(paths)) + " required pages found")


def check_log(vault, files):
    """Verify the sealed journal chain is intact."""
    log_path, log_err = page_rules.resolve("log.md", files)
    if log_path is None:
        return (False, "FAIL LOG " + log_err)
    ok, count, bad, reason = chain_rules.verify(read(vault, log_path))
    if not ok:
        return (False, "FAIL LOG " + reason)
    return (True, "PASS LOG " + str(count) + " entries chained")


def live_pages(files):
    """Return .md files that are live pages (not under raw/, not hidden)."""
    return [
        f for f in files
        if f.endswith(".md")
        and not f.startswith("raw/")
        and not os.path.basename(f).startswith(".")
    ]


def check_index(vault, files):
    """Verify every live page is listed in index.md."""
    index_path, index_err = page_rules.resolve("index.md", files)
    if index_path is None:
        return (False, "FAIL INDEX " + index_err)
    text = read(vault, index_path)
    not_listed = []
    pages_checked = 0
    for page in live_pages(files):
        if page == index_path:
            continue
        pages_checked += 1
        stem = os.path.basename(page)[:-3]
        if not ("[[" + stem + "]]" in text or "[[" + stem + "|" in text):
            not_listed.append(page)
    if not_listed:
        return (False, "FAIL INDEX not listed: " + ", ".join(not_listed))
    return (True, "PASS INDEX " + str(pages_checked) + " pages listed")


def check_sources(vault, files):
    """Verify every raw file is cited in sources.md."""
    raws = [
        f for f in files
        if f.startswith("raw/")
        and not os.path.basename(f).startswith(".")
    ]
    sources_path, sources_err = page_rules.resolve("sources.md", files)
    if sources_path is None:
        return (False, "FAIL SOURCES " + sources_err)
    text = read(vault, sources_path)
    not_cited = [f for f in raws if os.path.basename(f) not in text]
    if not_cited:
        return (False, "FAIL SOURCES not cited: " + ", ".join(not_cited))
    return (True, "PASS SOURCES " + str(len(raws)) + " raw files cited")


def commit_exists(repo, sha):
    """Check whether a commit exists in the given git repository."""
    return subprocess.run(
        ["git", "-C", repo, "cat-file", "-e", sha + "^{commit}"],
        capture_output=True
    ).returncode == 0


def check_commits(vault, files, repos, declared):
    """Verify every cited commit exists in at least one repository."""
    pairs = []
    excluded_count = 0
    for page in live_pages(files):
        result = commit_claims.claims(read(vault, page), declared=declared)
        for sha in result["commits"]:
            pairs.append((sha, page))
        excluded_count += len(result["excluded"])
    total_claims = len(pairs)
    if not repos:
        return (True, "SKIP COMMITS no repository given, " + str(total_claims) + " claims not checked, " + str(excluded_count) + " set apart")
    unknown = []
    for sha, page in pairs:
        found = any(commit_exists(repo, sha) for repo in repos)
        if not found:
            unknown.append((sha, page))
    if unknown:
        return (False, "FAIL COMMITS unknown: " + ", ".join(sha + " (" + page + ")" for sha, page in unknown) + "; " + str(excluded_count) + " set apart")
    return (True, "PASS COMMITS " + str(total_claims) + " claims found, " + str(excluded_count) + " set apart")


def run_checks(vault, repos, declared):
    """Run all five checks and return a list of (ok, message) tuples."""
    files = vault_files(vault)
    return [
        check_pages(vault, files),
        check_log(vault, files),
        check_index(vault, files),
        check_sources(vault, files),
        check_commits(vault, files, repos, declared),
    ]


# --- Autotest fixtures ---

LOG = "# Log\n\n" + chain_rules.render(chain_rules.GENESIS, "2026-09-26 00:00", "setup", [("Decision", "created")])
BASE = {
    "SCHEMA.md": "# S\n<!-- REQUIRED-READING\noverview.md\ntodo.md\n-->\n",
    "overview.md": "# O\n",
    "todo.md": "# T\n",
    "log.md": LOG,
    "index.md": "# I\n[[SCHEMA]] [[overview]] [[todo]] [[log]] [[sources]] [[decision-a|A]]\n",
    "sources.md": "# Sources\nnotes.txt\n",
    "raw/notes.txt": "raw\n",
    "02-decisions/decision-a.md": "# A\n",
}


def make(vault_dir, files):
    """Write fixture files into a vault directory."""
    for rel_path, text in files.items():
        full_path = os.path.join(vault_dir, rel_path)
        os.makedirs(os.path.dirname(full_path), exist_ok=True)
        with open(full_path, "w", encoding="utf-8") as handle:
            handle.write(text)


def run(*args):
    """Run vault_check.py as a subprocess and return (exit_code, stdout)."""
    result = subprocess.run(
        [sys.executable, os.path.abspath(__file__)] + list(args),
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout


def git_repo(directory):
    """Create a minimal git repository and return the HEAD sha."""
    subprocess.run(["git", "init", "-q", directory], check=True)
    subprocess.run(
        ["git", "-C", directory, "-c", "user.name=t", "-c", "user.email=t@t",
         "commit", "-q", "--allow-empty", "-m", "x"],
        check=True
    )
    return subprocess.run(
        ["git", "-C", directory, "rev-parse", "HEAD"],
        capture_output=True, text=True
    ).stdout.strip()


def run_autotest():
    """Execute all five proofs and print one line per proof."""
    all_passed = True
    temp_dirs = []

    # Proof 1: full pass on a clean vault
    vault_dir_one = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_one)
    make(vault_dir_one, BASE)
    exit_code_one, output_one = run("--vault", vault_dir_one)
    passed_one = (
        exit_code_one == 0
        and "PASS PAGES 2 required pages found" in output_one
        and "PASS LOG 1 entries chained" in output_one
        and "PASS INDEX 6 pages listed" in output_one
        and "PASS SOURCES 1 raw files cited" in output_one
        and "SKIP COMMITS no repository given, 0 claims not checked, 0 set apart" in output_one
        and output_one.endswith("VAULT OK\n")
    )
    all_passed = all_passed and passed_one
    print(("PASS" if passed_one else "FAIL") + " proof 1: expected exit 0 with all PASS lines, got exit " + str(exit_code_one))

    # Proof 2: moved page passes; missing index entry and uncited raw fail
    vault_dir_two_a = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_two_a)
    make(vault_dir_two_a, BASE)
    os.makedirs(os.path.join(vault_dir_two_a, "01-context"))
    os.rename(
        os.path.join(vault_dir_two_a, "overview.md"),
        os.path.join(vault_dir_two_a, "01-context", "overview.md")
    )
    exit_code_two_a, output_two_a = run("--vault", vault_dir_two_a)

    vault_dir_two_b = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_two_b)
    make(vault_dir_two_b, dict(BASE, **{"05-reference/lost.md": "# L\n", "raw/extra.pdf": "x"}))
    exit_code_two_b, output_two_b = run("--vault", vault_dir_two_b)

    passed_two = (
        exit_code_two_a == 0
        and exit_code_two_b == 6
        and "FAIL INDEX not listed: 05-reference/lost.md" in output_two_b
        and "FAIL SOURCES not cited: raw/extra.pdf" in output_two_b
        and "VAULT FAILED 2 checks" in output_two_b
    )
    all_passed = all_passed and passed_two
    print(("PASS" if passed_two else "FAIL") + " proof 2: expected exits 0 and 6, got " + str(exit_code_two_a) + " and " + str(exit_code_two_b))

    # Proof 3: rewritten log entry fails; missing required page fails
    vault_dir_three_a = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_three_a)
    make(vault_dir_three_a, dict(BASE, **{"log.md": LOG.replace("created", "CREATED")}))
    exit_code_three_a, output_three_a = run("--vault", vault_dir_three_a)

    vault_dir_three_b = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_three_b)
    make(vault_dir_three_b, BASE)
    os.remove(os.path.join(vault_dir_three_b, "todo.md"))
    exit_code_three_b, output_three_b = run("--vault", vault_dir_three_b)

    passed_three = (
        exit_code_three_a == 6
        and "FAIL LOG entry 0 was rewritten" in output_three_a
        and "FAIL PAGES missing page: todo.md" in output_three_b
    )
    all_passed = all_passed and passed_three
    print(("PASS" if passed_three else "FAIL") + " proof 3: expected exit 6 with FAIL LOG and FAIL PAGES, got exit " + str(exit_code_three_a))

    # Proof 4: commit verification with real repo, unknown sha, and declared id
    repo_directory = tempfile.mkdtemp()
    temp_dirs.append(repo_directory)
    commit_sha = git_repo(repo_directory)

    vault_dir_four_a = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_four_a)
    make(vault_dir_four_a, dict(BASE, **{"overview.md": "# O\nDone in `" + commit_sha + "`.\nKarpathy gist `a1b2c3d4e5f6a7b8c9d0`.\n"}))
    exit_code_four_a, output_four_a = run("--vault", vault_dir_four_a, "--repo", repo_directory)

    vault_dir_four_b = tempfile.mkdtemp()
    temp_dirs.append(vault_dir_four_b)
    make(vault_dir_four_b, dict(BASE, **{"todo.md": "# T\nsee `abc1234`\n"}))
    exit_code_four_b, output_four_b = run("--vault", vault_dir_four_b, "--repo", repo_directory)

    exit_code_four_c, output_four_c = run("--vault", vault_dir_four_b, "--repo", repo_directory, "--declared", "abc1234")

    passed_four = (
        exit_code_four_a == 0
        and "PASS COMMITS 1 claims found, 1 set apart" in output_four_a
        and exit_code_four_b == 6
        and "FAIL COMMITS unknown: abc1234 (todo.md); 0 set apart" in output_four_b
        and exit_code_four_c == 0
        and "PASS COMMITS 0 claims found, 1 set apart" in output_four_c
    )
    all_passed = all_passed and passed_four
    print(("PASS" if passed_four else "FAIL") + " proof 4: expected exits 0, 6, 0, got " + str(exit_code_four_a) + ", " + str(exit_code_four_b) + ", " + str(exit_code_four_c))

    # Proof 5: notice, no arguments, bad vault path, option without value
    exit_code_five_a, output_five_a = run("--notice")
    exit_code_five_b, output_five_b = run()
    missing_dir_code, missing_dir_out = run("--vault", "/nonexistent-dir-xyz")
    no_value_code, no_value_out = run("--vault", vault_dir_one, "--repo")

    passed_five = (
        exit_code_five_a == 0
        and output_five_a.startswith("NAME      vault_check.py")
        and exit_code_five_b == 2
        and output_five_b == USAGE + "\n"
        and missing_dir_code == 2
        and no_value_code == 2
    )
    all_passed = all_passed and passed_five
    print(("PASS" if passed_five else "FAIL") + " proof 5: expected exits 0, 2, 2, 2, got " + str(exit_code_five_a) + ", " + str(exit_code_five_b) + ", " + str(missing_dir_code) + ", " + str(no_value_code))

    # Cleanup
    for directory in temp_dirs:
        shutil.rmtree(directory, ignore_errors=True)

    if not all_passed:
        sys.exit(1)


def main():
    """Parse arguments, dispatch, and exit with the correct code."""
    argv = sys.argv[1:]
    vault = None
    repos = []
    declared = []
    notice = False
    autotest = False

    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--vault":
            if index + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            vault = argv[index + 1]
            index += 2
        elif arg == "--repo":
            if index + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            repos.append(argv[index + 1])
            index += 2
        elif arg == "--declared":
            if index + 1 >= len(argv):
                print(USAGE)
                sys.exit(2)
            declared.append(argv[index + 1])
            index += 2
        elif arg == "--notice":
            notice = True
            index += 1
        elif arg == "--autotest":
            autotest = True
            index += 1
        else:
            print(USAGE)
            sys.exit(2)

    if notice:
        sys.stdout.write(NOTICE)
        sys.exit(0)

    if autotest:
        run_autotest()
        sys.exit(0)

    if not vault:
        print(USAGE)
        sys.exit(2)

    if not os.path.isdir(vault):
        print(USAGE)
        sys.exit(2)

    results = run_checks(vault, repos, declared)
    for ok, message in results:
        print(message)
    fail_count = sum(1 for ok, _ in results if not ok)
    if fail_count == 0:
        print("VAULT OK")
        sys.exit(0)
    else:
        print("VAULT FAILED " + str(fail_count) + " checks")
        sys.exit(6)


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "vault_check", sys.argv[1:])
