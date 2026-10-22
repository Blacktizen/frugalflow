#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""page_rules.py - finds a vault's required-reading pages by name anywhere in the vault, and extracts their bearing lines and fingerprint."""

import os
import sys
import re
import hashlib
import subprocess

MARKERS = ["⛔⛔", "⛔", "⭐⭐"]
TAG = "REQUIRED-READING"
DEFAULT_PAGES = ["overview.md", "todo.md"]

_NOTICE = (
    "NAME      page_rules.py - finds a vault's required-reading pages by name anywhere in the vault, and extracts their bearing lines and fingerprint.\n"
    "READS     nothing: pure module; the caller passes the SCHEMA.md text, the vault's relative file list and the page texts.\n"
    "WRITES    nothing: required_pages() returns (paths, errors); a missing or ambiguous page is an error, never a guess.\n"
    "EXAMPLE   python3 page_rules.py --notice\n"
    "PITFALLS  2026-09-22 the old gate joined the vault path and the page name: moving a page into a subfolder bricked it.\n"
    "          Pages are now resolved by name, like a wiki link; two pages with the same name are refused.\n"
    "          2026-10-03 a page under raw/ or a line hidden in a comment, a code block or YAML front matter became required reading; both are now skipped.\n"
)

_USAGE = "usage: page_rules.py --notice | --autotest\n"


def schema_pages(schema_text):
    """Extract required-page names from a schema text block."""
    if not isinstance(schema_text, str):
        return None
    lines = schema_text.split("\n")
    collected = []
    in_block = False
    for line in lines:
        if not in_block:
            if TAG in line:
                in_block = True
        else:
            if "-->" in line:
                break
            stripped = line.strip()
            if stripped:
                collected.append(stripped)
    if in_block and collected:
        return collected
    return None


def is_raw(path):
    """Return True when the first path segment, lowercased, is 'raw'."""
    return path.split("/", 1)[0].lower() == "raw"


def resolve(name, files):
    """Resolve a page name to a unique vault-relative path, never under raw/."""
    n = name.strip()
    if not n:
        return (None, "missing page: " + name)
    if "/" in n:
        if n in files and not is_raw(n):
            return (n, "")
        return (None, "missing page: " + n)
    target = n if n.endswith(".md") else n + ".md"
    matches = sorted(f for f in files if f.split("/")[-1] == target and not is_raw(f))
    if len(matches) == 0:
        return (None, "missing page: " + n)
    if len(matches) == 1:
        return (matches[0], "")
    return (None, "ambiguous page: " + n + " matches " + ", ".join(matches))


def required_pages(schema_text, files):
    """Resolve all required pages; returns (paths, errors)."""
    names = schema_pages(schema_text)
    if names is None:
        names = DEFAULT_PAGES
    paths = []
    errors = []
    for name in names:
        path, err = resolve(name, files)
        if path is not None:
            paths.append(path)
        else:
            errors.append(err)
    return (paths, errors)


def _strip_comments(line, in_html, in_percent):
    """Remove HTML and %% comments from one line, tracking cross-line state."""
    out = []
    i = 0
    n = len(line)
    while i < n:
        if in_html:
            j = line.find("-->", i)
            if j == -1:
                break
            i = j + 3
            in_html = False
        elif in_percent:
            j = line.find("%%", i)
            if j == -1:
                break
            i = j + 2
            in_percent = False
        else:
            h = line.find("<!--", i)
            o = line.find("%%", i)
            starts = [p for p in (h, o) if p != -1]
            if not starts:
                out.append(line[i:])
                i = n
                break
            pos = min(starts)
            out.append(line[i:pos])
            if pos == h:
                in_html = True
                i = pos + 4
            else:
                in_percent = True
                i = pos + 2
    return ("".join(out), in_html, in_percent)


def visible_text(text):
    """Return text with YAML front matter, code fences and comments blanked, keeping the same number of lines."""
    lines = text.split("\n")
    out = []
    in_yaml = lines[0] == "---"
    in_code = False
    fence_char = ""
    fence_count = 0
    in_html = False
    in_percent = False

    for i, line in enumerate(lines):
        if in_yaml:
            out.append("")
            if i > 0 and line in ("---", "..."):
                in_yaml = False
            continue

        stripped = line.lstrip()
        if in_code:
            out.append("")
            if fence_char and stripped.startswith(fence_char * fence_count):
                in_code = False
            continue

        visible, in_html, in_percent = _strip_comments(line, in_html, in_percent)
        vstripped = visible.lstrip()
        if vstripped.startswith("```") or vstripped.startswith("~~~"):
            fence_char = vstripped[0]
            fence_count = 1
            while fence_count < len(vstripped) and vstripped[fence_count] == fence_char:
                fence_count += 1
            in_code = True
            out.append("")
            continue

        out.append(visible)

    return "\n".join(out)


def bearing_lines(text):
    """Return normalized lines that carry at least one marker."""
    result = []
    for line in visible_text(text).split("\n"):
        if any(m in line for m in MARKERS):
            normalized = re.sub(r"[ \t]+", " ", line.strip())
            result.append(normalized)
    return result


def fingerprint(pages):
    """Compute a SHA-256 fingerprint from base names and bearing lines."""
    segments = []
    for path, text in pages:
        base = path.split("/")[-1]
        segment = "\x00".join([base] + bearing_lines(text))
        segments.append(segment)
    return hashlib.sha256("\x00".join(segments).encode("utf-8")).hexdigest()


