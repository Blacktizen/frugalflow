#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import http.server
import importlib.util
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading

BIN = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "bin")


def LOAD(name):
    fpath = os.path.join(BIN, name + ".py")
    spec = importlib.util.spec_from_file_location(name + "_e2e", fpath)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def REC(seconds, chars=100, model="m", status="success"):
    return {"status": status, "model_asked": model, "seconds": seconds, "chars": chars}


LEAK = "owner = 'Ginette'\n"
CLEAN = "x = 1\n"
ANSWER_LEAK = '{"line": 1, "excerpt": "Ginette", "kind": "private_name", "why": "a first name"}'


def MODELS(port):
    own = {
        "id": "own", "name": "alpha-7b", "location": "remote",
        "endpoint": "http://127.0.0.1:" + str(port) + "/v1",
        "context_window": 8192, "trust": "private", "key_env": "",
        "max_output": 1024,
    }
    return {
        "models": [own],
        "layers": [{"name": "work", "delegable": True}],
        "roles": [{"name": "documents", "layer": "work", "model": "own"}],
    }


def DEAD_PORT():
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def RUN(args, env_extra=None):
    env = {k: v for k, v in os.environ.items() if k != "FRUGALFLOW_BRIEF_RULES"}
    if env_extra:
        env.update(env_extra)
    try:
        r = subprocess.run(
            [sys.executable] + args,
            capture_output=True, text=True, env=env, timeout=180,
        )
        return (r.returncode, r.stdout)
    except subprocess.TimeoutExpired:
        return (-1, "")


def SUPPORT(d):
    # a tool copied alone imports exit_log at startup; its support modules ride along.
    for module in ("exit_log.py", "block_log.py", "block_rules.py", "verify_extra.py"):
        shutil.copy(os.path.join(BIN, module), os.path.join(d, module))


def BROKEN(name, find, replace, d):
    src = os.path.join(BIN, name + ".py")
    dst = os.path.join(d, name + ".py")
    shutil.copy(src, dst)
    SUPPORT(d)
    with open(dst, "r", encoding="utf-8") as f:
        txt = f.read()
    if txt.count(find) != 1:
        raise ValueError("anchor not found: " + find)
    txt = txt.replace(find, replace)
    with open(dst, "w", encoding="utf-8") as f:
        f.write(txt)
    return dst


