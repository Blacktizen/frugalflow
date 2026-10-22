This folder contains an asset store under the directory `assets/`. It holds many files spread over subdirectories, and some of them are empty.

Walk the whole `assets/` directory and write a file named `inventory.json` with exactly these keys:
- "total_files": an integer, the number of files anywhere under `assets/`.
- "empty_files": a sorted list of the paths relative to this folder (they start with `assets/`), using forward slashes, of every file whose size is zero bytes.
- "total_bytes": an integer, the sum of the byte sizes of all files under `assets/`.
- "largest_file": a string, the path relative to this folder (it starts with `assets/`) (forward slashes) of the file with the largest byte size. If two files tie, use the one that sorts first as plain text.
- "subdir_count": an integer, the number of subdirectories inside `assets/`, counting nested directories, but not counting `assets/` itself.

Write valid JSON. Do not change any file under `assets/`. An automatic script reads `inventory.json` and compares every value.
