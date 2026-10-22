This folder contains a store under the directory `store/`. It holds many files spread over subdirectories, and some files share identical content with other files.

Walk the whole `store/` directory and write a file named `inventory.json` with exactly these keys:
- "total_files": an integer, the number of files anywhere under `store/`.
- "total_bytes": an integer, the sum of the byte sizes of all files under `store/`.
- "duplicate_content_groups": an integer, the number of distinct file contents that appear in more than one file.
- "largest_file": a string, the path relative to this folder (it starts with `store/`) (forward slashes) of the file with the largest byte size. If two files tie, use the one that sorts first as plain text.
- "extensions": a sorted list of the distinct file extensions, without the dot.

Write valid JSON. Do not change any file under `store/`. An automatic script reads `inventory.json` and compares every value.

When you are finished, end your answer with the single line `TESTS: GREEN` if you checked that everything required works, or `TESTS: RED` if not.
