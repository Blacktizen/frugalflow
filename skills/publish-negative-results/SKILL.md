---
name: publish-negative-results
description: Use when reporting a measurement, benchmark or experiment, including one that failed, missed its criterion or showed no saving.
---

# Negative results get published

If only the successes are reported, readers learn nothing about where the tool does not
work, and the next person repeats your dead end. A failed experiment, a bench where the
tool cost more than it saved, a criterion that was not met: publish them with the same
care, including the raw runs.

## How to apply

1. Report failures with the same care as successes, raw runs included.
2. Say plainly when no saving is shown, and keep the data.
3. Name the reason a result might have missed.
4. Publish negative benches next to the positive ones: FrugalFlow's benches B2, B6 and
   B7 sit in `BENCHMARKS.md` next to the successes.

## Example

A caching layer is expected to cut token use. The measurement shows a ratio of 0.94 with
noise ranging from 0.56 to 1.70 across tasks. The write-up says "no saving shown", keeps
the data, and names the reason it might have missed.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
