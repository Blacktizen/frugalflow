# Log - append-only, sealed

## [2026-10-22 00:00] setup
Decision: vault created by vault_new.py
<!-- chain prev=0000000000000000000000000000000000000000000000000000000000000000 hash=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a -->

## [2026-10-22 16:40] Session 1 closing note (ledger)
Done: items 1-3 complete with passing unittests in tests/: ledger/entry.py, ledger/balance.py, ledger/filter.py
Partial: item 4: ledger/order.py has sorted_entries() that sorts by date ascending and returns a new list; missing the description tie-break on equal dates; decided to sort by (date, description) so output is deterministic
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish ledger/order.py (item 4), then implement ledger/monthly.py (item 5) and ledger/statement.py (item 6) from SPEC.md
<!-- chain prev=9cc4f9703b125ae46f58383ec90d08b01b1fff43356ffab7d94ec3ba1c1e2b7a hash=ca2b0b664f83edf208df0c43ad888bc289a4210a20bb1bcd51ed2d56b9a060b6 -->