# --- fixtures ---
SCHEMA = "# Schema\n<!-- REQUIRED-READING\noverview.md\n\ntodo\nbible.md\n-->\nrest\n"
SCHEMA_EMPTY = "# Schema\n<!-- REQUIRED-READING\n-->\n"
FILES = ["overview.md", "todo.md", "02-models/bible.md", "raw/a.txt"]
FILES_DUP = ["overview.md", "todo.md", "bible.md", "02-models/bible.md"]
PAGE = "# Title\n⛔⛔  never   this\nplain line\n\t⭐⭐ keep\tthis \n⛔ and ⭐⭐ both\n"


def _autotest():
    results = []

    # Test 1: schema_pages
    r1 = (
        schema_pages(SCHEMA) == ["overview.md", "todo", "bible.md"]
        and schema_pages(SCHEMA_EMPTY) is None
        and schema_pages("no block") is None
        and schema_pages(None) is None
    )
    results.append(("schema_pages", "all four sub-assertions", r1))

    # Test 2: resolve
    r2 = (
        resolve("bible.md", FILES) == ("02-models/bible.md", "")
        and resolve("todo", FILES) == ("todo.md", "")
        and resolve("02-models/bible.md", FILES) == ("02-models/bible.md", "")
        and resolve("gone.md", FILES) == (None, "missing page: gone.md")
        and resolve("bible.md", FILES_DUP) == (None, "ambiguous page: bible.md matches 02-models/bible.md, bible.md")
    )
    results.append(("resolve", "five sub-assertions", r2))

    # Test 3: required_pages
    r3 = (
        required_pages(SCHEMA, FILES) == (["overview.md", "todo.md", "02-models/bible.md"], [])
        and required_pages(None, FILES) == (["overview.md", "todo.md"], [])
        and required_pages(SCHEMA, ["overview.md"]) == (["overview.md"], ["missing page: todo", "missing page: bible.md"])
    )
    results.append(("required_pages", "three sub-assertions", r3))

    # Test 4: bearing_lines
    r4 = (
        bearing_lines(PAGE) == ["⛔⛔ never this", "⭐⭐ keep this", "⛔ and ⭐⭐ both"]
        and bearing_lines("") == []
    )
    results.append(("bearing_lines", "two sub-assertions", r4))

    # Test 5: fingerprint + subprocess
    fp1 = fingerprint([("overview.md", PAGE)])
    fp2 = fingerprint([("01-context/overview.md", PAGE)])
    fp3 = fingerprint([("overview.md", PAGE + "⛔ new\n")])
    fp_empty = fingerprint([])
    r5_sub = (fp1 == fp2) and (fp1 != fp3) and (len(fp_empty) == 64)

    script = os.path.abspath(__file__)
    proc_notice = subprocess.run(
        [sys.executable, script, "--notice"],
        capture_output=True, text=True
    )
    r5_notice = (
        proc_notice.returncode == 0
        and proc_notice.stdout.startswith("NAME      page_rules.py")
    )

    proc_usage = subprocess.run(
        [sys.executable, script],
        capture_output=True, text=True
    )
    r5_usage = (
        proc_usage.returncode == 2
        and proc_usage.stdout == "usage: page_rules.py --notice | --autotest\n"
    )

    r5 = r5_sub and r5_notice and r5_usage
    results.append(("fingerprint+subprocess", "fingerprint invariants and CLI codes", r5))

    # Test 6: is_raw, raw pages are skipped, and hidden lines carry no markers
    RAW_TEXT = (
        "---\n"
        "title: ⛔⛔ hidden in YAML\n"
        "---\n"
        "```\n"
        "⛔ hidden in code\n"
        "```\n"
        "start <!-- ⭐⭐ hidden\n"
        "still hidden\n"
        "end --> visible\n"
        "%% ⛔ hidden %%\n"
    )
    r6 = (
        is_raw("raw/a.md")
        and is_raw("Raw/a.md")
        and is_raw("raw/web/a.md")
        and not is_raw("notes/raw/a.md")
        and not is_raw("rawdata/a.md")
        and resolve("todo.md", ["raw/todo.md"]) == (None, "missing page: todo.md")
        and resolve("raw/todo.md", ["raw/todo.md"]) == (None, "missing page: raw/todo.md")
        and bearing_lines(RAW_TEXT) == []
    )
    results.append(("is_raw+visible_text", "raw path cases and hidden markers", r6))

    all_pass = True
    for i, (name, desc, passed) in enumerate(results, 1):
        if passed:
            print("PASS test{} {} expected=True obtained=True".format(i, name))
        else:
            print("FAIL test{} {} expected=True obtained=False".format(i, name))
            all_pass = False
    return 0 if all_pass else 1


def _main():
    args = sys.argv[1:]
    if args == ["--notice"]:
        sys.stdout.write(_NOTICE)
        sys.exit(0)
    elif args == ["--autotest"]:
        sys.exit(_autotest())
    else:
        sys.stdout.write(_USAGE)
        sys.exit(2)


def _cli():
        _main()


if __name__ == "__main__":
    import exit_log
    exit_log.run(_cli, "page_rules", sys.argv[1:])
