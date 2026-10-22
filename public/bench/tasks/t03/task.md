In this folder, `timefmt.py` defines `format_duration(total_seconds)`. It returns a wrong result for many inputs.

Fix `format_duration` so that, for a non-negative integer number of seconds, it returns a string "H:MM:SS" where H is the whole number of hours (no leading zero, and it can grow past two digits), MM is the minutes within the hour written as exactly two digits, and SS is the seconds within the minute written as exactly two digits. Keep the function name and the file name unchanged. Use only the Python standard library.

The fix is verified by an automatic script that imports `timefmt` from this folder and calls `format_duration` on several values, checking each result for exact equality.
