# Ledger — package `ledger`

Six work items; each is one module inside `ledger/`. Import modules with
`from ledger import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `entry.py`
`parse(line) -> (date, description, amount)`
- Split `line` on spaces into at most 3 parts: `date`, `description` (may contain
  spaces), `amount`.
- `date` must match `YYYY-MM-DD` with a real month `1-12` and day `1-31`.
- `description` must not be empty.
- `amount` must parse as a float (negative and zero allowed).
- Raise `ValueError` otherwise (including a non-string or wrong-shaped line).

## Item 2 — `balance.py`
`balance(entries) -> float`
- Return the sum of the amounts of the `(date, description, amount)` tuples.

## Item 3 — `filter.py`
`by_date(entries, date) -> list`
- Return the entries whose date equals `date`, in their original order.

## Item 4 — `order.py`
`sorted_entries(entries) -> list`
- Return a new list sorted by `(date, description)` ascending. Do not mutate the
  input. Equal dates must be broken by description.

## Item 5 — `monthly.py`
`by_month(entries) -> dict`
- Return a dict mapping the `YYYY-MM` prefix of each entry's date to the sum of
  its amounts.

## Item 6 — `statement.py`
`render(entries) -> str`
- Return one line `date description amount` per entry, sorted by
  `(date, description)`, with a trailing newline; empty input renders as `""`.
