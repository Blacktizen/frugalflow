import sys
import os
import re
import difflib
import unicodedata
import tempfile
import subprocess


def fold(text):
    out = []
    for ch in text:
        if ch in (chr(0x2018), chr(0x2019), chr(0x201B), chr(0x2032)):
            out.append("'")
        elif ch in (chr(0x201C), chr(0x201D), chr(0x201E), chr(0x2033),
                    chr(0x00AB), chr(0x00BB)):
            out.append('"')
        elif ch in (chr(0x2010), chr(0x2011), chr(0x2012), chr(0x2013),
                    chr(0x2014), chr(0x2015), chr(0x2212)):
            out.append('-')
        elif ch == chr(0x2026):
            out.append('...')
        elif ch == chr(0xFB01):
            out.append('fi')
        elif ch == chr(0xFB02):
            out.append('fl')
        elif unicodedata.category(ch) == 'Zs':
            out.append(' ')
        else:
            out.append(ch)
    return ''.join(out)


def _line_content(line):
    if line.endswith('\r\n'):
        return line[:-2]
    if line.endswith('\r'):
        return line[:-1]
    if line.endswith('\n'):
        return line[:-1]
    return line


def _line_ending(line):
    if line.endswith('\r\n'):
        return '\r\n'
    if line.endswith('\r'):
        return '\r'
    if line.endswith('\n'):
        return '\n'
    return ''


def restore_line(original, produced):
    pattern = r'\.\.\.' + '|' + chr(0x2026) + '|' + '.'
    tok_o = re.findall(pattern, original)
    tok_p = re.findall(pattern, produced)
    folded_o = [fold(t) for t in tok_o]
    folded_p = [fold(t) for t in tok_p]
    sm = difflib.SequenceMatcher(None, folded_o, folded_p, autojunk=False)
    result = []
    n = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            for idx in range(i1, i2):
                jdx = j1 + (idx - i1)
                if tok_o[idx] != tok_p[jdx]:
                    n += 1
            result.extend(tok_o[i1:i2])
        elif tag == 'replace':
            result.extend(tok_p[j1:j2])
        elif tag == 'insert':
            result.extend(tok_p[j1:j2])
        elif tag == 'delete':
            pass
    return ''.join(result), n


def restore(original_text, produced_text):
    lines_o = original_text.splitlines(True)
    lines_p = produced_text.splitlines(True)
    contents_o = [_line_content(l) for l in lines_o]
    contents_p = [_line_content(l) for l in lines_p]

    sm = difflib.SequenceMatcher(None, contents_o, contents_p, autojunk=False)

    report = {'restored': 0, 'changed': 0, 'partial': 0, 'added': 0, 'removed': 0}
    output_lines = []

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == 'equal':
            output_lines.extend(lines_o[i1:i2])
        elif tag == 'delete':
            pass
        elif tag == 'insert':
            output_lines.extend(lines_p[j1:j2])
        elif tag == 'replace':
            n_orig = i2 - i1
            n_prod = j2 - j1
            pairs = min(n_orig, n_prod)
            for k in range(pairs):
                orig_line = lines_o[i1 + k]
                prod_line = lines_p[j1 + k]
                orig_content = contents_o[i1 + k]
                prod_content = contents_p[j1 + k]
                if fold(orig_content) == fold(prod_content):
                    output_lines.append(orig_line)
                    report['restored'] += 1
                else:
                    rendered, n = restore_line(orig_content, prod_content)
                    ending = _line_ending(prod_line)
                    output_lines.append(rendered + ending)
                    report['changed'] += 1
                    if n > 0:
                        report['partial'] += 1
            if n_prod > pairs:
                for k in range(pairs, n_prod):
                    output_lines.append(lines_p[j1 + k])
                report['added'] += n_prod - pairs
            if n_orig > pairs:
                report['removed'] += n_orig - pairs

    return ''.join(output_lines), report


def print_notice():
    lines = [
        "NAME      fidelity.py - gives a produced text back the typography of its original wherever nothing else changed: apostrophes, quotes, dashes, ellipses, special spaces.",
        "READS     the original file and the produced file named on the command line.",
        "WRITES    nothing, or the produced file rewritten in place with --write; it prints five counters.",
        "EXAMPLE   python3 fidelity.py original.txt produced.txt --write",
        "PITFALLS  2026-10-23 a model rewrote a word and silently turned every curly apostrophe of the same line into a straight one; lines that were changed were never repaired, only untouched lines were.",
    ]
    for line in lines:
        print(line)


