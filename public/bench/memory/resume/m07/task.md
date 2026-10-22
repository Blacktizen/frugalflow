This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish router/params.py
- (me) item 5: implement router/lookup.py per SPEC.md
- (me) item 6: implement router/url.py per SPEC.md
LAST ENTRY Session 1 closing note (router)
Done: items 1-3 complete with passing unittests in tests/: router/normalize.py, router/segments.py, router/match.py
Partial: item 4: router/params.py has extract() that captures ':name' segments into a dict in pattern order; missing the '*' wildcard segment; decided to capture params in a plain dict in pattern order, so handlers get values in the order the pattern lists them
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish router/params.py (item 4), then implement router/lookup.py (item 5) and router/url.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
