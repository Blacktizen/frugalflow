import os
import subprocess
import sys
import tempfile


def main():
    anon_path = os.path.join(
        os.path.dirname(os.path.abspath(__file__)),
        "..",
        "bin",
        "anon_check.py",
    )

    rules_content = '{"anonymizable": [], "irreducible": []}'

    doc_lines = [
        "mail " + "support" + "@example" + ".com",
        "address " + "192.0" + ".2.10",
        "key " + "AKIAIOSFODNN7" + "EXAMPLE",
    ]

    real_lines = [
        "mail " + "ann" + "@northfield-demo" + ".test",
        "address " + "10.4" + ".7.21",
        "path " + "/Us" + "ers/jdoe/work",
    ]

    tests = []
    all_pass = True

    with tempfile.TemporaryDirectory() as tmpdir:
        rules_path = os.path.join(tmpdir, "rules.json")
        with open(rules_path, "w", encoding="utf-8") as f:
            f.write(rules_content)

        doc_path = os.path.join(tmpdir, "doc.txt")
        with open(doc_path, "w", encoding="utf-8") as f:
            for line in doc_lines:
                f.write(line + "\n")

        real_path = os.path.join(tmpdir, "real.txt")
        with open(real_path, "w", encoding="utf-8") as f:
            for line in real_lines:
                f.write(line + "\n")

        # Test 1:doc.txt -> exit 0, last line "CLEAN 1 files"
        result1 = subprocess.run(
            [sys.executable, anon_path, "--rules", rules_path, "--scan", doc_path],
            capture_output=True,
            text=True,
        )
        lines1 = [l for l in result1.stdout.splitlines() if l.strip()]
        tests.append((1, 0, "CLEAN 1 files", result1.returncode, lines1[-1] if lines1 else ""))

        # Test 2:real.txt -> exit 12, last line "FOUND 3 in 1 of 1 files"
        result2 = subprocess.run(
            [sys.executable, anon_path, "--rules", rules_path, "--scan", real_path],
            capture_output=True,
            text=True,
        )
        lines2 = [l for l in result2.stdout.splitlines() if l.strip()]
        tests.append((2, 12, "FOUND 3 in 1 of 1 files", result2.returncode, lines2[-1] if lines2 else ""))

        # Test 3: missing file -> exit 2
        fake_path = os.path.join(tmpdir, "nope.txt")
        result3 = subprocess.run(
            [sys.executable, anon_path, "--rules", rules_path, "--scan", fake_path],
            capture_output=True,
            text=True,
        )
        lines3 = [l for l in result3.stdout.splitlines() if l.strip()]
        tests.append((3, 2, "", result3.returncode, lines3[-1] if lines3 else ""))

    for (idx, expected_code, expected_last, got_code, got_last) in tests:
        empty_output = (got_last == "" and expected_last != "")
        if empty_output:
            print("FAIL test %d: empty output, expected code=%d" % (idx, expected_code))
            all_pass = False
            continue

        if idx == 3:
            ok = (got_code == expected_code)
        else:
            ok = (got_code == expected_code and got_last == expected_last)

        if ok:
            print("PASS test %d: expected code=%d last=[%s] got code=%d last=[%s]"
                  % (idx, expected_code, expected_last, got_code, got_last))
        else:
            print("FAIL test %d: expected code=%d last=[%s] got code=%d last=[%s]"
                  % (idx, expected_code, expected_last, got_code, got_last))
            all_pass = False

    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
