In this folder, `stats.py` defines `median(values)`. It returns the wrong answer when the list has an even number of elements.

Fix `median` so that it returns the middle value when the list has an odd length, and the average of the two middle values when the list has an even length. The list is never empty, and every element is a number. Keep the function name and the file name unchanged. Use only the Python standard library.

The fix is verified by an automatic script that imports `stats` from this folder and calls `median` on several lists, checking each result for exact equality.
