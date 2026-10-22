This folder contains a source tree under the directory `tree/`. It holds many files spread over subdirectories.

Walk the whole `tree/` directory and write a file named `inventory.json` with exactly these keys:
- "total_files": an integer, the number of files anywhere under `tree/`.
- "extension_counts": an object whose keys are file extensions without the dot (for example "py") and whose values are integer counts of files with that extension.
- "total_bytes": an integer, the sum of the byte sizes of all files under `tree/`.
- "fixme_files": a sorted list of the paths relative to this folder (they start with `tree/`), using forward slashes, of every file whose content contains the exact substring "FIXME".
- "largest_file": a string, the path relative to this folder (it starts with `tree/`) (forward slashes) of the file with the largest byte size. If two files tie, use the one that sorts first as plain text.

Write valid JSON. Do not change any file under `tree/`. An automatic script reads `inventory.json` and compares every value.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
