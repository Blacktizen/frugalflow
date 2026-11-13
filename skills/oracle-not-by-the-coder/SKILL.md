---
name: oracle-not-by-the-coder
description: Use when writing tests or checks for code that a model (or you) will also write, and the oracle must exist before the candidate does.
---

# The oracle is never written by whoever writes the code

If one author writes both the implementation and its tests, the tests encode the author's
misunderstanding along with the code. The oracle comes from a different hand — another
model, a person, or a script fixed in advance — and it is written, or at least frozen,
before the candidate exists.

## How to apply

1. Write the checks first, from the spec, never from the implementation.
2. Have a different hand write them: another model, a person, or a fixed script.
3. Freeze the oracle before the candidate exists, and run it in a separate process.
4. Never ask for the implementation and its tests in one prompt.

## Example

A model asked for a date parser and its tests in one prompt reports 5 passing tests, yet
the file defines the function and never calls it, so the tests assert nothing. The same
task with an oracle written first and run in a separate process fails immediately and
says why.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
