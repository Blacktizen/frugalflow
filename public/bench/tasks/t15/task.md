This folder contains a project tree under the directory `project/`. It holds many text files, and some of them contain TODO markers.

Walk the whole `project/` directory and write a file named `inventory.json` with exactly these keys:
- "total_files": an integer, the number of files anywhere under `project/`.
- "total_lines": an integer, the total number of lines across all files under `project/`. The number of lines in one file is the number of newline characters in it, and an empty file has zero lines.
- "todo_files": a sorted list of the paths relative to this folder (they start with `project/`), using forward slashes, of every file whose content contains the exact substring "TODO".
- "longest_file": a string, the path relative to this folder (it starts with `project/`) (forward slashes) of the file with the most lines. If two files tie, use the one that sorts first as plain text.

Write valid JSON. Do not change any file under `project/`. An automatic script reads `inventory.json` and compares every value.
