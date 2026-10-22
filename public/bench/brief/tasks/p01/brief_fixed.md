NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1]. Each line of the file holds a name and a count, separated by a semicolon. There is no header line. The program prints the sum of the counts as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the sum of the count column, printed as one integer.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores nothing.
TESTS: 2
Copy verbatim the two fixtures below.

FORBIDDEN: reading any file other than the one given as argv[1].
The program code is pure ASCII.
Write nothing after the code block.

```
alice;3
bob;5
carol;7
```

```
x;10
y;20
```