def run_autotest():
    fidelity_path = os.path.abspath(__file__)
    cache_dir = tempfile.mkdtemp()
    sys.dont_write_bytecode = True

    env = os.environ.copy()
    env['PYTHONDONTWRITEBYTECODE'] = '1'
    env['PYTHONPYCACHEPREFIX'] = cache_dir

    tmp_dir = tempfile.mkdtemp()

    def write_tmp(name, content):
        path = os.path.join(tmp_dir, name)
        with open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(content)
        return path

    def read_file(path):
        with open(path, 'r', encoding='utf-8', newline='') as f:
            return f.read()

    A = chr(0x2019)
    E = chr(0x2026)
    N = chr(0x202F)

    O = ("Don" + A + "t forget the old project.\n"
         "The project runs 12 pages" + E + " plus a few diagrams.\n"
         "Is the project ready by noon" + N + "?\n"
         "This line does not change.\n")

    P1 = ("Don't forget the old venture.\n"
          "The venture runs 12 pages... plus a few diagrams.\n"
          "Is the project ready by noon ?\n"
          "This line does not change.\n")

    P2 = ("Don't forget the old venture.\n"
          "The venture runs 12 pages... plus a few diagrams.\n"
          "Is the project ready by noon ?\n"
          "This line has changed.\n"
          "End.\n")

    expected_1 = ("Don" + A + "t forget the old venture.\n"
                  "The venture runs 12 pages" + E + " plus a few diagrams.\n"
                  "Is the project ready by noon" + N + "?\n"
                  "This line does not change.\n")

    results = []

    # --- Test 1: O vs P1 with --write ---
    orig_f = write_tmp('t1_orig', O)
    prod_f = write_tmp('t1_prod', P1)
    proc = subprocess.run(
        [sys.executable, fidelity_path, orig_f, prod_f, '--write'],
        capture_output=True, text=True, env=env)
    code = proc.returncode
    stdout = proc.stdout
    rendered = read_file(prod_f)
    checks = []
    if not stdout:
        checks.append('stdout empty')
    if code != 1:
        checks.append('exit expected 1 got ' + str(code))
    if rendered != expected_1:
        checks.append('file content mismatch')
    for expected_line in ['restored 1', 'changed 2', 'partial 2', 'added 0', 'removed 0']:
        if expected_line not in stdout:
            checks.append('missing ' + expected_line)
    if checks:
        results.append('FAIL test1: expected exit 1 and restored 1/changed 2/partial 2/added 0/removed 0 and restored file; got ' + '; '.join(checks))
    else:
        results.append('PASS test1: exit 1, file restored, counters correct')

    # --- Test 2a: O vs P1 without --write, then 2b: O vs O ---
    prod_f2a = write_tmp('t2a_prod', P1)
    orig_f2a = write_tmp('t2a_orig', O)
    proc2a = subprocess.run(
        [sys.executable, fidelity_path, orig_f2a, prod_f2a],
        capture_output=True, text=True, env=env)
    checks2a = []
    if proc2a.returncode != 1:
        checks2a.append('exit expected 1 got ' + str(proc2a.returncode))
    if not proc2a.stdout:
        checks2a.append('stdout empty')
    if read_file(prod_f2a) != P1:
        checks2a.append('PRODUCED was modified without --write')

    prod_f2b = write_tmp('t2b_prod', O)
    orig_f2b = write_tmp('t2b_orig', O)
    proc2b = subprocess.run(
        [sys.executable, fidelity_path, orig_f2b, prod_f2b],
        capture_output=True, text=True, env=env)
    if proc2b.returncode != 0:
        checks2a.append('O vs O exit expected 0 got ' + str(proc2b.returncode))
    if 'restored 0' not in proc2b.stdout:
        checks2a.append('O vs O missing restored 0')

    if checks2a:
        results.append('FAIL test2: ' + '; '.join(checks2a))
    else:
        results.append('PASS test2: no-write exit 1 file unchanged; O vs O exit 0 restored 0')

    # --- Test 3: O vs P2 with --write ---
    prod_f3 = write_tmp('t3_prod', P2)
    orig_f3 = write_tmp('t3_orig', O)
    proc3 = subprocess.run(
        [sys.executable, fidelity_path, orig_f3, prod_f3, '--write'],
        capture_output=True, text=True, env=env)
    checks3 = []
    if not proc3.stdout:
        checks3.append('stdout empty')
    written3 = read_file(prod_f3)
    if 'End.\n' not in written3:
        checks3.append('End. line missing')
    if 'This line has changed.\n' not in written3:
        checks3.append('This line has changed. missing')
    if 'added 1' not in proc3.stdout:
        checks3.append('missing added 1')
    if proc3.returncode != 1:
        checks3.append('exit expected 1 got ' + str(proc3.returncode))
    if checks3:
        results.append('FAIL test3: ' + '; '.join(checks3))
    else:
        results.append('PASS test3: End. kept, line4 unchanged, added 1, exit 1')

    # --- Test 4: fold invariant ---
    checks4 = []
    for label, orig_text, prod_text in [
        ('test1', O, P1),
        ('test2', O, P1),
        ('test3', O, P2),
    ]:
        rendered_text, _ = restore(orig_text, prod_text)
        if fold(rendered_text) != fold(prod_text):
            checks4.append(label + ': fold mismatch')
    if checks4:
        results.append('FAIL test4: ' + '; '.join(checks4))
    else:
        results.append('PASS test4: fold invariant holds for tests 1-3')

    # --- Test 5: no args, --notice ---
    checks5 = []
    proc5a = subprocess.run(
        [sys.executable, fidelity_path],
        capture_output=True, text=True, env=env)
    if proc5a.returncode != 2:
        checks5.append('no-args exit expected 2 got ' + str(proc5a.returncode))
    if not proc5a.stdout:
        checks5.append('no-args stdout empty')

    proc5b = subprocess.run(
        [sys.executable, fidelity_path, '--notice'],
        capture_output=True, text=True, env=env)
    if proc5b.returncode != 0:
        checks5.append('--notice exit expected 0 got ' + str(proc5b.returncode))
    expected_notice = (
        "NAME      fidelity.py - gives a produced text back the typography of its original wherever nothing else changed: apostrophes, quotes, dashes, ellipses, special spaces.\n"
        "READS     the original file and the produced file named on the command line.\n"
        "WRITES    nothing, or the produced file rewritten in place with --write; it prints five counters.\n"
        "EXAMPLE   python3 fidelity.py original.txt produced.txt --write\n"
        "PITFALLS  2026-10-23 a model rewrote a word and silently turned every curly apostrophe of the same line into a straight one; lines that were changed were never repaired, only untouched lines were.\n"
    )
    if proc5b.stdout != expected_notice:
        checks5.append('--notice content mismatch')

    if checks5:
        results.append('FAIL test5: ' + '; '.join(checks5))
    else:
        results.append('PASS test5: exit codes 2 and 0 correct, notice exact')

    for r in results:
        print(r)

    all_pass = all(r.startswith('PASS') for r in results)
    return 0 if all_pass else 1


