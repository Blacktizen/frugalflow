NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads one value from a settings file and filters file names.

The program reads the list of allowed extensions from the settings file config.json given as argv[1], then reads file names from stdin (one per line) and prints, in order, those whose extension is in the list, one per line and nothing else.

EXACT LOCATION: the list of allowed extensions sits in config.json at filters -> allowed -> extensions; do not look for it anywhere else.

FORBIDDEN: hard-coding the list of extensions instead of reading it from the settings file.
The program code is pure ASCII.
Write nothing after the code block.

The settings file, verbatim:

```
{"filters": {"allowed": {"extensions": [".txt", ".md"]}}}
```
