This folder holds a project that is partly done; SPEC.md lists the whole work. Continue the work and finish all 6 items, keeping what already works. Run the tests of the project when you can.

The previous session left this resume (there is no other memory to look for):

RESUME of the previous session
OPEN
- (me) item 4: finish backoff/retry.py
- (me) item 5: implement backoff/steps.py per SPEC.md
- (me) item 6: implement backoff/budget.py per SPEC.md
LAST ENTRY Session 1 closing note (backoff)
Done: items 1-3 complete with passing unittests in tests/: backoff/delays.py, backoff/caps.py, backoff/sums.py
Partial: item 4: backoff/retry.py has should_retry() that stops at max_attempts; missing the check that the error's exact type is in the retryable set; decided to compare type(error) exactly, not isinstance, so subclasses are not silently retried
Not started: items 5 and 6
How to test: python3 -m unittest discover -s tests
Next step: finish backoff/retry.py (item 4), then implement backoff/steps.py (item 5) and backoff/budget.py (item 6) from SPEC.md

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