def main():
    args = sys.argv[1:]

    if args == ['--notice']:
        print_notice()
        sys.exit(0)

    if args == ['--autotest']:
        sys.exit(run_autotest())

    write_flag = False
    positional = []
    for a in args:
        if a == '--write':
            write_flag = True
        else:
            positional.append(a)

    if len(positional) < 2:
        print("usage: python3 fidelity.py ORIGINAL PRODUCED [--write]")
        sys.exit(2)

    orig_path = positional[0]
    prod_path = positional[1]

    try:
        with open(orig_path, 'r', encoding='utf-8', newline='') as f:
            original_text = f.read()
        with open(prod_path, 'r', encoding='utf-8', newline='') as f:
            produced_text = f.read()
    except OSError:
        print("usage: python3 fidelity.py ORIGINAL PRODUCED [--write]")
        sys.exit(2)

    rendered, report = restore(original_text, produced_text)

    print("restored " + str(report['restored']))
    print("changed " + str(report['changed']))
    print("partial " + str(report['partial']))
    print("added " + str(report['added']))
    print("removed " + str(report['removed']))

    differs = rendered != produced_text

    if write_flag and differs:
        with open(prod_path, 'w', encoding='utf-8', newline='') as f:
            f.write(rendered)

    sys.exit(1 if differs else 0)


if __name__ == '__main__':
    main()
