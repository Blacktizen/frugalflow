This folder contains an HTTP access log in the file `access.log`. Each line has six whitespace-separated fields in this exact order: timestamp, host, HTTP method, path, status code, response bytes. For example: `2026-01-15T10:23:45 edge-2 GET /api/orders 200 4821`.

Read every line of `access.log` in this folder and write a file named `summary.json` with exactly these keys:
- "total_requests": an integer, the total number of log lines in the file.
- "status_2xx": an integer, the number of lines whose status code starts with 2. Likewise "status_3xx", "status_4xx" and "status_5xx".
- "top_path": a string, the path that appears in the most lines. If two paths tie, use the one that sorts first as plain text.
- "total_bytes": an integer, the sum of the response byte counts.

Write valid JSON. Do not change the log files. An automatic script reads `summary.json` and compares every value.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
