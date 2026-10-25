#!/usr/bin/env python3
"""demo_record.py - records the frugalflow terminal demo as an animated SVG."""

import os
import sys
import json
import re
import shutil
import subprocess
import tempfile
import http.server
import threading
import urllib.request
import xml.etree.ElementTree

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import demo_svg

FRUGAL = os.path.join(os.path.dirname(os.path.abspath(__file__)), "frugalflow.py")

USAGE = "usage: demo_record.py --out FILE | --notice | --autotest"

NOTICE = (
    "NAME      demo_record.py - records the frugalflow terminal demo as an animated SVG from the real commands run in a throwaway folder.\n"
    "READS     nothing outside its own temporary folder; it runs frugalflow scan, setup --yes and doctor there against a local fake model server.\n"
    "WRITES    the SVG file named by --out; the temporary folder is removed. The install scene is written by hand, the other three are real outputs.\n"
    "EXAMPLE   python3 demo_record.py --out docs/demo.svg\n"
    "PITFALLS  2026-10-25 a captured doctor line carried the path of the machine; every output is now cleaned and the file is refused if a path or the planted secret is left.\n"
    "          2026-10-25 the user environment keys appeared in the FOUND lines; the commands now run without any variable ending in _API_KEY."
)

APP_LINES = [
    "import os",
    "",
    "API_BASE = \"https://api.example.org\"",
    "api" + "_key = " + chr(34) + "abcd1234efgh5678ijkl" + chr(34),
]


class FakeHandler(http.server.BaseHTTPRequestHandler):

    def do_GET(self):
        if self.path in ("/v1/models", "/models"):
            raw = json.dumps({"data": [{"id": "demo-model"}]}).encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *args):
        pass


def start_fake():
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), FakeHandler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, "http://127.0.0.1:" + str(server.server_address[1])


def _classify(line):
    if re.match(r"FOUND \d", line) or line.startswith("FAIL"):
        return "fail"
    if ": secret " in line or ": private data " in line or line.startswith("WARN"):
        return "warn"
    if (line.startswith("OK") or line.startswith("CLEAN") or line.startswith("CHOSEN")
            or line.startswith("SETUP DONE") or line.startswith("FOUND lmstudio")):
        return "ok"
    if (line.startswith("INFO") or line.startswith("Fix:")
            or line.startswith("False positive?") or line.startswith("exit code")):
        return "dim"
    return "plain"


def _scene_lines(command, raw_lines):
    out = [{"text": command, "cls": "cmd"}]
    for line in raw_lines:
        out.append({"text": line, "cls": _classify(line)})
    return out


def _make_run(sandbox, home_path, pyc_path):
    def run(args, cwd):
        env = os.environ.copy()
        env["HOME"] = home_path
        env["USERPROFILE"] = home_path
        env.pop("FRUGALFLOW_HOME", None)
        for k in list(env):
            if k.endswith("_API_KEY") or k.startswith("GIT_"):
                del env[k]
        env["PYTHONPYCACHEPREFIX"] = pyc_path
        return subprocess.run(
            [sys.executable, FRUGAL] + args,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=300,
            env=env,
        )
    return run


def _make_clean(sandbox, server_addr):
    real_sandbox = os.path.realpath(sandbox)
    port_match = re.compile(r"http://127\.0\.0\.1:\d+")
    py_match = re.compile(r"python3 \S*frugalflow\.py")

    def clean(text):
        text = text.replace(real_sandbox, "<tmp>")
        text = text.replace(sandbox, "<tmp>")
        text = text.replace("<tmp>/home/.frugalflow", "~/.frugalflow")
        text = text.replace("<tmp>/home/.claude", "~/.claude")
        text = text.replace("<tmp>/home", "~")
        text = text.replace("<tmp>/demo-app", "./demo-app")
        text = port_match.sub("http://127.0.0.1:1234", text)
        text = py_match.sub("frugalflow", text)
        return text
    return clean


FORBIDDEN = [
    "/Us" + "ers/", "/private/", "/var/folders", "/tmp/",
    "abcd1234efgh5678ijkl", "Traceback",
]


