#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""mcp_server.py - the FrugalFlow MCP server on stdio: journal_add, lint_brief, resume, delegate, launched outside the Claude Code sandbox."""

import os
import sys
import json
import shutil
import tempfile
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

USAGE ="usage: mcp_server.py --notice | --autotest\n"

NOTICE = (
    "NAME      mcp_server.py - the FrugalFlow MCP server on stdio: four tools (journal_add, lint_brief, resume, delegate) that run the real tools outside the Claude Code sandbox.\n"
    "READS     one JSON-RPC 2.0 message per line on stdin; each tool reads what the tool it launches reads.\n"
    "WRITES    nothing by itself: a journal entry or a delegation receipt exists only through the tool that verifies it. JSON responses on stdout, one per line; debug on stderr. Exit 0 when stdin closes, 2 usage.\n"
    "EXAMPLE   python3 mcp_server.py   (the plugin registers it in .mcp.json; the client talks to it over stdio)\n"
    "PITFALLS  2026-11-13 inside the sandbox Bash can no longer write the journal or the receipts: this server runs with the user's rights outside the sandbox, so a receipt written through a tool cannot be forged by the assistant.\n"
    "          2026-11-13 stdout carries JSON responses only: one stray print breaks the client's stream; debug lines go to stderr.\n"
    "          2026-11-13 delegate over MCP ran the verify command and wrote out anywhere outside the sandbox; verify is refused and out is confined to the project.\n"
    "          2026-11-13 Claude Code loads CLAUDE.md and CLAUDE.local.md as instructions at any depth: an out whose base name is either one is refused."
)

BIN = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PROTOCOL = "2025-06-18"

# The server runs outside the sandbox: the out path it hands to delegate.py must stay
# inside the project, and no component of a request is ever run as a command.
WORK_ROOT = os.path.realpath(os.getcwd())
PROTECTED_COMPONENTS = {".git", ".githooks", ".claude", "vault"}
PROTECTED_NAMES = {"CLAUDE.md", "CLAUDE.local.md", ".mcp.json", "settings.json", "settings.local.json"}


def server_version():
    """The package version: the installed metadata first, then pyproject.toml at the repository root, then a last resort."""
    try:
        import importlib.metadata
        return importlib.metadata.version("frugalflow")
    except Exception:
        pass
    try:
        with open(os.path.join(BIN, "..", "..", "pyproject.toml"), "r", encoding="utf-8") as handle:
            for line in handle:
                stripped = line.strip()
                if stripped.startswith("version"):
                    parts = stripped.split("=", 1)
                    if len(parts) == 2:
                        value = parts[1].strip().strip('"').strip("'")
                        if value:
                            return value
    except OSError:
        pass
    return "0.0.0"


TOOLS = [
    {
        "name": "journal_add",
        "description": "Append one sealed entry to a vault's append-only journal; the hash chain is verified before and after the append.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "description": "absolute path of the vault folder"},
                "title": {"type": "string", "description": "the title of the entry"},
                "fields": {"type": "object", "description": "the entry fields: every key maps to a string value",
                           "additionalProperties": {"type": "string"}},
            },
            "required": ["vault", "title", "fields"],
        },
    },
    {
        "name": "lint_brief",
        "description": "Check a delegation brief against the brief rules: says ACCEPTED or lists the rules it fails.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "brief": {"type": "string", "description": "the brief text"},
                "trust": {"type": "string", "description": "optional trust ceiling: private or untrusted_third_party"},
            },
            "required": ["brief"],
        },
    },
    {
        "name": "resume",
        "description": "Print the text that starts a new session: where the project stands, open todos, recent decisions.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "vault": {"type": "string", "description": "absolute path of the vault folder"},
                "entries": {"type": "integer", "description": "optional number of recent journal entries to show"},
            },
            "required": ["vault"],
        },
    },
    {
        "name": "delegate",
        "description": "Send a checked brief to a cheaper model and write the answer to the out file: the answer is written unverified, check it yourself in your shell; the delegation receipt is written by the delegate tool itself, never by this server.",
        "inputSchema": {
            "type": "object",
            "properties": {
                "role": {"type": "string", "description": "the role named in models.json"},
                "brief": {"type": "string", "description": "the brief text"},
                "out": {"type": "string", "description": "absolute path, inside the project folder, of the file the answer lands in"},
            },
            "required": ["role", "brief", "out"],
        },
    },
]


