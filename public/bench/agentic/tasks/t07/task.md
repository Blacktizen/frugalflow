# Task: fix merge

The module `cfg.py` defines `merge(base, override)`, which should return a new dictionary produced by deep-merging `override` into `base`. If a key exists in both and both values are dictionaries, merge them recursively; otherwise the value from `override` wins and lists are replaced, not concatenated. A value of `None` in `override` deletes the key from the result. The input dictionaries must not be modified.

The current implementation is buggy for some inputs. Fix it without changing the function signature.

Run `python3 test_visible.py` to check the ordinary cases, and verify your fix on edge cases as well.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
