# Log - append-only, sealed

## [2026-10-22 00:00] setup
Decision: vault created by vault_new.py
<!-- chain prev=0000000000000000000000000000000000000000000000000000000000000000 hash=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a -->

## [2026-10-22 16:40] Session 1 closing note (stock)
Done: items 1-3 complete with passing unittests in tests/: stock/parse.py, stock/stats.py, stock/report.py
Partial: item 4: stock/adjust.py has apply() that mutates totals in place, returns the same dict, and guards a non-int delta; missing the guard that raises ValueError when the result would be negative; decided apply() mutates in place so chains of adjustments need no reassignment, because callers adjust one record repeatedly
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish stock/adjust.py (item 4), then implement stock/merge.py (item 5) and stock/low.py (item 6) from SPEC.md
<!-- chain prev=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a hash=b2979925b0a245debd58b554cbdbdd55cebc98e04263637aebd7c955b3dd8c12 -->
