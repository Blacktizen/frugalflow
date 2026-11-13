---
name: task-is-a-creation
description: Use when delegating work to a model, to choose between editing a large existing file and asking for a new, self-contained one.
---

# A delegated task is a creation, not a retouch

Giving a cheaper model a large existing file and asking for a small edit invites silent
damage: lines dropped, quotes altered, an unrelated function rewritten. Ask for a new,
small, self-contained file with a precisely stated interface, then integrate it yourself
or with a mechanical merge.

## How to apply

1. Prefer a new small file over a retouch of a large one.
2. State the interface precisely and the cases the file must pass.
3. Integrate the result yourself or with a mechanical merge.
4. When fidelity matters, measure it: in FrugalFlow, `frugalflow run fidelity` checks
   the drift (in bench B4, 69.9 % of the lines of a retouched text had drifted
   typography before the check).

## Example

"Fix the timeout bug in `server.py`" (900 lines) comes back with the bug fixed and the
logging format changed. "Write `retry.py` exposing `retry(fn, attempts, delay)`, here are
the five cases it must pass" comes back as a file you can read in one minute and replace
if it is wrong.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
