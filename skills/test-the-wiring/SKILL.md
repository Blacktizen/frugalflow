---
name: test-the-wiring
description: Use when a component has passing unit tests but nothing proves the hook, command or pipeline actually reaches it.
---

# Testing a component is not testing its wiring

A unit of code can be perfect and never be called. A test that imports the function
proves the function; it does not prove that the hook, the command or the pipeline
actually reaches it. Test the path a real user takes, from the entry point.

## How to apply

1. Write at least one test that enters from the real entry point a user takes.
2. Break the code on purpose and confirm the test goes red.
3. Treat a test that never failed once as not yet a test.
4. In FrugalFlow, `frugalflow run bite` breaks the code on purpose and writes the
   receipt.

## Example

Your input sanitizer has 40 passing unit tests, but the web handler calls a different,
older function. A test that posts a hostile string to the handler fails on day one.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
