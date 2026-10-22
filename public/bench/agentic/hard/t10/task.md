This folder contains a service log in the file `svc.log`. Each line has five whitespace-separated fields: timestamp, level, service, code, and message. The message is the remaining text and may contain spaces. For example: `2026-02-03T08:11:23 WARN db-2 W-305 connection timeout while waiting for a reply`.

Read every line of `svc.log` in this folder and write a file named `summary.json` with exactly these keys:
- "total_lines": an integer, the total number of log lines in the file.
- "level_counts": an object with the four keys "INFO", "WARN", "ERROR" and "DEBUG", each an integer count of lines at that level.
- "distinct_services": an integer, the number of distinct service names.
- "busiest_service": a string, the service with the most lines. If two services tie, use the one that sorts first as plain text.
- "distinct_error_codes": an integer, the number of distinct codes seen on ERROR lines.
- "warn_timeouts": an integer, the number of WARN lines whose message contains the substring "timeout".

Write valid JSON. Do not change the log files. An automatic script reads `summary.json` and compares every value.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
