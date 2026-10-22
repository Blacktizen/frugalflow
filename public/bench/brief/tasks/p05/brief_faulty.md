NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1]. Each line holds a name and a count, separated by a comma. The program prints the sum of the counts as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the sum of the counts, printed as one integer.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores nothing.
TESTS: 2
The fixtures: a file with three rows (alice 3, bob 5, carol 7), and a second file with two rows (x 10, y 20).

FORBIDDEN: printing anything other than the single integer.
The program code is pure ASCII.
Write nothing after the code block.
