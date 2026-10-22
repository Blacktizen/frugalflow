# Config validator — package `cfg`

Six work items; each is one module inside `cfg/`. Import modules with
`from cfg import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `types.py`
- `is_int(s)`: `True` iff `s` is a string that `int(s)` accepts.
- `is_float(s)`: `True` iff `s` is a string that `float(s)` accepts.
- `is_bool(s)`: `True` iff `s` is a string whose stripped lowercase is one of
  `true`, `false`, `yes`, `no`, `1`, `0`.
- A non-string argument is always `False`.

## Item 2 — `get.py`
`get(cfg, key, default=None) -> value`
- Return `cfg[key]`, or `default` when the key is missing OR its value is `None`.

## Item 3 — `intval.py`
`to_int(value, default, lo, hi) -> int`
- `None` returns `default`. A bool raises `ValueError`.
- Otherwise `int(value)`; a failure raises `ValueError`.
- The result must satisfy `lo <= result <= hi`; otherwise `ValueError`.

## Item 4 — `schema.py`
`check(cfg, rules) -> list`
- `rules` is an ordered dict mapping a key to a predicate.
- Return, in rules order, the keys that FAIL: a key is failing when it is missing
  from `cfg` or its predicate returns false.

## Item 5 — `merge.py`
`merge(base, overrides) -> dict`
- Return a NEW dict equal to `base` updated with the entries of `overrides`
  whose value is not `None`. Do not mutate `base`.

## Item 6 — `defaults.py`
`with_defaults(cfg, defaults) -> dict`
- Return a NEW dict equal to `cfg` but with each key of `defaults` filled in when
  it is missing from `cfg` or its value is `None`.
