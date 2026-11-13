# Isolated mode

[← Back to the README](../README.md)

`frugalflow harden` turns on the isolated mode: Claude Code's native sandbox around Bash, and read-only protection of the FrugalFlow settings and journals against the assistant. `frugalflow doctor` then prints `isolation: isolated` instead of `isolation: cooperative`.

## What harden does

It writes into `~/.claude/settings.json` (or the folder given with `--claude-dir`):

- `sandbox.enabled: true`, `sandbox.allowUnsandboxedCommands: false` (no escape from the sandbox), `sandbox.failIfUnavailable: true` (Bash fails when the sandbox cannot start, instead of running unsandboxed).
- Every protected path into `sandbox.filesystem.denyWrite`: the FrugalFlow home, the two Claude Code settings files, and for each `--project DIR`, `DIR/vault/log.md`, `DIR/.claude/settings.json` and `DIR/.claude/settings.local.json`.
- A `permissions.deny` rule `Edit(//path)` for each protected file, `Edit(//home/**)` for the home: the file tools (Edit, Write, NotebookEdit) are refused on them too, not just Bash.

Existing keys and rules are never removed, reordered or modified. The original settings.json is copied to a dated `.before-frugalflow-` backup first, and the exact list of additions is recorded in `<home>/harden.json`. A second run that changes nothing writes nothing and prints `ALREADY HARDENED`. Like `init`, harden refuses to run from inside a Claude Code session without a terminal: run it yourself. Restart Claude Code to apply.

## What it does not do

- The native sandbox covers **Bash only**. The file tools are protected by the `permissions.deny` rules harden writes, not by the sandbox.
- Hooks and local MCP servers run **outside** the sandbox. The MCP server below uses exactly that: it is FrugalFlow's own writing path, not something the sandbox enforces.
- The isolated mode is optional and never demanded: the doctor's isolation line is an INFO, never a FAIL.
- This design has not yet been reviewed by an external auditor.
- Native Windows is unsupported: the Claude Code sandbox needs macOS, Linux or WSL2. `harden` says so and exits; `doctor` prints `isolation: unsupported on native Windows`.

## Receipts outside the sandbox

In isolated mode, the assistant's Bash runs in the native sandbox: it can no longer write the vault journal or the delegation receipts — the protected paths are read-only to it. That is the point, but it leaves a problem: the journal entries and receipts still have to be written, and an assistant that cannot write them could also be an assistant that claims to have written them.

`public/bin/mcp_server.py` is a local MCP server (JSON-RPC 2.0 over stdio, standard library only) that offers four tools: `journal_add`, `lint_brief`, `resume` and `delegate`. Hooks and local MCP servers run **outside** the sandbox, with the user's rights, so the server can do what the sandboxed Bash cannot: it launches the real tools (`journal_add.py`, `brief_check.py`, `resume_cmd.py`, `delegate.py`) and returns their output. The server writes nothing by itself — a journal entry exists only if `journal_add.py` verified the hash chain, a delegation receipt only if `delegate.py` wrote it. The assistant calls the tools; it cannot forge their result, because the verification happens in a process it does not control.

The plugin registers the server through the repository's `.mcp.json`:

```json
{"mcpServers": {"frugalflow": {"command": "python3",
  "args": ["-I", "${CLAUDE_PLUGIN_ROOT}/public/bin/mcp_server.py"]}}}
```

`frugalflow harden` also protects the delegation logs named by `<home>/guard.json` (resolved inside the home): a log kept outside the home folder gets its own `denyWrite` entry and `Edit` rule, so the assistant cannot append a receipt by hand either.

What this changes: in isolated mode the writing path is a tool call the assistant makes, not a shell command it runs. What remains to be proven: an adverse review (roadmap C3) must attack this path — a forged `tools/call`, a tampered models file, a receipt written through a different tool — before the claim "a receipt cannot be forged" is worth printing anywhere else.

## Taking it back

```
frugalflow harden --remove
```

`--remove` rereads `<home>/harden.json` and removes exactly what was added: the recorded list entries, the three sandbox flags (restored to their previous values, or removed when harden created them), the empty containers. Settings that existed before harden come back identical, and `harden.json` is deleted. The dated backups stay, in case you want to compare.