def _run(cmd, timeout):
    """Launch one FrugalFlow tool with this server's own environment. Returns (is_error, text)."""
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, input="", timeout=timeout)
    except subprocess.TimeoutExpired:
        return True, "TIMEOUT: the tool ran longer than " + str(timeout) + " seconds and was stopped"
    except OSError as error:
        return True, "LAUNCH FAILED: " + str(error)
    text = proc.stdout
    if proc.stderr:
        text = (text + "\n" + proc.stderr) if text else proc.stderr
    return proc.returncode != 0, text


def _tool_journal_add(args):
    vault = args.get("vault")
    title = args.get("title")
    fields = args.get("fields")
    if not isinstance(vault, str) or not isinstance(title, str) or not isinstance(fields, dict):
        return True, "bad arguments: vault and title (strings) and fields (object of strings) are required"
    if not os.path.isabs(vault):
        return True, "path must be absolute"
    cmd = [sys.executable, "-I", os.path.join(BIN, "journal_add.py"), "--vault", vault, "--title", title]
    for key in sorted(fields):
        value = fields[key]
        if not isinstance(key, str) or not isinstance(value, str):
            return True, "bad arguments: fields must map strings to strings"
        cmd += ["--field", key + "=" + value]
    return _run(cmd, 60)


def _tool_lint_brief(args):
    brief = args.get("brief")
    trust = args.get("trust")
    if not isinstance(brief, str):
        return True, "bad arguments: brief (string) is required"
    if trust is not None and not isinstance(trust, str):
        return True, "bad arguments: trust must be a string"
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "brief.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(brief)
        cmd = [sys.executable, "-I", os.path.join(BIN, "brief_check.py"), "--brief", path]
        if trust is not None:
            cmd += ["--trust", trust]
        return _run(cmd, 60)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _tool_resume(args):
    vault = args.get("vault")
    entries = args.get("entries")
    if not isinstance(vault, str):
        return True, "bad arguments: vault (string) is required"
    if not os.path.isabs(vault):
        return True, "path must be absolute"
    if entries is not None and (isinstance(entries, bool) or not isinstance(entries, int)):
        return True, "bad arguments: entries must be an integer"
    cmd = [sys.executable, "-I", os.path.join(BIN, "resume_cmd.py"), "--vault", vault]
    if entries is not None:
        cmd += ["--entries", str(entries)]
    return _run(cmd, 60)


def _frugalflow_home():
    """The FrugalFlow home, resolved: FRUGALFLOW_HOME, else ~/.frugalflow."""
    home = os.environ.get("FRUGALFLOW_HOME") or os.path.join(os.path.expanduser("~"), ".frugalflow")
    return os.path.realpath(home)


def _collect_abs(node, found):
    """Every absolute-path string inside a JSON value, resolved and added to found."""
    if isinstance(node, str):
        if os.path.isabs(node):
            found.add(os.path.realpath(node))
    elif isinstance(node, list):
        for item in node:
            _collect_abs(item, found)
    elif isinstance(node, dict):
        for value in node.values():
            _collect_abs(value, found)


def _harden_protected():
    """The protected paths listed in <home>/harden.json, resolved; empty when absent or unreadable."""
    path = os.path.join(_frugalflow_home(), "harden.json")
    found = set()
    try:
        with open(path, "r", encoding="utf-8") as handle:
            _collect_abs(json.load(handle), found)
    except (OSError, ValueError):
        return set()
    return found


def _under(path, root):
    """True when path is root itself or sits under it (both already resolved)."""
    return path == root or path.startswith(root + os.sep)


def _check_out(out):
    """Why this out path is refused, or None when it is allowed. The server runs outside
    the sandbox, so out may only be a plain file inside the project folder: never the
    FrugalFlow home, never a git hook, a settings file, a vault path or a harden-protected path."""
    real = os.path.realpath(out)
    project_dir = os.environ.get("CLAUDE_PROJECT_DIR")
    root = os.path.realpath(project_dir) if project_dir else WORK_ROOT
    if not _under(real, root):
        return "out is not allowed: not under the project folder " + root
    home = _frugalflow_home()
    if _under(real, home):
        return "out is not allowed: under FRUGALFLOW_HOME " + home
    for component in real.split(os.sep):
        if component in PROTECTED_COMPONENTS:
            return "out is not allowed: protected path component: " + component
    name = os.path.basename(real)
    if name in PROTECTED_NAMES:
        return "out is not allowed: protected file name: " + name
    for protected in sorted(_harden_protected()):
        if _under(real, protected):
            return "out is not allowed: covered by the protected path " + protected + " listed in harden.json"
    return None


