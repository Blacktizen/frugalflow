You are given a module `intervals.py` with a function `merge(intervals)` that takes a list of inclusive intervals `[start, end]` of numbers and returns a new list of the merged intervals, sorted by start, where intervals that overlap or merely touch are combined, so `[1,2]` and `[2,3]` merge into `[1,3]`. The input may be in any order. If an interval is given with its start greater than its end, treat it as `[end, start]`. The input list must not be modified.

For example, `merge([[1,3],[2,6],[8,10]])` returns `[[1,6],[8,10]]`.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
