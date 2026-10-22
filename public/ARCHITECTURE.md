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
