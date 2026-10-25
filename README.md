# FrugalFlow

[![tests](https://github.com/Blacktizen/frugalflow/actions/workflows/tests.yml/badge.svg)](https://github.com/Blacktizen/frugalflow/actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](#quick-install)
[![Status: beta](https://img.shields.io/badge/status-beta-orange.svg)](#status-beta-and-improving-in-the-open)

**Let your AI coding assistant delegate the grunt work to cheaper or local models, under mechanical control, with memory and a paper trail.**

AI coding agents are remarkable, and they have four habits that hurt: they bill every token at the premium rate, even for boilerplate; they say "all green" without proof; they let secrets and personal data slip into what they publish; and they forget everything between one session and the next.

FrugalFlow is a toolkit around Claude Code that attacks those four problems together. The paid assistant keeps the part that needs judgment. Bulky mechanical work goes to a cheaper or local model. Nothing that model produces is accepted on its own word: an independent check decides, guards refuse what must not happen, a hash-chained journal records what did, and a project vault remembers it all for the next session.

Python 3.11+, standard library only, no package to install.

## Why we built it

We kept delegating work to cheaper models and kept paying for it in other ways: briefs that were quietly wrong, "done" announcements that were not true, a private name in a commit, a lesson learned on Tuesday that was gone by Thursday. Each time, the fix was a small mechanical check, and the checks piled up into a method.

The goals of the project:

- **Delegate safely.** Cheaper models do the bulky work; a paid check decides what is accepted.
- **Trust nothing unproven.** A claim of success needs an oracle outside the model that made it.
- **Keep private things private.** Names, paths, addresses and secrets are caught before anything leaves your machine.
- **Remember.** Decisions, refusals and lessons live in a vault and a tamper-evident journal, not in a chat window.
- **Measure in the open.** Every figure comes with its bench, its limits, and its raw runs, the disappointing ones included.

The way of working behind it is written down in [`docs/METHOD.md`](docs/METHOD.md). It is the part we think is most reusable, with or without our tools.

## What you get

More than 100 small Python tools in `public/bin/`, each carrying `--notice` (its contract) and `--autotest`.

- **Guards that fail closed.** `guard_hook.py` and `guard_rules.py` refuse a code write that cannot point to a recent successful delegation receipt. A crashed check or any doubt means refusal, with a "To fix:" line, never a silent pass. `bite.py` breaks code on purpose to prove a suite really goes red.
- **An external oracle.** `delegate.py --verify` retries until an independent check passes and never writes an unchecked attempt to the target. The model saying "green" is never enough.
- **Anonymization before publication.** `anon_check.py` refuses files carrying a private name, a personal path, an address or a secret. `anon_review.py` has a local model reread each file. `send_rules.py` decides what may leave for a third-party model. `release_check.py` stages the public tree and runs the last checks.
- **Typographic fidelity.** `fidelity.py` stops delegated edits from silently changing quotes, dashes and spacing in lines you never asked to touch.
- **Brief checking.** `brief_check.py` judges the task you are about to send, before it costs anything, and names each broken rule with how to fix it.
- **Project memory in a vault.** `vault_new.py` mounts a vault; `vault_check.py` is the closing pass that checks its invariants; `reading_gate.py` attests a reading only when a restatement repeats every bearing line of the required pages.
- **A hash-chained, append-only journal.** `journal_add.py` appends sealed entries; `session_log.py` seals every session event with the hash of the previous line; `r1_guard.py` blocks the end of a turn while a state-changing command ran with no journal entry after it.
- **The refusal loop.** `refusal_loop.py` turns every new refusal into a todo line and blocks a commit while a tool logs no refusal or the bench holds an unresolved false refusal or hole. A wrong refusal becomes a patch and a bench case.
- **Per-model notes, layered configuration, token receipts.** `model_notes.py` records model quirks; three JSON files that a project may only tighten (`config_check.py`); `usage_report.py` gives a token receipt per session.

The test suite is part of the product: 18 end-to-end suites plus the autotests of every tool (128 items in all) run in a fresh checkout through `public/tests/run_all.py`, and in CI on Python 3.11 and 3.12 with no key and no model.

## What is measured

We would rather show you evidence than adjectives. Four results are measured on pre-written, neutral, synthetic benches, each with its success criterion fixed before the run:

| Tool | What the bench measured | Result on that bench |
|---|---|---|
| `anon_check.py` | Planted leaks that reached delivery | 16.2 % (13/80) with the tool, against 42.5 % (34/80) with a model rereading alone and 100 % with no check; 0 false positives on 40 decoys |
| `fidelity.py` | Lines whose typography drifted | 69.9 % (498/712) without the tool, 0.0 % (0/712) with it |
| `brief_check.py` | First-attempt success of delegated tasks | 24.4 % with a faulty brief, 97.8 % with the corrected one; 0 false refusals on 45 sound briefs |
| External oracle (`delegate.py --verify`) | A model announcing green on failing work, on a pre-registered set of 30 tasks, 4 repetitions | 10.0 % (12/120) of announcements were false; the oracle caught all 12 at the second attempt for 1.11x the tokens, with 0 wrong results delivered |

These are results on the benches' own sets, not guarantees about your data or models; the oracle result sits exactly on its pre-set threshold and we call it fragile. The scope of every figure, the seven benches (including the ones that did **not** prove their case), and the commands to replay them are in [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md).

## Status: beta, and improving in the open

FrugalFlow is **beta**. The guards, the journal and the verification passes are real and tested; the work still ahead is clear, and we would rather list it than hide it.

On small tasks, the token economics are not there yet: on our 20-task bench, FrugalFlow cost more per solved task than the assistant alone (see [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md)). The value today is control, safety and memory; the saving has to be earned and no saving is claimed until a bench shows one.

### Roadmap and where we need help

- **Make delegation pay off.** Find the task sizes and mixes where handing work to a cheaper model beats working alone, and publish the bench either way. Larger real-world tasks are the missing data.
- **Fewer wrong refusals.** Most early briefs were wrong and the guards refused wrongly at times. Every false refusal you report becomes a bench case and a fix.
- **Wider benches.** The benches use small synthetic sets, one local model at a time, with oracles written by a model. More models, more tasks and independently written oracles would make every verdict stronger.
- **Stronger isolation.** There is no system isolation yet: the working folder used to verify a candidate is a temporary folder, not a sandbox (`verify_worktree.py` is named for that reason). A container or OS-level sandbox backend is a welcome contribution. See [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md).
- **More engines.** It has been tested with a local OpenAI-compatible server and Claude Code. Reports and patches for other setups are valuable.

## Quick install

1. **Check the prerequisites.** Python 3.11 or newer, Claude Code, and at least one delegated model: a local OpenAI-compatible server (LM Studio, vLLM, llama.cpp, Ollama) or a remote one with an API key kept in an environment variable (config files only name the variable).
2. **Clone and initialize**, from the folder that holds `public/`:

   ```
   python3 public/bin/frugalflow.py init --lmstudio-url http://localhost:8000
   python3 public/bin/frugalflow.py doctor
   ```

3. **Start a project and run the tests.**

   ```
   python3 public/bin/frugalflow.py new-project demo --root ~/projects
   python3 public/tests/run_all.py
   ```

`doctor` prints one `OK`, `INFO` or `WARN` line per check; a `WARN` saying the engine does not answer is expected until your model server runs, and nothing else needs it for the tests. `init` starts in `observe` mode: rules watch and log but **do not block anything**. `doctor` shows the effective guard mode and warns while it is `observe`; `python3 public/bin/frugalflow.py mode active` turns enforcement on. See [`public/QUICKSTART.md`](public/QUICKSTART.md).

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
- [`public/examples/brief_template.md`](public/examples/brief_template.md)

## License

MIT. See [`LICENSE`](LICENSE). Reused work is credited in [`public/CREDITS.md`](public/CREDITS.md).
