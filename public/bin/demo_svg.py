import sys
import os
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from xml.sax.saxutils import escape

NOTICE = (
    "NAME      demo_svg.py - draws an animated terminal recording as one SVG file,"
    " with no tool and no script inside.\n"
    "READS     nothing: pure module, it only works on the scenes it is given.\n"
    "WRITES    nothing: render returns the SVG text, duration returns the length in seconds.\n"
    "EXAMPLE   python3 demo_svg.py --autotest\n"
    "PITFALLS  2026-10-25 text longer than the window ran out of the picture;"
    " lines are now cut at 100 characters.\n"
    "          2026-10-25 a raw less-than sign in a captured line broke the whole SVG;"
    " every line is escaped."
)

VALID_CLS = frozenset(("cmd", "ok", "warn", "fail", "dim", "plain"))


def _norm(cls):
    return cls if cls in VALID_CLS else "plain"


def _timeline(scenes):
    scenes = [s for s in scenes if s["lines"]]
    if not scenes:
        return 1.0, []
    t = 0.0
    entries = []
    scene_ends = []
    gi = 0
    for si, scene in enumerate(scenes):
        lines = scene["lines"]
        hold = scene["hold"]
        lt = round(t + 0.3, 3)
        for j in range(len(lines)):
            if j > 0:
                prev = _norm(lines[j - 1]["cls"])
                lt = round(lt + (0.9 if prev == "cmd" else 0.18), 3)
            entries.append((gi, si, j, lt))
            gi += 1
        se = round(entries[-1][3] + hold, 3)
        scene_ends.append(se)
        t = round(se + 0.4, 3)
    total = round(scene_ends[-1] + 1.0, 3)
    for i in range(len(entries)):
        si = entries[i][1]
        entries[i] = (entries[i][0], entries[i][1], entries[i][2],
                      entries[i][3], scene_ends[si])
    return total, entries


def duration(scenes):
    return _timeline(scenes)[0]


def render(scenes, width=860):
    total, entries = _timeline(scenes)
    m = 0
    for e in entries:
        s = e[1]
        cnt = sum(1 for x in entries if x[1] == s)
        if cnt > m:
            m = cnt
    h = 28 + 16 + m * 20 + 16
    dur_s = "%.3f" % total
    parts = []
    parts.append(
        '<svg xmlns="http://www.w3.org/2000/svg" width="%d"'
        ' height="%d" viewBox="0 0 %d %d" role="img"'
        ' aria-label="Terminal demo of frugalflow">'
        % (width, h, width, h)
    )
    parts.append('<title>Terminal demo of frugalflow</title>')
    style = []
    style.append(
        'text{font-family:ui-monospace,SFMono-Regular,Menlo,'
        'Consolas,monospace;font-size:14px;white-space:pre}'
    )
    style.append(
        '.cmd{fill:#e6edf3}.ok{fill:#3fb950}.warn{fill:#d29922}'
        '.fail{fill:#f85149}.dim{fill:#8b949e}.plain{fill:#c9d1d9}'
        '.p{fill:#3fb950}'
    )
    style.append(
        '.l{opacity:0;animation-duration:%ss;'
        'animation-iteration-count:infinite;'
        'animation-timing-function:step-end}' % dur_s
    )
    for gi, si, j, lt, se in entries:
        style.append('.l%d{animation-name:k%d}' % (gi, gi))
        a = round(lt / total * 100, 3)
        a2 = round(a + 0.001, 3)
        b = round(se / total * 100, 3)
        b2 = round(b + 0.001, 3)
        style.append(
            '@keyframes k%d{0%%,%.3f%%{opacity:0}%.3f%%,%.3f%%'
            '{opacity:1}%.3f%%,100%%{opacity:0}}' % (gi, a, a2, b, b2)
        )
    parts.append('<style>' + ''.join(style) + '</style>')
    parts.append('<rect width="%d" height="%d" rx="8" fill="#0d1117"/>'
                 % (width, h))
    parts.append('<rect width="%d" height="28" rx="8" fill="#161b22"/>' % width)
    parts.append('<circle cx="18" cy="14" r="5" fill="#f85149"/>')
    parts.append('<circle cx="36" cy="14" r="5" fill="#d29922"/>')
    parts.append('<circle cx="54" cy="14" r="5" fill="#3fb950"/>')
    scenes_filtered = [s for s in scenes if s["lines"]]
    for gi, si, j, lt, se in entries:
        line = scenes_filtered[si]["lines"][j]
        cls = _norm(line["cls"])
        txt = line["text"]
        if len(txt) > 100:
            txt = txt[:97] + "..."
        y = 28 + 24 + j * 20
        if cls == "cmd":
            inner = '<tspan class="p">$ </tspan>' + escape(txt)
        else:
            inner = escape(txt)
        parts.append(
            '<text class="l l%d %s" x="20" y="%d">%s</text>'
            % (gi, cls, y, inner)
        )
    parts.append('</svg>')
    return '\n'.join(parts) + '\n'


