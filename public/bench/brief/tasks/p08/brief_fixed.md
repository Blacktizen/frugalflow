NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads one value from a settings file and builds a file name.

The program reads the output suffix from the settings file config.json given as argv[1], then prints the name given as argv[2] with the suffix appended, on stdout and nothing else.

EXACT LOCATION: the output suffix sits in config.json at output -> format -> suffix; do not look for it anywhere else.

FORBIDDEN: hard-coding the suffix instead of reading it from the settings file.
The program code is pure ASCII.
Write nothing after the code block.

The settings file, verbatim:

```
{"output": {"format": {"suffix": ".done"}}}
```
