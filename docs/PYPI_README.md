# FrugalFlow

**Project memory your coding agent can't skip.**

FrugalFlow gives Claude Code a memory per project.

A reading gate refuses every write until the project's rules have been reread; every decision is sealed in a hash-chained journal the moment it is made; the next session starts where the previous one stopped.

Other memory tools suggest what to remember; FrugalFlow requires it, and refuses to go on until it is done.

## The one number

Conventions kept across 5 fresh-context sessions: **35/40** modules with FrugalFlow, **15/40** without (lenient reading). Pre-registered bench, one local model, Python only, 2 repetitions per condition.

The strict reading, where the assistant alone scores zero, is explained in [docs/BENCHMARKS.md](https://github.com/Blacktizen/frugalflow/blob/main/docs/BENCHMARKS.md).

## What it costs

About **1.6x the tokens** on that bench (6.54 M against 4.04 M cumulated over 5 sessions). FrugalFlow does not save tokens today; it buys memory with them.

## Quick start

```
pipx install git+https://github.com/Blacktizen/frugalflow
frugalflow new-project myapp --root ~/projects
frugalflow resume
```

Or as a Claude Code plugin:

```
/plugin marketplace add Blacktizen/frugalflow
/plugin install frugalflow@frugalflow
```

`init` starts in `observe` mode (nothing is blocked); `doctor` shows the mode; `frugalflow mode active` turns enforcement on. Install details: [public/QUICKSTART.md](https://github.com/Blacktizen/frugalflow/blob/main/public/QUICKSTART.md), [docs/INSTALL.md](https://github.com/Blacktizen/frugalflow/blob/main/docs/INSTALL.md).

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

They are not a security boundary against a hostile agent. The hooks run as the same user as the assistant: a script the assistant writes and then runs can do what that user can do, and no rule on the text of a command can see inside it. To contain an agent that actively tries to get around the rules, run it in an isolated environment (another user, a container) where FrugalFlow's files are read-only to it. [`public/THREAT_MODEL.md`](https://github.com/Blacktizen/frugalflow/blob/main/public/THREAT_MODEL.md) lists what is covered and what is not. The text guard is frozen at v0.1.7; an isolated mode built on the native Claude Code sandbox is on the roadmap.

The full README, with the optional modules, the roadmap and the documentation index, is on [the project page](https://github.com/Blacktizen/frugalflow/blob/main/README.md).
