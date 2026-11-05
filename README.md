# FrugalFlow

[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#quick-install)

**The AI coding assistant that never loses the thread of your project.**

FrugalFlow gives Claude Code a structured memory per project, makes it reread that memory before it acts, and records every decision the moment it is made. It hands bulky work to cheaper models with briefs that get better with every mistake, and it keeps your private data out of any third-party model.

Frugal where it matters: in the intelligence of the project. An assistant that remembers why things are the way they are does not write useless code, does not reopen settled choices, and does not break what already works.

![Terminal demo: install, scan finds a planted key, setup --yes, doctor is green](docs/demo.svg)

```
pipx install git+https://github.com/Blacktizen/frugalflow
frugalflow new-project myapp --root ~/projects   # the vault, the hooks, the gates: your project now has a memory
frugalflow resume                                # tomorrow: pick up exactly where you stopped
```

## Why FrugalFlow

### 1. A memory built like a wiki, not a chat log
Every project gets a vault on the *LLM Wiki* pattern: raw sources, a wiki of linked pages, a schema that says how to keep it. Entry is always the same path: `overview`, then `index`, then two or three targeted pages, never everything. The closing pass (`vault_check`) keeps it healthy every time: no orphan page, no dead link, a todo always present. Close in as many passes as the session needs: when the closing is done, nothing falls through.

### 2. Rereading is not a suggestion: it is enforced
The reading gate refuses any write until the project's bearing lines (its rules, its warnings, its validated methods) have gone through the assistant's context. It is a check, not an instruction: the assistant cannot forget it. The rule that matters is in front of it every time it acts.

### 3. Every decision is written when it is made
After any action that changes state (a commit, a merge, a setting, a measurement that settles a question), a sealed journal entry must follow, or the end of the turn is blocked (`r1_guard`). The journal is append-only and hash-chained: an entry is superseded, never rewritten. Nothing is reconstructed from memory at the end of the day.

### 4. The next session starts where the last one stopped
`frugalflow resume` builds the handoff from the vault and the sealed journal. It is generated, never hand-copied, so it cannot drift from what really happened.

### 5. Delegation that gets better with every mistake
Bulky work goes to a local or cheaper model. A failed delegation almost always comes from the brief, not from the model, so every brief is checked before it is sent (`brief_check`): each rule it breaks is named, with how to fix it. Every first attempt that fails adds its rule, so the same mistake is never paid twice. Each tool carries its own notice, with the dated pitfalls it has met, and every new rule must pass the whole bench with no regression. Per-model notes keep what each model needs, each with its proof (`model_notes`).

### 6. Nothing is accepted on a model's word
"Done" means nothing until an independent check says so (`delegate.py --verify`). A test only counts once it has been seen red, then green: `bite` breaks the code on purpose to prove the suite really fails. Inside the hook, a check that crashes or doubts refuses, with a "To fix:" line, never a silent pass.

### 7. Your private data stays out of third-party models
Before anything goes to a hosted model, including models hosted abroad, `anon_check` refuses names, personal paths, addresses and secrets, and `send_rules` decides what may leave. `frugalflow scan` finds secrets in a folder or a repo, with no model and no setup, and works as a pre-commit hook or a CI step.

### 8. A refusal log per tool: a built-in progress loop
Every tool logs its own refusals. Each new refusal becomes a todo line, then a bench case; a wrong refusal becomes a fix that must keep every other case green (`refusal_loop`). A commit waits while a false refusal is still open. The tools improve from their own use, every day.

### 9. Smooth, and it guides you
FrugalFlow works in the background through Claude Code hooks. When it stops something, it says why and what to run next. `doctor` is the health check: one line per check, in one command. `frugalflow config` shows every setting and what it means. The settings are yours: you change them in your own terminal (`config set`, `on`, `off`, `mode`), and the assistant is refused if it tries, in every mode.

## What the guards are, and what they are not

FrugalFlow's guards are a safety net against the mistakes and shortcuts of a cooperative assistant: forgetting the project's rules, skipping a delegation, writing over a log, turning a setting off, sending private data to a third party. They refuse at the moment of the gesture, and every refusal says what to do instead.

They are not a security boundary against a hostile agent. The hooks run as the same user as the assistant: a script the assistant writes and then runs can do what that user can do, and no rule on the text of a command can see inside it. To contain an agent that actively tries to get around the rules, run it in an isolated environment (another user, a container) where FrugalFlow's files are read-only to it. [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md) lists what is covered and what is not.

## Measured

| What FrugalFlow does | Bench | Result |
|---|---|---|
| Keeps the project's conventions across fresh sessions | 5 fresh-context sessions, model that forgets | **36 of 40 modules** keep the conventions, against **0 of 40** without FrugalFlow |
| Stops a broken brief before it runs | 45 sound and faulty briefs | first-attempt success **24.4 % → 97.8 %**, 0 false refusals |
| Catches a false "all green" | 30 pre-registered tasks, 4 repetitions | **every** false announcement caught, 0 wrong result delivered |
| Stops leaks before they leave | 80 planted leaks, 40 decoys | leaks delivered: **100 % → 16.2 %**, 0 false positives |
| No silent edits | 712 lines | typography altered: **69.9 % → 0 %** |

Every figure, its protocol and its raw runs: [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md).

## Built with FrugalFlow

FrugalFlow was built with its own method, and its method runs every day on long-lived production projects, a web application and a mobile application among them. Counted by script from its own files, over 11 weeks: **956** sealed journal entries, **201** numbered todos, **745** commits through its own gates, **224** sessions resumed from a written handoff.

More than 100 small tools, each with `--notice` (its contract and pitfalls) and `--autotest`; a test suite that runs in a fresh clone with no key and no model, in CI on Python 3.11 and 3.12; standard library only, no dependency.

## Quick install

Three commands, about two minutes. Python 3.11 or newer is the only prerequisite.

```
pipx install git+https://github.com/Blacktizen/frugalflow    # works today, no PyPI needed
frugalflow scan .                                              # step 2: the door in, no model needed
frugalflow setup                                               # step 3: guided, ends with doctor
```

Without pipx: `python3 -m venv ~/.ff && ~/.ff/bin/pip install git+https://github.com/Blacktizen/frugalflow`, then run `~/.ff/bin/frugalflow`. Coming soon: `pipx install frugalflow` from PyPI (soon, not published yet).

**Start with `scan`.** `frugalflow scan [PATH]` looks for secrets and private data (API keys, private key blocks, passwords in clear, personal paths, e-mail and IP addresses) in a folder or a git repo. It needs no model, no key and no setup. It prints one line per leak with file, line, type and label, never the value found. Exit code 0 means clean, **12 means a leak was found**, so it works as a pre-commit hook or a CI step:

```
frugalflow scan .                 # a folder or a repo (git-aware: it respects .gitignore)
frugalflow scan --staged .        # only what is staged: the pre-commit form
frugalflow scan --quiet .         # one summary line
```

Pre-commit hook (`.git/hooks/pre-commit`, then `chmod +x`): `exec frugalflow scan --staged "$(git rev-parse --show-toplevel)"`. CI step: `frugalflow scan .`. Your own names and patterns go in `~/.frugalflow/anonymization.json`, or pass `--rules FILE`.

**Then `setup`.** `frugalflow setup` detects Ollama (:11434), LM Studio (:1234), a typed OpenAI-compatible endpoint (`--endpoint URL`) and any `*_API_KEY` variable (only its name is stored, never its value), asks which one to use, copies every file it is about to touch into `~/.frugalflow/setup-backups`, writes the configuration, and finishes with `doctor`. `frugalflow setup --yes` takes the first engine found without asking (for CI). `frugalflow uninstall` puts every file back as it was, byte for byte; a file you edited since is kept and only the FrugalFlow block is cut out of it. The older walk over the model layers is now `frugalflow setup --layers`.

**From a clone.** Everything also runs from a checkout, with the same arguments, as `python3 public/bin/frugalflow.py COMMAND`, and `python3 public/tests/run_all.py` runs the tests.

`doctor` prints one `OK`, `INFO` or `WARN` line per check; a `WARN` saying the engine does not answer is expected until your model server runs, and nothing else needs it for the tests. `init` starts in `observe` mode: rules watch and log but **do not block anything**. `doctor` shows the effective guard mode and warns while it is `observe`; `frugalflow mode active` turns enforcement on. Start a project with `frugalflow new-project demo --root ~/projects`. See [`public/QUICKSTART.md`](public/QUICKSTART.md).

`run_all.py` exits 1 if any item failed, after running all (`--fail-fast` stops at the first). It judges only exit codes, never the words a test prints. Verify one tool with `python3 public/bin/<tool>.py --autotest`.

To check a tree before sharing it, use a clean copy with no `.git` and no cache files:

```
git clone . ../ff-check && rm -rf ../ff-check/.git
python3 public/bin/release_check.py check --tree ../ff-check --skip-e2e
```

The last line is `RELEASE READY` when every check passes.

## Join in

FrugalFlow gets better the way it was built: from other people's real cases. You do not need to write much code to help.

- **Report a false refusal.** A guard that blocked something it should not have is the most valuable report you can send. Copy the refused line, say what you were doing and what the right answer was.
- **Add a case to a bench.** A new brief, a new disguised command, a new leak pattern, a task where delegation did or did not pay off. Red before the fix, green after.
- **Pick a good first issue.** Look for the `good first issue` label in the issue tracker; small rules, notes and docs are a gentle start.
- **Propose a brief rule or record a model pitfall.** Both are described, with the proof they need, in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Star the repository** if the method is useful to you, so others can find it.

Every change keeps the tests green and adds a bench case when a refusal was wrong.

## Documentation

- [`docs/METHOD.md`](docs/METHOD.md): the principles behind the tools, with neutral examples
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md): every figure, its scope, and how to replay it
- [`docs/PIPELINE.md`](docs/PIPELINE.md): how a task flows through the tools, with a diagram
- [`public/QUICKSTART.md`](public/QUICKSTART.md)
- [`public/ARCHITECTURE.md`](public/ARCHITECTURE.md)
- [`public/SCHEMA_JSON.md`](public/SCHEMA_JSON.md)
- [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md)
- [`public/NOTICE.md`](public/NOTICE.md)
- [`public/CREDITS.md`](public/CREDITS.md)
- [`public/bench/README.md`](public/bench/README.md)
- [`public/bench/multisession/README.md`](public/bench/multisession/README.md): the multi-session bench
- [`public/examples/brief_template.md`](public/examples/brief_template.md)

## License

MIT. See [`LICENSE`](LICENSE). Reused work is credited in [`public/CREDITS.md`](public/CREDITS.md).
