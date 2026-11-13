---
name: rerun-state
description: Use when a document or page states a recomputable state — counts, statuses, which checks are green — that can go stale unnoticed.
---

# A state is re-run, not re-read

A page that says "the tests pass" or "12 open issues" is a photograph of a past moment,
and it goes stale without anyone noticing. Whatever can be recomputed should be a command
that is re-run when you need the answer, not a sentence copied into a document.

## How to apply

1. Find every recomputable number or status quoted in your documents.
2. Replace it with the command that produces it, plus the date of the last run.
3. When you need the answer, re-run the command instead of re-reading the page.
4. In FrugalFlow, `frugalflow resume` generates the handoff from the vault and the
   sealed journal, never hand-copied, so it cannot drift.

## Example

A status page lists "coverage: 84 %". Nobody updated it after the last refactor, and a
new teammate trusts it. Replace the number with `make coverage` and a rule that reports
quote the output of that command from today.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
