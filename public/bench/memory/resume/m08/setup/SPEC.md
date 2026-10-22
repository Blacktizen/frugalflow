# Retry / backoff helper — package `backoff`

Six work items; each is one module inside `backoff/`. Import modules with
`from backoff import <module>`. Everything below is normative, including the edge
cases. Do not rename modules or functions.

## Item 1 — `delays.py`
`exponential(base, factor, n) -> list`
- Return the first `n` terms of `base, base*factor, base*factor^2, ...`.
- `n` must be a non-negative integer; otherwise `ValueError`. `n == 0` yields `[]`.

## Item 2 — `caps.py`
`cap(delay, maximum) -> float`
- Return `min(delay, maximum)`. A negative `maximum` raises `ValueError`.

## Item 3 — `sums.py`
`total(delays) -> float`
- Return the sum of `delays`; an empty list yields `0.0`.

## Item 4 — `retry.py`
`should_retry(attempt, max_attempts, error, retryable) -> bool`
- Return `True` iff `attempt < max_attempts` AND `type(error)` is exactly one of
  the types in the `retryable` set (do not use `isinstance`).

## Item 5 — `steps.py`
`delay_at(base, factor, attempt) -> float`
- Return `base * (factor ** attempt)`. `attempt` must be a non-negative integer;
  otherwise `ValueError`.

## Item 6 — `budget.py`
`within_budget(delays, budget) -> list`
- Return the longest prefix of `delays` whose running sum is `<= budget`.