def _do_out(out_file):
    sandbox = tempfile.mkdtemp(prefix="frugalflow_demo_")
    server = None
    try:
        home_path = os.path.join(sandbox, "home")
        demo_app = os.path.join(sandbox, "demo-app")
        pyc_path = os.path.join(sandbox, "pyc")
        os.makedirs(home_path)
        os.makedirs(demo_app)
        os.makedirs(pyc_path)

        with open(os.path.join(demo_app, "app.py"), "w") as f:
            f.write("\n".join(APP_LINES) + "\n")
        with open(os.path.join(demo_app, "README.md"), "w") as f:
            f.write("# demo-app\n")

        server, addr = start_fake()

        with urllib.request.urlopen(addr + "/v1/models", timeout=5) as resp:
            if resp.status != 200:
                print("REFUSED cannot write " + out_file)
                return 1
        with urllib.request.urlopen(addr + "/models", timeout=5) as resp:
            if resp.status != 200:
                print("REFUSED cannot write " + out_file)
                return 1

        run = _make_run(sandbox, home_path, pyc_path)
        clean = _make_clean(sandbox, addr)

        scenes = []

        # Scene 1: Installation (hardcoded)
        scenes.append({
            "hold": 3.0,
            "lines": [
                {"text": "pipx install git+https://github.com/Blacktizen/frugalflow", "cls": "cmd"},
                {"text": "  installed package frugalflow 0.1.0, installed using Python 3.12", "cls": "plain"},
                {"text": "  These apps are now globally available", "cls": "plain"},
                {"text": "    - frugalflow", "cls": "plain"},
                {"text": "done!", "cls": "ok"},
            ],
        })

        # Scene 2: Scan
        res = run(["scan", "./demo-app"], sandbox)
        if res.returncode != 12:
            print("REFUSED scan exited " + str(res.returncode))
            return 1
        scan_lines = [l for l in clean(res.stdout).splitlines() if l]
        scene2_lines = _scene_lines("frugalflow scan ./demo-app", scan_lines)
        scene2_lines.append({"text": "exit code 12", "cls": "dim"})
        scenes.append({"hold": 5.0, "lines": scene2_lines})

        # Scene 3: Setup
        res = run(["setup", "--yes", "--lmstudio-url", addr,
                   "--ollama-url", "http://127.0.0.1:1"], sandbox)
        if res.returncode != 0:
            print("REFUSED setup exited " + str(res.returncode))
            return 1
        setup_lines = [
            l for l in clean(res.stdout).splitlines() if l
            and (l.startswith("FOUND ") or l.startswith("CHOSEN ")
                 or l.startswith("SET models.json") or l.startswith("BLOCK ")
                 or l.startswith("HOOKS ") or l.startswith("SETUP DONE"))
        ]
        scenes.append({"hold": 4.5, "lines": _scene_lines("frugalflow setup --yes", setup_lines)})

        # Scene 4: Doctor
        res = run(["doctor", "--lmstudio-url", addr,
                   "--ollama-url", "http://127.0.0.1:1"], sandbox)
        if res.returncode != 0:
            print("REFUSED doctor exited " + str(res.returncode))
            return 1
        doctor_lines = [l for l in clean(res.stdout).splitlines() if l][:12]
        scenes.append({"hold": 5.0, "lines": _scene_lines("frugalflow doctor", doctor_lines)})

        # Verification: check all scene text for forbidden substrings
        forbidden_with_sandbox = FORBIDDEN + [sandbox]
        for scene in scenes:
            for entry in scene["lines"]:
                for token in forbidden_with_sandbox:
                    if token in entry["text"]:
                        print("REFUSED demo contains " + token)
                        return 1

        # Write SVG
        svg_text = demo_svg.render(scenes)
        with open(out_file, "w", encoding="utf-8", newline="") as f:
            f.write(svg_text)

        total_lines = sum(len(s["lines"]) for s in scenes)
        dur = demo_svg.duration(scenes)
        print("WROTE " + out_file + " (" + str(total_lines) + " lines, "
              + format(dur, ".1f") + " s)")
        return 0

    finally:
        if server is not None:
            server.shutdown()
        shutil.rmtree(sandbox, ignore_errors=True)


