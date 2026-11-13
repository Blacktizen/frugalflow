---
name: frugalflow-memory
description: The FrugalFlow project memory: the reading gate, the sealed journal, the closing pass and the handoff. Use when working in a project that has a FrugalFlow vault.
---

# FrugalFlow memory

Four rules, each enforced by a hook — the assistant cannot skip them.

## 1. The reading gate: reread before you write
Before the first write into a project's vault, the project's own rules must have gone
through your context. Read `vault/overview.md`, then `vault/index.md`, then the two or
three pages the task touches — never the whole vault. The gate refuses the first write
into a vault that asks for a reading, shows the bearing lines, and accepts the identical
write right after. The rules you just reread are the ones that bind your edits.

## 2. The sealed journal: one entry after every gesture
Any action that changes state — a commit, a merge, a setting, a measurement that settles
a question — must be followed by a journal entry, before the turn ends:

```
frugalflow run journal_add --vault <vault> --title <t> --field "Decision=..." --field "Why=..."
```

The journal is append-only and
hash-chained: an entry is superseded, never rewritten. `r1_guard` blocks the end of the
turn when a gesture has no entry.

## 3. The closing pass: `frugalflow close`
At the end of a session, run `frugalflow close`. It checks the vault (no orphan page,
no dead link, a todo present) and says whether the handoff is ready.

## 4. The handoff: `frugalflow resume`
A new session starts with `frugalflow resume`: the handoff is generated from the vault
and the sealed journal, never hand-copied, so it cannot drift from what really happened.
