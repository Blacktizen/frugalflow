This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish graph/reach.py
- (me) item 5: implement graph/shortest.py per SPEC.md
- (me) item 6: implement graph/count.py per SPEC.md
LAST ENTRY Session 1 closing note (graph)
Done: items 1-3 complete with passing unittests in tests/: graph/edges.py, graph/degree.py, graph/components.py
Partial: item 4: graph/reach.py has reachable() that returns the start plus its direct neighbours; missing the exploration of further nodes; decided to track seen nodes in a set, so cycles are handled once traversal is finished
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish graph/reach.py (item 4), then implement graph/shortest.py (item 5) and graph/count.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
