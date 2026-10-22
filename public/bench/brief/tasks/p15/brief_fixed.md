NATURE: creation
PRODUIT: controle

Write a command-line program prog.py that reads a file and prints one integer.

The program takes the file path as argv[1] and prints one integer on stdout: how many lines the program keeps.

Before returning, include a self-test (`python3 prog.py --selftest`): run each case in a subprocess, print one line per test starting with PASS or FAIL, and exit with a non-zero exit status as soon as one case fails.

THE QUANTITY the cases measure: the single integer printed on stdout.
THE FILTER THAT the program applies to what it reads: it keeps only the lines that do not start with `;` and ignores every line that starts with `;`.
TESTS: 2
Copy verbatim the two fixtures below.

FORBIDDEN: printing anything other than the single integer.
The program code is pure ASCII.
Write nothing after the code block.

```
; note
alpha
beta
; another note
```

```
gamma
```