def _tool_delegate(args):
    role = args.get("role")
    brief = args.get("brief")
    out = args.get("out")
    if not isinstance(role, str) or not isinstance(brief, str) or not isinstance(out, str):
        return True, "bad arguments: role, brief and out (strings) are required"
    if "verify" in args:
        return True, ("verify is not accepted over MCP: run your check in your own shell, "
                      "inside the sandbox, on the file delegate wrote")
    if not os.path.isabs(out):
        return True, "path must be absolute"
    reason = _check_out(out)
    if reason is not None:
        return True, reason
    tmp = tempfile.mkdtemp()
    try:
        path = os.path.join(tmp, "brief.md")
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(brief)
        cmd = [sys.executable, "-I", os.path.join(BIN, "delegate.py"),
               "--role", role, "--file", path, "--out", out]
        return _run(cmd, 1800)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


HANDLERS = {
    "journal_add": _tool_journal_add,
    "lint_brief": _tool_lint_brief,
    "resume": _tool_resume,
    "delegate": _tool_delegate,
}


def _send(payload):
    sys.stdout.write(json.dumps(payload) + "\n")
    sys.stdout.flush()


def _reply(req_id, result):
    _send({"jsonrpc": "2.0", "id": req_id, "result": result})


def _fail(req_id, code, message):
    _send({"jsonrpc": "2.0", "id": req_id, "error": {"code": code, "message": message}})


def _handle(message):
    """One message in, one response out — or none for a notification."""
    req_id = message.get("id")
    method = message.get("method")
    params = message.get("params")
    if not isinstance(params, dict):
        params = {}
    if method == "initialize":
        protocol = params.get("protocolVersion")
        if not isinstance(protocol, str) or not protocol:
            protocol = DEFAULT_PROTOCOL
        _reply(req_id, {
            "protocolVersion": protocol,
            "capabilities": {"tools": {}},
            "serverInfo": {"name": "frugalflow", "version": server_version()},
        })
    elif method == "notifications/initialized":
        return  # a notification: no answer
    elif method == "tools/list":
        _reply(req_id, {"tools": TOOLS})
    elif method == "tools/call":
        name = params.get("name")
        arguments = params.get("arguments")
        if not isinstance(arguments, dict):
            arguments = {}
        handler = HANDLERS.get(name)
        if handler is None:
            _reply(req_id, {"content": [{"type": "text", "text": "unknown tool: " + str(name)}], "isError": True})
            return
        is_error, text = handler(arguments)
        _reply(req_id, {"content": [{"type": "text", "text": text}], "isError": bool(is_error)})
    elif method == "ping":
        _reply(req_id, {})
    elif req_id is None:
        return  # an unknown notification: nothing to answer
    else:
        _fail(req_id, -32601, "unknown method: " + str(method))


def serve():
    """Read one JSON message per line until stdin closes, then stop clean."""
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            message = json.loads(line)
        except ValueError:
            _fail(None, -32700, "invalid JSON: the line is not a JSON-RPC message")
            continue
        if not isinstance(message, dict):
            _fail(None, -32700, "invalid JSON: the message is not an object")
            continue
        try:
            _handle(message)
        except Exception as error:
            # one broken message must not take the server down
            sys.stderr.write("mcp_server: " + type(error).__name__ + ": " + str(error) + "\n")
            if message.get("id") is not None:
                _fail(message.get("id"), -32603, "internal error: " + str(error))
    return 0


