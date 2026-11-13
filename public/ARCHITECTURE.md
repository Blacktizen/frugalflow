# Architecture

Two things are fixed here: **how a deployment is laid out**, and **how it is configured**.
Every tool fits these two shapes.

## 1. Deployment layout

```
frugalflow/
  bin/                 executable tools, one job each
  config/              JSON only - no code, no secrets
    *.example.json       the user files, as examples to copy (see SCHEMA_JSON.md)
  hooks/               the git hook templates; install_hooks.py copies them into .git/hooks
  tests/               one end-to-end suite per feature: e2e_<feature>.py
    bite/                one bite receipt per suite, written by bite.py only
  SCHEMA_JSON.md       the configuration contract
  NOTICE.md            the notice contract every tool follows
  ARCHITECTURE.md      this file
```

The user's own settings do not live in the repository: they live in `~/.frugalflow/`
(`models.json`, `preferences.json`), plus an optional `.frugalflow.json` at a project root.

Rules:

- **No secret ever lands in `config/`.** API keys are read from the OS keychain or from the
  environment, and the config file stores only the *name* of the entry to look up.
- **No tool writes into another tool's directory.** A tool reads config, reads the disk,
  prints, and exits with a code.
- **State is never stored.** Anything that could be recomputed from the disk is recomputed.

## 2. Configuration: JSON, validated, layered

Described key by key in `SCHEMA_JSON.md`. Three files, never one:

| File | Holds | Where |
|---|---|---|
| `models.json` | the models, the delegation **layers** (as data), the **roles** | `~/.frugalflow/` |
| `preferences.json` | the user's ceilings | `~/.frugalflow/` |
| `.frugalflow.json` | per-project settings, which may only **tighten** | project root |

A tool that resolves a value must be able to say *where it came from*: `config_check.py`
prints every effective ceiling with its source. A config that cannot be validated is an
error, never a guess, and so is an unknown trust level. **A default that guesses manufactures
a false red.** A project file that loosens a ceiling is refused, never clamped.

The validation is code, not JSON Schema files: `config_rules.py`, `layers.py` and
`ceilings.py` are pure modules, each with its own self-test, and `config_check.py` runs them.

## 3. End-to-end tests, one suite per feature

Each feature ships `tests/e2e_<feature>.py`, which:

1. builds a **fresh temporary scene** on disk, from fixtures written in the file itself;
2. runs the feature's real entry point as a **subprocess**, with real command-line arguments;
3. reads the **real exit code** and the real output;
4. prints one `PASS` or `FAIL` line per test, with expected and obtained;
5. exits 0 only if every test passed.

Two rules make the suite worth running:

- **It must move a number.** A test that asserts a constant proves nothing. Each suite
  changes an input (a file, a setting, a log line) and asserts that the printed result changes with it.
- **It must be proven to bite.** Before a suite is trusted, the code it covers is deliberately
  broken and the suite must go red. A green light that was never shown red is not a check.

The proof is run by `bin/bite.py`, which alone writes the receipt in `tests/bite/`. Nothing
stops a hand-typed receipt, so none should ever be typed.

## Layers

The repository holds three layers. Only the first two are installed.

- **Core** — the memory, the journal, the reading gate, resume, close, the guards, init, doctor, and the plugin and MCP launchers. These run where the operator works and judge without asking a model.
- **Delegation** — what prepares, sends, checks and accounts for a task sent to a model: the delegate, the brief checker and its rules, the model notes, the token receipts, and the anonymization applied before a send.
- **Workshop** — `dev/bin/`, in the repository only, never installed: the release and bench tools. A workshop tool reads the tree and runs the suites; nothing under `bin/` imports or launches one.

Every file of `bin/` belongs to one layer; a file that serves both belongs to core.

**Core**

- entry point and lifecycle: `frugalflow.py`, `init_cmd.py`, `onboard_cmd.py`, `onboard_choice.py`, `setup_cmd.py`, `setup_manifest.py`, `uninstall_cmd.py`, `doctor_cmd.py`, `config_cmd.py`, `config_check.py`, `config_rules.py`, `ceilings.py`, `layers.py`, `example_defaults.py`, `env_detect.py`, `engine_lock.py`, `harden_cmd.py`, `claudecode_check.py`, `claude_block.py`, `settings_merge.py`, `banner_merge.py`, `statusline.py`, `install_hooks.py`
- launchers and hooks: `launcher.py`, `plugin_hook.py`, `guard_hook.py`, `mcp_server.py`, `session_banner.py`
- vault and handoff: `vault_new.py`, `vault_check.py`, `page_rules.py`, `git_vault_rules.py`, `chain_rules.py`, `commit_claims.py`, `resume_cmd.py`, `close_cmd.py`
- journal and session log: `journal_add.py`, `journal_guard.py`, `journal_log.py`, `journal_read_proof.py`, `journal_rules.py`, `session_log.py`, `session_event.py`, `session_chain.py`, `session_note.py`, `session_digest.py`, `session_summary.py`, `notes_rules.py`, `r1_guard.py`, `r1_rules.py`, `exit_log.py`, `block_log.py`, `block_rules.py`
- reading gate: `reading_gate.py`, `read_intake.py`, `read_quarantine.py`, `guard_checks.py`, `guard_rules.py`
- guards over commands and code: `shell_rules.py`, `shell_split.py`, `shell_targets.py`, `shell_tokens.py`, `shell_vars.py`, `shell_quotes.py`, `quote_mask.py`, `subshells.py`, `chain_vars.py`, `safe_vars.py`, `command_head.py`, `bounded_output.py`, `awk_calls.py`, `digest_rules.py`, `inline_writes.py`, `python_file_import.py`, `python_literal_roles.py`, `python_read_proof.py`, `python_write_proof.py`, `python_shell_calls.py`, `restore_rules.py`, `settings_cli_guard.py`, `verify_extra.py`, `scan_cmd.py`, `scan_files.py`
- the notice contract and the refusal loop: `notice_rules.py`, `refusal_loop.py`, `bite.py`

**Delegation**

- the send: `delegate.py`, `delegate_call.py`, `delegate_prep.py`, `card_check.py`, `card_rules.py`, `bench_check.py`, `bench_rules.py`
- the brief: `brief_check.py`, `brief_rules.py`, `lint_cmd.py`
- limits and models: `limits_files.py`, `run_limits.py`, `budget_rules.py`, `eta_rules.py`, `ledger_rules.py`, `sampling_check.py`, `sampling_rules.py`, `answer_rules.py`, `model_notes.py`
- the check of produced work: `verify_rules.py`, `verify_worktree.py`, `fidelity.py`
- anonymization before a send: `send_rules.py`, `share_rules.py`, `anon_check.py`, `anon_core.py`, `anon_rules.py`, `anon_review.py`, `anon_review_rules.py`
- receipts: `usage_report.py`, `usage_rules.py`, `receipt_rules.py`, `session_share.py`, `report_cmd.py`, `report_rules.py`

**Workshop** (`dev/bin/`, not installed)

- `release_check.py`, `lang_check.py`, `notice_check.py`, `demo_record.py`, `demo_svg.py`, `import_betterleaks.py`, `bench_run.py`, `bench_report.py`, `brief_bench.py`, `shell_bench.py`
