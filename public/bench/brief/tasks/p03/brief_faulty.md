NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and a threshold date, and prints one integer.

The program takes the file path as argv[1] and the threshold as argv[2]. Each line of the file holds a date, then a comma and an event name. The program prints how many events fall strictly after the threshold date, as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the single integer printed on stdout.
THE FILTER THAT the program applies to what it reads: it keeps every line whose date is after the threshold and ignores the rest.
TESTS: 2
The fixtures: a file with three rows, dated mid-January 2024, early June 2024 and mid-March 2025, and a second file with two rows, dated early 2023 and mid-May 2024.

FORBIDDEN: hard-coding the threshold instead of reading argv[2].
The program code is pure ASCII.
Write nothing after the code block.
