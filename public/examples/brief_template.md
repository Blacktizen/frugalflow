NATURE: creation
PRODUCT: control
TESTS: 3

# Task: write `count_words.py`, a word counter with its self-test

<!-- Brief template for delegate.py. Copy this file, replace the task, keep every line of the
     "Rules" section as it is: each one answers a rule that brief_check.py enforces. -->

File to create, and only this one: `count_words.py`, in the current folder. It is a new file (creation), not an edit.
Forbidden: touching any other file.

## What to write

A Python 3 file `count_words.py`, standard library only, that defines `count_words(text)`: the number of words in `text`, words being separated by any whitespace (`text.split()`).
Command line: `python3 count_words.py FILE` prints the word count of FILE and exits 0; `python3 count_words.py` without argument prints `usage: count_words.py FILE | --autotest` and exits 2; `python3 count_words.py --autotest` runs the self-test.

## Visible strings, verbatim

`usage: count_words.py FILE | --autotest`

## Fixtures, exact content to copy as is

Fixture 1, a file holding exactly these two lines (to copy as is):
```
one two  three
four
```
Expected count: 4. Empty text: 0. Text `"  "`: 0.

## The filter that the check applies

The check keeps the exit code and the stdout of each command; it ignores stderr.

## The quantity each test moves

The printed word count (0 to 4) and the exit code (0 or 2).

## The 3 tests of the check

1. `count_words.py` on fixture 1 prints `4` and exits 0.
2. No argument: the usage line, exit 2.
3. `--autotest` exits 0 and prints one PASS line per case.

## Rules
Writing accented byte literals is forbidden (accented byte literals): the file is utf-8.
Write nothing after the code block, not a word, not a line.
The self-test runs each case in a subprocess and exits non-zero as soon as one case fails.
It prints ONE LINE PER TEST, starting with PASS or FAIL, with the expected and the obtained value; an empty output is impossible.
It is FORBIDDEN to print FAIL while exiting with code zero.
Every exit code has its test: 0 (tests 1 and 3), 2 (test 2), 1 (test 3 when a case fails).
