This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish conv/time.py
- (me) item 5: implement conv/format.py per SPEC.md
- (me) item 6: implement conv/square.py per SPEC.md
LAST ENTRY Session 1 closing note (conv)
Done: items 1-3 complete with passing unittests in tests/: conv/length.py, conv/mass.py, conv/temp.py
Partial: item 4: conv/time.py has to_hours() backed by an HOURS table for s, min, h; missing the 'day' entry; decided a single table of units-to-hours keeps each conversion one lookup, so adding a unit is one line
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish conv/time.py (item 4), then implement conv/format.py (item 5) and conv/square.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
