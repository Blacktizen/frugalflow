---
name: false-refusal-is-a-defect
description: Use when a guard, linter or filter blocks work that should pass, or when deciding whether a rule's wrong refusals matter as much as its misses.
---

# A false refusal is a defect, exactly like a hole

A guard can fail in two directions: it lets something bad through (a hole), or it blocks
something good (a false refusal). An operator who meets wrong refusals learns to work
around the guard, and then the guard protects nothing.

## How to apply

1. Log every refusal a guard issues, with the input that triggered it.
2. Review the refusals regularly and separate the right ones from the wrong ones.
3. Treat each wrong refusal as a defect: log it, fix it, and replay it with the same
   urgency as a missed leak.
4. Report both columns — holes and false refusals — in every check you publish.

## Example

A linter rule refuses any commit message containing the word "password", to stop leaked
credentials. It also blocks "fix password reset page". After a week people reword their
messages to dodge the rule, then someone disables it — so a wrong refusal is logged,
fixed and replayed with the same urgency as a missed leak.

Full principle: <https://github.com/Blacktizen/frugalflow/blob/main/docs/METHOD.md>
