In this folder, `csvtools.py` defines `to_csv_row(fields)`. It builds a comma-separated row but does not quote fields that need quoting.

Fix `to_csv_row` so that it returns a CSV row as a string: the fields are joined with commas, and any field that contains a comma, a double quote, or a newline is wrapped in double quotes with every double quote inside the field doubled. Fields without those characters are written as-is. Keep the function name and the file name unchanged. Use only the Python standard library.

The fix is verified by an automatic script that imports `csvtools` from this folder and calls `to_csv_row` on several lists, checking each result for exact equality.