def _tag(el):
    t = el.tag
    if '}' in t:
        return t.split('}', 1)[1]
    return t


def _autotest():
    S1 = {
        "lines": [
            {"text": "x", "cls": "cmd"},
            {"text": "y", "cls": "plain"},
            {"text": "z", "cls": "ok"},
        ],
        "hold": 2.0,
    }
    S2 = {"lines": [{"text": "w", "cls": "cmd"}], "hold": 1.0}
    ODD = {
        "lines": [
            {"text": "a<b & c > d", "cls": "warn"},
            {"text": "A" * 120, "cls": "weird"},
        ],
        "hold": 0.5,
    }
    results = []

    # Test 1: duration
    d1 = duration([S1])
    d2 = duration([S1, S2])
    ok1 = abs(d1 - 4.38) < 0.0005 and abs(d2 - 6.08) < 0.0005
    results.append((ok1, "expected 4.380 6.080 got %.3f %.3f" % (d1, d2)))

    # Test 2: structure
    svg2 = render([S1, S2])
    ok2 = False
    try:
        root = ET.fromstring(svg2)
        if (_tag(root) == "svg"
                and root.get("width") == "860"
                and root.get("height") == "120"):
            texts = [el for el in root.iter() if _tag(el) == "text"]
            ok2 = len(texts) == 4
    except ET.ParseError:
        pass
    results.append((ok2, "expected svg 860x120 with 4 text elements"))

    # Test 3: escape and truncate
    svg3 = render([ODD])
    ok3 = False
    try:
        root = ET.fromstring(svg3)
        texts = [el for el in root.iter() if _tag(el) == "text"]
        t0 = texts[0].text or ""
        t1 = texts[1].text or ""
        cls1 = texts[1].get("class", "")
        ok3 = (
            t0 == "a<b & c > d"
            and "a&lt;b &amp; c &gt; d" in svg3
            and t1 == "A" * 97 + "..."
            and "plain" in cls1
            and "weird" not in cls1
        )
    except (ET.ParseError, IndexError):
        pass
    results.append((ok3, "escape/truncate/class checks"))

    # Test 4: animation
    svg4 = render([S1, S2])
    expected_kf = (
        "@keyframes k0{0%,4.934%{opacity:0}4.935%,55.592%"
        "{opacity:1}55.593%,100%{opacity:0}}"
    )
    kf_count = svg4.count("@keyframes k")
    ok4 = (
        kf_count == 4
        and "animation-duration:6.080s" in svg4
        and expected_kf in svg4
    )
    results.append((ok4, "keyframes=%d duration=%s exact_match=%s"
                    % (kf_count, "animation-duration:6.080s" in svg4,
                       expected_kf in svg4)))

    # Test 5: cleanliness
    svg5a = render([S1])
    svg5b = render([S1])
    same_output = (svg5a == svg5b)
    http_count = svg5a.count("http")
    no_script = "<script" not in svg5a
    no_href = "href" not in svg5a
    empty_dur = duration([])
    svg_empty = render([])
    ok_empty = (empty_dur == 1.0)
    try:
        root_e = ET.fromstring(svg_empty)
        texts_e = [el for el in root_e.iter() if _tag(el) == "text"]
        ok_empty = ok_empty and len(texts_e) == 0
    except ET.ParseError:
        ok_empty = False
    env = os.environ.copy()
    pycache_dir = tempfile.mkdtemp()
    env["PYTHONPYCACHEPREFIX"] = pycache_dir
    proc = subprocess.run(
        [sys.executable, os.path.abspath(__file__)],
        capture_output=True, text=True, env=env,
    )
    expected_usage = "usage: demo_svg.py --notice | --autotest"
    ok_cli = (proc.stdout.strip() == expected_usage
              and proc.returncode == 2)
    ok5 = (same_output and http_count == 1 and no_script
           and no_href and ok_empty and ok_cli)
    results.append((ok5, "same=%s http=%d script=%s href=%s empty=%s cli=%d/%d"
                    % (same_output, http_count, no_script, no_href,
                       ok_empty, proc.returncode, 2)))

    passed = 0
    for i, (ok, msg) in enumerate(results):
        tag = "PASS" if ok else "FAIL"
        print("%s test %d: %s" % (tag, i + 1, msg))
        if ok:
            passed += 1
    print("AUTOTEST %d/5" % passed)
    return 0 if passed == 5 else 1


if __name__ == "__main__":
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        print(NOTICE)
        sys.exit(0)
    elif len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(_autotest())
    else:
        print("usage: demo_svg.py --notice | --autotest")
        sys.exit(2)
