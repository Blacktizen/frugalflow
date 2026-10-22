# Log - append-only, sealed

## [2026-10-22 00:00] setup
Decision: vault created by vault_new.py
<!-- chain prev=0000000000000000000000000000000000000000000000000000000000000000 hash=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a -->

## [2026-10-22 16:40] Session 1 closing note (backoff)
Done: items 1-3 complete with passing unittests in tests/: backoff/delays.py, backoff/caps.py, backoff/sums.py
Partial: item 4: backoff/retry.py has should_retry() that stops at max_attempts; missing the check that the error's exact type is in the retryable set; decided to compare type(error) exactly, not isinstance, so subclasses are not silently retried
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish backoff/retry.py (item 4), then implement backoff/steps.py (item 5) and backoff/budget.py (item 6) from SPEC.md
<!-- chain prev=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a hash=eb4b79b442a1feaaf70b9f78432874d0b1e4fde0b46786a4a4c7aa051079942b -->
