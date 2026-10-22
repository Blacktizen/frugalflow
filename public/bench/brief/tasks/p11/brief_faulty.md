NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads one value from a settings file and transforms lines.

The program reads the logging flag from the settings file config.json given as argv[1], then reads lines from stdin and prints each line prefixed with `LOG: ` when the flag is enabled, and unchanged when it is not.

FORBIDDEN: hard-coding the flag instead of reading it from the settings file.
The program code is pure ASCII.
Write nothing after the code block.
