# Task: busiest UTC hour

The file `events.log` has one event per line: `<ISO timestamp> <user> <action>`, the three parts separated by single spaces. Timestamps carry a UTC offset such as `+02:00`, `-05:00`, or `Z`.

Convert every timestamp to UTC, then bucket events by the UTC hour they fall in, written in the format `2026-01-15T10` (year-month-day, the letter T, and a 2-digit hour). Write `busiest.json` containing:

- `hour`: the UTC hour with the most events
- `count`: how many events fall in that hour

If two hours tie for the most events, pick the earliest one.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
