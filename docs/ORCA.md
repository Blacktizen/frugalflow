# Using FrugalFlow with Orca workers

[← Back to the README](../README.md)

A compatibility page: what FrugalFlow's guards do — and do not do — when Orca runs a fleet of code agents.

Orca ([github.com/stablyai/orca](https://github.com/stablyai/orca), MIT) is a desktop application with an
`orca` command line. It runs a fleet of command-line code agents — Claude Code, Codex, OpenCode,
and others — each in its own git worktree, with a diff view. Its orchestration feature
([orca.dev/docs/cli/orchestration](https://orca.dev/docs/cli/orchestration)) has a coordinating agent
create a run and tasks with dependencies, launch supervised workers, wait for their messages and
answer their questions. The feature is marked experimental, and its documentation describes no guard,
no permission model and no memory.

FrugalFlow does not integrate with Orca and does not become an orchestrator. It is compatible with
it: the value of FrugalFlow is the control of what the orchestration produces.

## What works

FrugalFlow hooks installed at the user level (`frugalflow init`, or the Claude Code plugin) apply to
every Claude Code worker Orca launches: each worker is an ordinary Claude Code session, and Claude
Code runs the user-level hooks for it like for any other session.

In every worktree that contains the vault, the reading gate, the sealed journal and `frugalflow
resume` work as they do in a single-session repository.

## What does not

Codex, OpenCode and the other agents Orca can launch do not run Claude Code hooks. They
are **not under guard**: no reading gate, no sealed journal entry required, no refusal at the moment
of the gesture.

Two ways to stay in control:

- use only Claude Code workers, so every worker runs under the same hooks;
- or judge the result of the other workers by an external check — the same principle as
  `delegate.py --verify`: a test only counts once it has been seen red, then green.

## The vault across worktrees

If the vault is tracked by git, each worktree gets its own copy of the vault and of its journal.
Two workers that seal entries in parallel produce two journal chains to reconcile at merge time.

FrugalFlow does not yet provide a lock or a journal merge across worktrees. Until it does, the
practical shape is one worker that seals — the coordinator — while the other workers propose their
decisions in their reports instead of writing them to the journal.

## Recipe

1. Install FrugalFlow at the user level: `frugalflow init`, or in Claude Code
   `/plugin marketplace add` then `/plugin install frugalflow@frugalflow`.
2. Mount the vault in the repository: `frugalflow init --here`, run in the main worktree.
3. For the coordinator, type `frugalflow mode orchestrator` yourself in your terminal, if you want
   it refused for writing bulky code without a delegation receipt.
4. Launch Claude Code workers from Orca; each gets its own worktree, and the vault comes with it
   when it is tracked by git.
5. Finish in the main worktree with `frugalflow close`, then start the next session with
   `frugalflow resume`.

## Isolated mode

`frugalflow harden` and the MCP server ([ISOLATION.md](ISOLATION.md)) act on the Claude Code
settings of the user who launches the workers, so they hold for every Claude Code worker on the same
machine. They do not cover the other agents Orca can launch — the same limit as above, seen from the
sandbox side.

## Status

A compatibility page, not an integration. Nothing on this page has been tested end to end with Orca
to date. If you run FrugalFlow under Orca, reports of what the guards caught — or missed — are
welcome in the repository's discussions.
