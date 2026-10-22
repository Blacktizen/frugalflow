NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads one value from a settings file and classifies integers.

The program reads the maximum allowed count from the settings file config.json given as argv[1], then reads integers from stdin (one per line) and prints OK for each integer up to the maximum and OVER for each integer above it, one line per input.

EXACT LOCATION: the maximum allowed count sits in config.json at limits -> daily -> max; do not look for it anywhere else.

FORBIDDEN: hard-coding the maximum instead of reading it from the settings file.
The program code is pure ASCII.
Write nothing after the code block.

The settings file, verbatim:

```
{"limits": {"daily": {"max": 40}}}
```
