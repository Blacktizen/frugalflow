---
name: external-oracle
description: Use when a model reports its own work as done or green, before accepting that report or merging the change it describes.
---

# A "green" announced by the model is worth nothing without an external oracle

A model that writes code also writes a convincing sentence saying the work is done, and
the sentence is evidence of fluency, not of correctness. Only a check that runs on the
delivered artifact, and whose verdict does not pass through the model, counts.

## How to apply

1. Never accept "tests pass" from the model that made the change.
2. Run an independent check on the delivered artifact yourself or in CI.
3. Keep the verdict out of the model's hands: its summary is not the evidence.
4. In FrugalFlow, `frugalflow delegate --verify CMD` never writes the candidate to its
   target until the independent check passes.

## Example

A model reports "all 12 tests pass" after editing a parser; you rerun the suite yourself
and 3 fail, because the summary described the tests it meant to run. On the
pre-registered set, the model announced green on failing work in about one attempt out
of ten, and it never announced red — its own announcement carried no information.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