def run_autotest():
    """Proof: launch this server as a subprocess, drive it with JSON-RPC lines, check the answers, the sealed journal and the refusals."""
    tmp = tempfile.mkdtemp()
    try:
        home = os.path.join(tmp, "home")
        ff = os.path.join(tmp, "ff")
        os.makedirs(home, exist_ok=True)
        os.makedirs(ff, exist_ok=True)
        env = {k: v for k, v in os.environ.items() if k != "CLAUDECODE" and not k.startswith("GIT_")}
        env["HOME"] = home
        env["FRUGALFLOW_HOME"] = ff

        def tool(name, *args):
            return subprocess.run([sys.executable, "-I", os.path.join(BIN, name)] + list(args),
                                  capture_output=True, text=True, input="", env=env, timeout=60)

        created = tool("vault_new.py", "--root", os.path.join(tmp, "proj"), "--name", "demo")
        vault = os.path.join(tmp, "proj", "vault")
        log_path = os.path.join(vault, "log.md")
        size_before = os.path.getsize(log_path) if os.path.isfile(log_path) else 0

        messages = [
            {"jsonrpc": "2.0", "id": 1, "method": "initialize",
             "params": {"protocolVersion": DEFAULT_PROTOCOL, "capabilities": {},
                        "clientInfo": {"name": "autotest", "version": "1"}}},
            {"jsonrpc": "2.0", "method": "notifications/initialized"},
            {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
            {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "journal_add",
             "arguments": {"vault": vault, "title": "Autotest entry",
                           "fields": {"Decision": "keep the chain", "Why": "the server must write it"}}}},
            {"jsonrpc": "2.0", "id": 4, "method": "tools/call", "params": {"name": "lint_brief",
             "arguments": {"brief": ""}}},
            "not json at all",
            {"jsonrpc": "2.0", "id": 5, "method": "ping"},
        ]

        proc = subprocess.Popen([sys.executable, "-I", os.path.abspath(__file__)],
                                stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True, env=env)
        for message in messages:
            proc.stdin.write((message if isinstance(message, str) else json.dumps(message)) + "\n")
        proc.stdin.close()
        stdout = proc.stdout.read()
        stderr = proc.stderr.read()
        exit_code = proc.wait(timeout=60)

        answers = {}
        for line in stdout.splitlines():
            try:
                obj = json.loads(line)
            except ValueError:
                continue
            if isinstance(obj, dict) and "id" in obj:
                answers[obj["id"] if obj["id"] is not None else "null"] = obj

        results = []

        # 1: initialize
        try:
            info = answers[1]["result"]
            ok = (info["serverInfo"]["name"] == "frugalflow"
                  and "tools" in info["capabilities"]
                  and info["protocolVersion"] == DEFAULT_PROTOCOL)
            got = "name=" + repr(info["serverInfo"]["name"]) + " capabilities=" + repr(sorted(info["capabilities"])) \
                  + " protocol=" + repr(info["protocolVersion"])
        except Exception as error:
            ok, got = False, "no initialize answer: " + str(error)
        results.append((1, ok, "serverInfo frugalflow, capabilities tools, protocol echoed", got))

        # 2: tools/list
        try:
            tools = answers[2]["result"]["tools"]
            names = sorted(t["name"] for t in tools)
            ok = names == ["delegate", "journal_add", "lint_brief", "resume"]
            got = "names=" + repr(names)
        except Exception as error:
            ok, got = False, "no tools/list answer: " + str(error)
        results.append((2, ok, "four tools delegate journal_add lint_brief resume", got))

        # 3: journal_add writes a sealed entry
        try:
            is_error = answers[3]["result"]["isError"]
            grew = os.path.getsize(log_path) > size_before
            checked = tool("vault_check.py", "--vault", vault)
            ok = (created.returncode == 0 and is_error is False and grew and checked.returncode == 0
                  and exit_code == 0)
            got = "isError=" + repr(is_error) + " log_grew=" + str(grew) \
                  + " vault_check=" + str(checked.returncode) + " server_exit=" + str(exit_code)
        except Exception as error:
            ok, got = False, "no journal_add answer: " + str(error)
        results.append((3, ok, "isError False, log.md grows, vault_check exits 0, server exits 0", got))

        # 4: lint_brief refuses an empty brief
        try:
            is_error = answers[4]["result"]["isError"]
            ok = is_error is True
            got = "isError=" + repr(is_error)
        except Exception as error:
            ok, got = False, "no lint_brief answer: " + str(error)
        results.append((4, ok, "empty brief: isError True", got))

        # 5: a non-JSON line is refused, the server keeps going
        try:
            parse_ok = answers["null"]["error"]["code"] == -32700
            ping_ok = answers[5]["result"] == {}
            ok = parse_ok and ping_ok
            got = "parse_code=" + repr(answers["null"]["error"]["code"]) + " ping=" + repr(answers[5]["result"])
        except Exception as error:
            ok, got = False, "no parse answer or no ping answer: " + str(error)
        results.append((5, ok, "error -32700 with id null, then ping answers {}", got))

        if stderr.strip():
            sys.stderr.write(stderr)

        all_pass = True
        for num, ok, expected, got in results:
            if ok:
                print("PASS {} expected {} | got {}".format(num, expected, got))
            else:
                print("FAIL {} expected {} | got {}".format(num, expected, got))
                all_pass = False
        return 0 if all_pass else 1
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    args = sys.argv[1:]
    if args == ["--notice"]:
        sys.stdout.write(NOTICE)
        return 0
    if args == ["--autotest"]:
        return run_autotest()
    if args:
        sys.stdout.write(USAGE)
        return 2
    return serve()


if __name__ == "__main__":
    import exit_log
    exit_log.run(main, "mcp_server", sys.argv[1:])
