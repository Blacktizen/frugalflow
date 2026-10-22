This folder contains an event log in the file `events.log`. Each line has four whitespace-separated fields: timestamp, event type, event id, amount. The amount is a non-negative integer number of cents. For example: `2026-04-01T09:00:00 purchase evt-0001 1200`.

Read every line of `events.log` in this folder and write a file named `summary.json` with exactly these keys:
- "total_events": an integer, the total number of log lines in the file.
- "type_counts": an object with the five keys "purchase", "refund", "signup", "chargeback" and "adjustment", each an integer count.
- "total_amount": an integer, the sum of all amounts.
- "largest_event": a string, the event id with the largest amount. If two events tie, use the one that sorts first as plain text.
- "events_above_1000": an integer, the number of events whose amount is greater than 1000.

Write valid JSON. Do not change the log files. An automatic script reads `summary.json` and compares every value.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
