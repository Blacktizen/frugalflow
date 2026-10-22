NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads one value from a settings file and scales an integer.

The program reads the priority weight from the settings file config.json given as argv[1], then prints the integer given as argv[2] multiplied by that weight, on stdout and nothing else.

EXACT LOCATION: the priority weight sits in config.json at scoring -> weights -> priority; do not look for it anywhere else.

FORBIDDEN: hard-coding the weight instead of reading it from the settings file.
The program code is pure ASCII.
Write nothing after the code block.

The settings file, verbatim:

```
{"scoring": {"weights": {"priority": 3}}}
```
