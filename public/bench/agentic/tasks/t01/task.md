# Task: summarize the access log

The file `access.log` contains one request per line, with fields `timestamp host method path status bytes`. Lines end with LF, except some lines that end with CRLF. A well-formed line has exactly 6 whitespace-separated fields; only these well-formed lines count as valid requests. Blank lines are ignored. Lines whose first field starts with `#` are comments and are ignored. Some lines are truncated (fewer than 6 fields) and are also ignored.

Write a file `summary.json` containing:

- `total_valid`: number of valid requests
- `status_classes`: object mapping each status class `2xx`, `3xx`, `4xx`, `5xx` to its count of valid requests
- `top_path`: the path of valid requests that appears most often; if several paths tie, the one that sorts first wins
- `total_bytes`: sum of the `bytes` field over valid requests
- `skipped`: the number of non-blank lines that were ignored

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
