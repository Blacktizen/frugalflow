NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1]. The file is a CSV with a header line `name,count` followed by data rows. The program prints the number of data rows as a single integer on stdout and nothing else.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the single integer printed on stdout.
THE FILTER THAT the program applies to what it reads: it keeps every non-empty line and ignores blank lines.
TESTS: 2
Copy verbatim the two fixtures below.

FORBIDDEN: printing anything other than the single integer.
The program code is pure ASCII.
Write nothing after the code block.

```
name,count
alice,10
bob,20
carol,30
```

```
name,count
x,1
y,2
```
