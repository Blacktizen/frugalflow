This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish table/align.py
- (me) item 5: implement table/escape.py per SPEC.md
- (me) item 6: implement table/markdown.py per SPEC.md
LAST ENTRY Session 1 closing note (table)
Done: items 1-3 complete with passing unittests in tests/: table/split.py, table/widths.py, table/render.py
Partial: item 4: table/align.py has pad() that left- and right-justifies a cell; missing center alignment; decided center puts the odd extra space on the right, so centering is deterministic for odd widths
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish table/align.py (item 4), then implement table/escape.py (item 5) and table/markdown.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
