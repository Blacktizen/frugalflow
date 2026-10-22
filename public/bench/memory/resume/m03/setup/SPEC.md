# Schedule planner — package `plan`

Six work items; each is one module inside `plan/`. Import modules with
`from plan import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `slot.py`
`parse_time(text) -> int`
- Parse `text` as `HH:MM` with exactly two digits in each part.
- Return minutes since midnight.
- Raise `ValueError` for a non-string, a wrong shape (not `HH:MM`), a
  non-numeric part, or hours/minutes out of range (`0-23` / `0-59`).

## Item 2 — `overlap.py`
`overlap(a, b) -> bool`
- `a` and `b` are `(start, end)` minute intervals.
- Return `True` iff they strictly overlap: `max(a0, b0) < min(a1, b1)`.
  Touching at a single minute does not overlap.

## Item 3 — `fit.py`
`find_slot(busy, duration, day_start, day_end) -> int | None`
- Return the earliest start `s >= day_start` such that `[s, s+duration)` fits
  inside `[day_start, day_end]` and does not overlap any interval in `busy`
  (a list of `(start, end)`; order is not guaranteed).
- Return `None` when no such slot exists.
- Raise `ValueError` for `duration <= 0` or invalid day bounds
  (`day_start < 0` or `day_end <= day_start`).

## Item 4 — `compress.py`
`merge(intervals) -> list`
- Return a new list of intervals where intervals that overlap OR touch
  (`start <= previous end`) are merged into one. Result is sorted by start.
- Do not mutate the input. An empty input yields `[]`.

## Item 5 — `total.py`
`total(intervals) -> int`
- Return the total minutes covered by `intervals` after merging overlapping or
  touching intervals (use item 4's semantics).

## Item 6 — `weekday.py`
`day_index(name) -> int`
- Map a case-insensitive day name (`mon`..`sun`) to `0`..`6`, ignoring leading
  and trailing whitespace. Any other name raises `ValueError`.
