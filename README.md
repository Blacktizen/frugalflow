# FrugalFlow

[![tests](../../actions/workflows/tests.yml/badge.svg)](../../actions/workflows/tests.yml)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![Python 3.11+](https://img.shields.io/badge/python-3.11%2B-blue.svg)](docs/INSTALL.md)

**Project memory your coding agent can't skip.**

FrugalFlow gives Claude Code a memory per project.

A reading gate refuses every write until the project's rules have been reread; every decision is sealed in a hash-chained journal the moment it is made; the next session starts where the previous one stopped.

Other memory tools suggest what to remember; FrugalFlow requires it, and refuses to go on until it is done.

## The one number

Conventions kept across 5 fresh-context sessions: **35/40** modules with FrugalFlow, **15/40** without (lenient reading). Pre-registered bench, one local model, Python only, 2 repetitions per condition.

The strict reading, where the assistant alone scores zero, is explained in [docs/BENCHMARKS.md](docs/BENCHMARKS.md).

## What it costs

About **1.6x the tokens** on that bench (6.54 M against 4.04 M cumulated over 5 sessions). FrugalFlow does not save tokens today; it buys memory with them.

## Quick start

```
pipx install git+https://github.com/Blacktizen/frugalflow
frugalflow new-project myapp --root ~/projects
frugalflow resume
```

`init` starts in `observe` mode (nothing is blocked); `doctor` shows the mode; `frugalflow mode active` turns enforcement on. Install details: [public/QUICKSTART.md](public/QUICKSTART.md), [docs/INSTALL.md](docs/INSTALL.md).

## How the memory works

### 1. A memory built like a wiki, not a chat log
Every project gets a vault on the *LLM Wiki* pattern: raw sources, a wiki of linked pages, a schema that says how to keep it. Entry is always the same path: `overview`, then `index`, then two or three targeted pages, never everything. The closing pass (`vault_check`) keeps it healthy: no orphan page, no dead link, a todo always present.

### 2. Rereading is not a suggestion: it is enforced
The reading gate refuses any write until the project's bearing lines (its rules, its warnings, its validated methods) have gone through the assistant's context. It is a check, not an instruction: the assistant cannot forget it. The rule that matters is in front of it every time it acts.

### 3. Every decision is written when it is made
After any action that changes state (a commit, a merge, a setting, a measurement that settles a question), a sealed journal entry must follow, or the end of the turn is blocked (`r1_guard`). The journal is append-only and hash-chained: an entry is superseded, never rewritten. Nothing is reconstructed from memory at the end of the day.

### 4. The next session starts where the last one stopped
`frugalflow resume` builds the handoff from the vault and the sealed journal. It is generated, never hand-copied, so it cannot drift from what really happened.

### 5. Nothing is accepted on a model's word
"Done" means nothing until an independent check says so (`delegate.py --verify`). A test only counts once it has been seen red, then green: `bite` breaks the code on purpose to prove the suite really fails. Inside the hook, a check that crashes or doubts refuses, with a "To fix:" line, never a silent pass.

## What it is not

FrugalFlow's guards are a safety net against the mistakes and shortcuts of a cooperative assistant: forgetting the project's rules, skipping a delegation, writing over a log, turning a setting off, sending private data to a third party. They refuse at the moment of the gesture, and every refusal says what to do instead. Settings are yours to change in your own terminal (`config set`, `on`, `off`, `mode`); the assistant is refused if it tries, in every mode.

They are not a security boundary against a hostile agent. The hooks run as the same user as the assistant: a script the assistant writes and then runs can do what that user can do, and no rule on the text of a command can see inside it. To contain an agent that actively tries to get around the rules, run it in an isolated environment (another user, a container) where FrugalFlow's files are read-only to it. [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md) lists what is covered and what is not. The text guard is frozen at v0.1.7; an isolated mode built on the native Claude Code sandbox is on the roadmap.

## Optional modules

- [Delegation](docs/DELEGATION.md): bulky work handed to cheaper models, with briefs that get better with every mistake.
- [Privacy and anonymization](docs/PRIVACY.md): your private data stays out of third-party models.
- [Refusal loop](docs/REFUSAL_LOOP.md): a refusal log per tool that feeds the benches.
- [Benchmarks](docs/BENCHMARKS.md): every figure, its scope, and how to replay it.

## Built with FrugalFlow

FrugalFlow was built with its own method, and its method runs every day on long-lived production projects, a web application and a mobile application among them. Counted by script from its own files, over 11 weeks: **956** sealed journal entries, **201** numbered todos, **745** commits through its own gates, **224** sessions resumed from a written handoff.

More than 100 small tools, each with `--notice` (its contract and pitfalls) and `--autotest`; a test suite that runs in a fresh clone with no key and no model, in CI on Python 3.11 and 3.12; standard library only, no dependency.

## Join in

FrugalFlow gets better the way it was built: from other people's real cases. You do not need to write much code to help.

- **Report a false refusal.** A guard that blocked something it should not have is the most valuable report you can send. Copy the refused line, say what you were doing and what the right answer was.
- **Add a case to a bench.** A new brief, a new disguised command, a new leak pattern, a task where delegation did or did not pay off. Red before the fix, green after.
- **Pick a good first issue.** Look for the `good first issue` label in the issue tracker; small rules, notes and docs are a gentle start.
- **Propose a brief rule or record a model pitfall.** Both are described, with the proof they need, in [`CONTRIBUTING.md`](CONTRIBUTING.md).
- **Star the repository** if the method is useful to you, so others can find it.

Every change keeps the tests green and adds a bench case when a refusal was wrong.

## Documentation

- [`docs/INSTALL.md`](docs/INSTALL.md): install, scan, setup, uninstall, release check
- [`docs/METHOD.md`](docs/METHOD.md): the principles behind the tools, with neutral examples
- [`docs/BENCHMARKS.md`](docs/BENCHMARKS.md): every figure, its scope, and how to replay it
- [`docs/PIPELINE.md`](docs/PIPELINE.md): how a task flows through the tools, with a diagram
- [`docs/DELEGATION.md`](docs/DELEGATION.md): delegation, briefs, per-model notes
- [`docs/PRIVACY.md`](docs/PRIVACY.md): anonymization and secret scanning
- [`docs/REFUSAL_LOOP.md`](docs/REFUSAL_LOOP.md): the refusal log and its bench loop
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
