---
name: fail-closed
description: Use when writing or reviewing a guard, check or scanner, to decide what it does when it crashes, times out or cannot read its configuration.
---

# A guard that breaks must close, not open

If a safety check crashes, times out or cannot read its configuration, the safe outcome
is refusal with a message saying how to fix it. A check that quietly returns "fine" when
it fails is invisible, and a default value that guesses manufactures verdicts out of
nothing.

## How to apply

1. On crash, timeout or missing configuration, refuse with a distinct exit code and a
   "To fix:" line.
2. Never catch the error and continue with an empty or guessed configuration.
3. Make the failure visible on the dashboard, not a silent pass.
4. In FrugalFlow, `frugalflow run anon_check` exits with code 13 and prints
   `NO RULES FILE` rather than reporting a clean tree.

## Example

A secret scanner loads its pattern file from a path that no longer exists, catches the
error and scans with an empty list. Every file passes. The fix is the opposite
behaviour: a missing pattern file stops the run.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
