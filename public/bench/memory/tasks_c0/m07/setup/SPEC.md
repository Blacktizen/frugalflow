# Simple router — package `router`

Six work items; each is one module inside `router/`. Import modules with
`from router import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `normalize.py`
`normalize(path) -> str`
- Ensure a leading `/`, collapse runs of `/` (drop empty segments), drop any
  trailing slash, and return `/` for the root (an empty or all-slash path).
- A non-string `path` raises `ValueError`.

## Item 2 — `segments.py`
`segments(path) -> list[str]`
- Return the non-empty segments of the normalized path; the root yields `[]`.

## Item 3 — `match.py`
`match(pattern, path) -> bool`
- Both pattern and path are split into segments. They match iff they have the
  same number of segments and each pattern segment equals the path segment,
  except `"*"` matches any single segment.

## Item 4 — `params.py`
`extract(pattern, path) -> dict | None`
- Split both into segments; return `None` if the lengths differ or any literal
  segment mismatches.
- A pattern segment `:name` captures the path segment under `name` (order of
  capture = pattern order). A `"*"` segment matches anything and captures nothing.

## Item 5 — `lookup.py`
`lookup(routes, path) -> tuple | None`
- `routes` is a list of `(pattern, handler)`. Return `(handler, params)` for the
  FIRST pattern that matches, using item 4's `extract`; otherwise `None`.

## Item 6 — `url.py`
`build(path, params) -> str`
- Replace every `{name}` placeholder in `path` with `str(params[name])`.
- Raise `ValueError` if any placeholder is left without a matching key.
  Keys in `params` not present in `path` are ignored.
