# Task: fix dedupe

The module `textutil.py` defines `dedupe(items)`, which should return a list of the unique strings from `items`, keeping the first occurrence of each and preserving their order. Two strings count as the same if they differ only by letter case, by leading/trailing whitespace, or by Unicode composition of accents (for example, a precomposed `é` equals a decomposed `e` followed by a combining accent). When two strings count as the same, keep the first one exactly as it appears, unchanged.

The current implementation is buggy for some inputs. Fix it without changing the function signature.

Run `python3 test_visible.py` to check the ordinary cases, and verify your fix on edge cases as well.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