class _FakeHandler(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        if self.path == "/v1/chat/completions":
            length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(length).decode("utf-8", errors="replace")
            if "Ginette" in body:
                answer = ANSWER_LEAK
            else:
                answer = "NONE"
            payload = json.dumps({
                "model": "alpha-7b",
                "choices": [{"message": {"content": answer}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            })
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(payload.encode("utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, *a, **kw):
        pass


def run_e2e():
    server = http.server.HTTPServer(("127.0.0.1", 0), _FakeHandler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()

    lines = []

    # ---- Step 1: verify ----
    with tempfile.TemporaryDirectory() as d:
        v = LOAD("verify_rules")
        target1 = os.path.join(d, "e.py")
        c1 = v.judge("python3 -m py_compile x.py", target1)
        ok1a = c1[0] == 3
        ok1b = any(ln.startswith("VERIFY WEAK: ") for ln in c1[2])
        target2 = os.path.join(d, "t.py")
        c2 = v.judge("python3 " + target2 + " --autotest", target2)
        ok2a = c2[0] == 0
        ok2b = "$FRUGALFLOW_CANDIDATE" in c2[1]
        ok2c = len(c2[2]) > 0 and c2[2][0].startswith("VERIFY CORRECTED: ")
        ok = ok1a and ok1b and ok2a and ok2b and ok2c
        exp = "code3+WEAK, code0+CANDIDATE+CORRECTED"
        if ok:
            lines.append("PASS 1 verify: expected " + exp + " got " + exp)
        else:
            got = "c1_code=%s c1_weak=%s c2_code=%s c2_cand=%s c2_corr=%s" % (
                c1[0], ok1b, c2[0], ok2b, ok2c)
            lines.append("FAIL 1 verify: expected " + exp + " got " + got)

    # ---- Step 2: verify_bites ----
    with tempfile.TemporaryDirectory() as d:
        okdir = os.path.join(d, "ok")
        os.makedirs(okdir)
        shutil.copy(os.path.join(BIN, "verify_rules.py"), os.path.join(okdir, "verify_rules.py"))
        SUPPORT(okdir)
        rc0, out0 = RUN([os.path.join(okdir, "verify_rules.py"), "--autotest"])
        ok_healthy = rc0 == 0
        p = BROKEN(
            "verify_rules",
            "def weak_reason(cmd):",
            "def weak_reason(cmd):\n    return None\ndef _e2e_unused(cmd):",
            d,
        )
        rc1, out1 = RUN([p, "--autotest"])
        ok_broken = rc1 == 1 and "FAIL" in out1
        if out1 == "":
            ok_broken = False
        ok = ok_healthy and ok_broken
        exp = "healthy_rc=0, broken_rc=1+FAIL"
        if ok:
            lines.append("PASS 2 verify_bites: expected " + exp + " got " + exp)
        else:
            got = "healthy_rc=%s broken_rc=%s broken_hasFAIL=%s" % (rc0, rc1, "FAIL" in out1)
            lines.append("FAIL 2 verify_bites: expected " + exp + " got " + got)

    # ---- Step 3: eta ----
    with tempfile.TemporaryDirectory() as d:
        e = LOAD("eta_rules")
        est1 = e.estimate([REC(10), REC(20), REC(60)], "m", 100)
        est2 = e.estimate([REC(10), REC(20)], "m", 100)
        est3 = e.estimate([REC(10), REC(20), REC(60, status="failure")], "m", 100)
        ok1 = est1 == (20.0, 3)
        ok2 = est2 is None
        ok3 = est3 is None
        okdir = os.path.join(d, "ok")
        os.makedirs(okdir)
        shutil.copy(os.path.join(BIN, "eta_rules.py"), os.path.join(okdir, "eta_rules.py"))
        SUPPORT(okdir)
        rc0, out0 = RUN([os.path.join(okdir, "eta_rules.py"), "--autotest"])
        ok4 = rc0 == 0
        p = BROKEN("eta_rules", "MINIMUM = 3", "MINIMUM = 1", d)
        rc1, out1 = RUN([p, "--autotest"])
        ok5 = rc1 == 1 and "FAIL" in out1
        if out1 == "":
            ok5 = False
        ok = ok1 and ok2 and ok3 and ok4 and ok5
        exp = "(20.0,3),None,None,autotest0,broken_rc=1+FAIL"
        if ok:
            lines.append("PASS 3 eta: expected " + exp + " got " + exp)
        else:
            got = "est1=%s est2=%s est3=%s healthy_rc=%s broken_rc=%s" % (
                est1, est2, est3, rc0, rc1)
            lines.append("FAIL 3 eta: expected " + exp + " got " + got)

    # ---- Step 4: anon_leak ----
    with tempfile.TemporaryDirectory() as d:
        home = os.path.join(d, "home")
        os.makedirs(home)
        with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(MODELS(port)))
        leak_path = os.path.join(d, "leak.txt")
        clean_path = os.path.join(d, "clean.txt")
        with open(leak_path, "w", encoding="utf-8") as f:
            f.write(LEAK)
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(CLEAN)
        env4 = {"FRUGALFLOW_HOME": home}
        rc_l, out_l = RUN([os.path.join(BIN, "anon_review.py"), leak_path], env4)
        ok_lc = rc_l == 4
        ok_ls = "SUSPECT " in out_l
        ok_ld = ":1 private_name" in out_l
        ok_ln = "Ginette" not in out_l
        rc_c, out_c = RUN([os.path.join(BIN, "anon_review.py"), clean_path], env4)
        ok_cc = rc_c == 0
        ok_co = "CLEAN " in out_c
        jsonl = os.path.join(home, "anon_review.jsonl")
        n_lines = 0
        if os.path.exists(jsonl):
            with open(jsonl, "r", encoding="utf-8") as f:
                n_lines = len(f.readlines())
        ok_jl = n_lines == 2
        ok = ok_lc and ok_ls and ok_ld and ok_ln and ok_cc and ok_co and ok_jl
        exp = "leak_rc=4+SUSPECT+noGinette, clean_rc=0+CLEAN, jsonl=2"
        if ok:
            lines.append("PASS 4 anon_leak: expected " + exp + " got " + exp)
        else:
            got = "leak_rc=%s SUSPECT=%s detail=%s noGinette=%s clean_rc=%s CLEAN=%s jsonl=%d" % (
                rc_l, ok_ls, ok_ld, ok_ln, rc_c, ok_co, n_lines)
            lines.append("FAIL 4 anon_leak: expected " + exp + " got " + got)

    # ---- Step 5: anon_unplugged ----
    with tempfile.TemporaryDirectory() as d:
        home = os.path.join(d, "home")
        os.makedirs(home)
        with open(os.path.join(home, "models.json"), "w", encoding="utf-8") as f:
            f.write(json.dumps(MODELS(DEAD_PORT())))
        clean_path = os.path.join(d, "clean.txt")
        with open(clean_path, "w", encoding="utf-8") as f:
            f.write(CLEAN)
        env5 = {"FRUGALFLOW_HOME": home}
        rc, out = RUN([os.path.join(BIN, "anon_review.py"), clean_path], env5)
        ok_c = rc == 3
        ok_u = "UNREAD " in out
        ok_nc = "CLEAN " not in out
        if out == "":
            ok_u = False
        ok = ok_c and ok_u and ok_nc
        exp = "rc=3+UNREAD+noCLEAN"
        if ok:
            lines.append("PASS 5 anon_unplugged: expected " + exp + " got " + exp)
        else:
            got = "rc=%s UNREAD=%s noCLEAN=%s" % (rc, ok_u, ok_nc)
            lines.append("FAIL 5 anon_unplugged: expected " + exp + " got " + got)

    server.shutdown()

    for ln in lines:
        print(ln)

    all_pass = all(ln.startswith("PASS") for ln in lines)
    if all_pass:
        print("E2E DELEGATION SERVER OK")
        return 0
    print("E2E DELEGATION SERVER FAILED")
    return 1


NOTICE = (
    "NAME      e2e_delegation_server.py - end-to-end test: "
    "the --verify guard, the delay estimate and the AI anonymization review, "
    "with a fake local engine.\n"
    "READS     the tools in ../bin next to this file; everything else lives in temporary folders.\n"
    "WRITES    nothing outside its temporary folders: one PASS or FAIL line per step, "
    "then E2E DELEGATION SERVER OK (0) or E2E DELEGATION SERVER FAILED (1).\n"
    "EXAMPLE   python3 e2e_delegation_server.py\n"
    "PITFALLS  2026-09-26 the exit code 1 of verify_rules and eta_rules was proved nowhere; "
    "this suite runs their self-test on a broken copy and must see it fail.\n"
)

USAGE = "usage: e2e_delegation_server.py [--autotest] | --notice"


def main():
    if len(sys.argv) == 2 and sys.argv[1] == "--notice":
        sys.stdout.write(NOTICE)
        sys.exit(0)
    if len(sys.argv) == 2 and sys.argv[1] == "--autotest":
        sys.exit(run_e2e())
    if len(sys.argv) == 1:
        sys.exit(run_e2e())
    print(USAGE)
    sys.exit(2)


if __name__ == "__main__":
    main()
