This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish cfg/schema.py
- (me) item 5: implement cfg/merge.py per SPEC.md
- (me) item 6: implement cfg/defaults.py per SPEC.md
LAST ENTRY Session 1 closing note (cfg)
Done: items 1-3 complete with passing unittests in tests/: cfg/types.py, cfg/get.py, cfg/intval.py
Partial: item 4: cfg/schema.py has check() that reports rule keys whose predicate returns false; missing reporting keys absent from cfg; decided to report in rule insertion order, so output is deterministic for callers
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish cfg/schema.py (item 4), then implement cfg/merge.py (item 5) and cfg/defaults.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
