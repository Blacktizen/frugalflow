---
name: criteria-before-measure
description: Use before running any measurement, benchmark or experiment, to fix the metric, threshold, sample and stopping rule in advance.
---

# Criteria are fixed before the measurement (pre-registration)

If you pick the success threshold after seeing the results, you will pick one the results
meet. Write down the metric, the threshold, the sample and the stopping rule before the
first run, commit that file, then run.

## How to apply

1. Write the metric, the threshold, the sample and the stopping rule in a file.
2. Commit that file before the first run.
3. Report against the criterion as written; a result that lands exactly on the
   threshold is called fragile, not rounded up.
4. Refuse "close enough" — that temptation is precisely what the file is there to remove.

## Example

"The new prompt should cut errors by 30 %" is written in a file and committed. The run
shows 29 %. The report says "criterion missed", even though 29 % looks fine. Bench B3
follows this rule, and its result sits exactly on its threshold.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
