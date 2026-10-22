# Task: fix parse_duration

The module `durations.py` defines `parse_duration(text)`, which should parse a duration string made of parts such as `1h30m`, `90s`, `2d`, or `1d2h3m4s` and return the total number of seconds as an int. Units are `d`, `h`, `m`, `s` (86400, 3600, 60, and 1 seconds) and may be written in upper or lower case. Whitespace is allowed between the parts. An empty string, a bare number with no unit, or an unknown unit must raise `ValueError`.

The current implementation is buggy for some inputs. Fix it without changing the function signature.

Run `python3 test_visible.py` to check the ordinary cases, and verify your fix on edge cases as well.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
