# Task: fix add_months

The module `dates.py` defines `add_months(date, n)`, which should return the `datetime.date` that is `n` months after `date`. `n` may be negative. Keep the same day-of-month where possible; if the target month has fewer days, clamp to the last day of the target month.

The current implementation is buggy for some inputs. Fix it without changing the function signature.

Run `python3 test_visible.py` to check the ordinary cases, and verify your fix on edge cases as well.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
