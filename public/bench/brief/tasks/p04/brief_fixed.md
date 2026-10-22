NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints names, one per line.

The program takes the file path as argv[1]. Each line holds a name and a count, separated by a comma. The program prints the names sorted by count from highest to lowest, one per line on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the list of names printed on stdout, one per line.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores nothing.
TESTS: 2
Copy verbatim the two fixtures below.

FORBIDDEN: printing anything other than the names, one per line.
The program code is pure ASCII.
Write nothing after the code block.

```
alice,3
bob,9
carol,5
```

```
x,1
y,2
z,3
```
