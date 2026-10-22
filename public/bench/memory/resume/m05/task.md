This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish ledger/order.py
- (me) item 5: implement ledger/monthly.py per SPEC.md
- (me) item 6: implement ledger/statement.py per SPEC.md
LAST ENTRY Session 1 closing note (ledger)
Done: items 1-3 complete with passing unittests in tests/: ledger/entry.py, ledger/balance.py, ledger/filter.py
Partial: item 4: ledger/order.py has sorted_entries() that sorts by date ascending and returns a new list; missing the description tie-break on equal dates; decided to sort by (date, description) so output is deterministic
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish ledger/order.py (item 4), then implement ledger/monthly.py (item 5) and ledger/statement.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
