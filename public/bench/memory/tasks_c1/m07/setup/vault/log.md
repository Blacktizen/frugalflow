# Log - append-only, sealed

## [2026-10-22 00:00] setup
Decision: vault created by vault_new.py
<!-- chain prev=0000000000000000000000000000000000000000000000000000000000000000 hash=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a -->

## [2026-10-22 16:40] Session 1 closing note (router)
Done: items 1-3 complete with passing unittests in tests/: router/normalize.py, router/segments.py, router/match.py
Partial: item 4: router/params.py has extract() that captures ':name' segments into a dict in pattern order; missing the '*' wildcard segment; decided to capture params in a plain dict in pattern order, so handlers get values in the order the pattern lists them
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish router/params.py (item 4), then implement router/lookup.py (item 5) and router/url.py (item 6) from SPEC.md
<!-- chain prev=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a hash=9a1e2630169bc5a3002ddaebd7953d16b6d280f7e4929f58c5b34097c7b42ef1 -->
