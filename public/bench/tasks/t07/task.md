In this folder, `kv.py` defines `parse_key_values(text)`. It reads lines of the form key=value but does not clean the whitespace around keys and values.

Fix `parse_key_values` so that it returns a dictionary built from the non-empty lines of `text`. Lines whose first non-space character is "#" are ignored. Every other line is split on the first "=" character; the key and the value are both stripped of leading and trailing whitespace. If the same key appears more than once, the last occurrence wins. Keep the function name and the file name unchanged. Use only the Python standard library.

The fix is verified by an automatic script that imports `kv` from this folder and calls `parse_key_values` on several strings, checking each result for exact equality.
