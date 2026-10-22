In this folder, `validate.py` defines `is_valid_identifier(name)`. It accepts some strings that are not valid identifiers.

Fix `is_valid_identifier` so that it returns True exactly when `name` is a non-empty string whose first character is a letter or an underscore and whose remaining characters are letters, digits or underscores, and returns False otherwise. Keep the function name and the file name unchanged. Use only the Python standard library.

The fix is verified by an automatic script that imports `validate` from this folder and calls `is_valid_identifier` on several strings, checking each result for exact equality with True or False.
