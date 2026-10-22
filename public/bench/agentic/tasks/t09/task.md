# Task: count user sessions

The file `clicks.log` has one click per line: `<epoch_seconds> <user>`, the two parts separated by a single space. A session is a run of clicks by the same user where each click is at most 1800 seconds after the previous click of that user; a new session starts when the gap from the previous click is strictly greater than 1800 seconds (a gap of exactly 1800 seconds stays in the same session). Consider each user's clicks in chronological order by their timestamp; the file is not sorted by time.

Write `sessions.json` mapping every user to their number of sessions.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