def _autotest():
    tmp = tempfile.mkdtemp(prefix="frugalflow_at_")
    try:
        env = os.environ.copy()
        for k in list(env):
            if k.startswith("GIT_") or k.endswith("_API_KEY"):
                del env[k]
        env["PYTHONPYCACHEPREFIX"] = tmp + "/pyc"
        os.makedirs(env["PYTHONPYCACHEPREFIX"], exist_ok=True)

        script = os.path.abspath(__file__)
        results = []

        def spawn(args):
            return subprocess.run(
                [sys.executable, script] + args,
                capture_output=True, text=True, timeout=600, env=env, cwd=tmp,
            )

        # Test 1: --out succeeds, file valid XML
        out1 = os.path.join(tmp, "demo.svg")
        r = spawn(["--out", out1])
        ok1 = (r.returncode == 0
               and r.stdout.startswith("WROTE ")
               and os.path.isfile(out1))
        if ok1:
            try:
                xml.etree.ElementTree.parse(out1)
            except Exception:
                ok1 = False
        results.append((ok1, "code 0, valid SVG", "code " + str(r.returncode)))

        # Test 2: SVG contains required substrings
        svg_text = ""
        if os.path.isfile(out1):
            with open(out1, "r", encoding="utf-8") as f:
                svg_text = f.read()
        needles = [
            "frugalflow scan ./demo-app",
            "FOUND 1 leak(s) in 1 file(s)",
            "SETUP DONE",
            "OK CLAUDE.md has the FrugalFlow block",
        ]
        missing = [n for n in needles if n not in svg_text]
        ok2 = (len(missing) == 0)
        results.append((ok2, "4 substrings present", "missing: " + str(missing)))

        # Test 3: SVG contains no forbidden substrings
        forbidden_at = FORBIDDEN + [tmp]
        found_bad = [f for f in forbidden_at if f in svg_text]
        ok3 = (len(found_bad) == 0)
        results.append((ok3, "no forbidden path/secret", "found: " + str(found_bad)))

        # Test 4: animation-duration 20-45, at least 25 text elements
        ok4 = False
        dur_str = "?"
        txt_count = 0
        if svg_text:
            root = xml.etree.ElementTree.fromstring(svg_text)
            ns = {"svg": "http://www.w3.org/2000/svg"}
            # remove namespace for simpler xpath
            texts = root.findall(".//{http://www.w3.org/2000/svg}text")
            txt_count = len(texts)
            # find animation-duration in style
            dur_m = re.search(r"animation-duration:\s*([0-9.]+)s", svg_text)
            if dur_m:
                dur_val = float(dur_m.group(1))
                dur_str = str(dur_val)
                ok4 = (20 <= dur_val <= 45 and txt_count >= 25)
        results.append((ok4, "duration 20-45, texts>=25", "dur=" + dur_str + " texts=" + str(txt_count)))

        # Test 5: no args -> 2; --notice -> 0; bad out dir -> 1
        r_narg = spawn([])
        r_notice = spawn(["--notice"])
        bad_out = os.path.join(tmp, "absent", "demo.svg")
        r_bad = spawn(["--out", bad_out])
        ok5 = (
            r_narg.returncode == 2 and "usage: demo_record.py" in r_narg.stdout
            and r_notice.returncode == 0
            and r_bad.returncode == 1 and "REFUSED cannot write " in r_bad.stdout
        )
        results.append((ok5, "2/0/1", "got " + str(r_narg.returncode) + "/"
                        + str(r_notice.returncode) + "/" + str(r_bad.returncode)))

        pass_count = 0
        for i, (passed, expected, got) in enumerate(results, 1):
            tag = "PASS" if passed else "FAIL"
            print(tag + " " + str(i) + ": " + expected + ", got " + got)
            if passed:
                pass_count += 1

        print("AUTOTEST " + str(pass_count) + "/5")
        return 0 if pass_count == 5 else 1

    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main(argv):
    if argv == ["--notice"]:
        print(NOTICE)
        return 0
    if argv == ["--autotest"]:
        return _autotest()
    if len(argv) == 2 and argv[0] == "--out":
        out_file = argv[1]
        parent = os.path.dirname(out_file) or "."
        if not os.path.isdir(parent):
            print("REFUSED cannot write " + out_file)
            return 1
        return _do_out(out_file)
    print(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
