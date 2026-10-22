This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish stock/adjust.py
- (me) item 5: implement stock/merge.py per SPEC.md
- (me) item 6: implement stock/low.py per SPEC.md
LAST ENTRY Session 1 closing note (stock)
Done: items 1-3 complete with passing unittests in tests/: stock/parse.py, stock/stats.py, stock/report.py
Partial: item 4: stock/adjust.py has apply() that mutates totals in place, returns the same dict, and guards a non-int delta; missing the guard that raises ValueError when the result would be negative; decided apply() mutates in place so chains of adjustments need no reassignment, because callers adjust one record repeatedly
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish stock/adjust.py (item 4), then implement stock/merge.py (item 5) and stock/low.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
