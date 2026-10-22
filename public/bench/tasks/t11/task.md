This folder contains a batch job log in the file `jobs.log`. Each line has four whitespace-separated fields: timestamp, job id, status, duration in milliseconds. The status is either OK or FAIL. For example: `2026-03-12T14:05:02 job-0002 FAIL 89`.

Read every line of `jobs.log` in this folder and write a file named `summary.json` with exactly these keys:
- "total_jobs": an integer, the total number of log lines in the file.
- "succeeded": an integer, the number of lines whose status is OK.
- "failed": an integer, the number of lines whose status is FAIL.
- "total_duration_ms": an integer, the sum of all durations.
- "longest_job": a string, the job id with the largest duration. If two jobs tie, use the one that sorts first as plain text.
- "failed_ids": a sorted list of the job ids of every line whose status is FAIL.

Write valid JSON. Do not change the log files. An automatic script reads `summary.json` and compares every value.
