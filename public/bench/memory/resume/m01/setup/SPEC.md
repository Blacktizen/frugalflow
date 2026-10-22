# Inventory report — package `stock`

Six work items; each is one module inside `stock/`. Import modules with
`from stock import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `parse.py`
`parse_line(line) -> (name, quantity, unit)`
- Split `line` on commas and strip whitespace around every field.
- 2 fields: the unit is absent and becomes `"pcs"`.
- 3 fields: the third field is the unit; a stripped-empty unit also becomes `"pcs"`.
- Any other number of fields is an error.
- `name` must be a non-empty string; `quantity` must be an integer >= 0.
- Raise `ValueError` for a non-string or empty `line`, an empty `name`, a
  non-integer or negative `quantity`, and any number of fields other than 2 or 3.

## Item 2 — `stats.py`
`total(parsed) -> dict`
- `parsed` is a list of `(name, quantity, unit)` tuples from item 1.
- Return a dict mapping each `name` to the sum of its quantities.

## Item 3 — `report.py`
`render(totals) -> str`
- Return one line `name: quantity` per name, sorted by name ascending.
- End with a trailing newline; an empty dict renders as `""`.

## Item 4 — `adjust.py`
`apply(totals, name, delta) -> dict`
- Add `delta` to `totals[name]` (a missing name counts as 0), mutating `totals`
  in place and returning the same dict object.
- `delta` must be an integer; otherwise `ValueError`.
- If the resulting quantity would be negative, raise `ValueError`.

## Item 5 — `merge.py`
`merge(left, right) -> dict`
- Return a NEW dict summing, per name, the quantities of `left` and `right`
  (a missing name counts as 0). Do not mutate either argument.

## Item 6 — `low.py`
`below(totals, limit) -> list`
- Return the names whose quantity is strictly less than `limit`, sorted ascending.
