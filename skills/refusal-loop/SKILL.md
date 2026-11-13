---
name: refusal-loop
description: Use when reviewing the refusals a guard issued, to turn the wrong ones into bench cases and fixes that open no new hole.
---

# The refusal loop: journal, then bench, then fix without regression

Every refusal a guard issues is written to a journal, and a review of that journal
separates the right refusals from the wrong ones. Each wrong one becomes a case in a
dedicated bench, a fix is made to the rule, and the bench is replayed in full to prove
the fix did not open a new hole — only then does the change merge.

## How to apply

1. Log every refusal, with the input that triggered it.
2. Review the journal and mark each refusal right or wrong.
3. Add each wrong refusal as a case in a dedicated bench, then fix the rule.
4. Replay the whole bench before merging.
5. In FrugalFlow, `frugalflow run refusal_loop` automates the bookkeeping and blocks a
   commit while a tool logs no refusals or the bench contains an unresolved false
   refusal or hole.

## Example

The journal shows `grep -r "TODO" src/` being refused as a write, because the parser saw
a redirect-like character inside the quotes. The case is added to the bench and shows
red; the parser is fixed, the whole bench of previous attacks is replayed, and everything
is green.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
