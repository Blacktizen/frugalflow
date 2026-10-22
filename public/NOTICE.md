# The notice contract

Every tool in `bin/` answers `--notice`. It prints five sections, in this order, and does
nothing else: it writes no file and exits with code 0.

```
NAME      <tool>.py - what it is for, in one sentence, on one line.
READS     which JSON, which key, and what breaks if it is missing.
WRITES    what it puts on disk, and where; or "nothing".
EXAMPLE   one complete invocation that works, naming the tool.
PITFALLS  what already went wrong, each line dated YYYY-MM-DD.
          A line that starts with a space continues the section above.
```

## What `bin/notice_check.py` refuses

It runs `python3 <tool> --notice` in an **empty temporary directory**, with `HOME` pointed
there, and refuses the tool when:

| Defect | Why it matters |
|---|---|
| the exit code is not 0 | a notice that fails is no notice |
| a file appeared in the directory | a notice must not *run* anything |
| a section is missing, empty, doubled, or out of order | the five questions are the contract |
| a line outside any section | stray output means the tool did not recognise `--notice` |
| `NAME` spans more than one line | one sentence, or it is not a name |
| `EXAMPLE` does not name the tool | an example of something else teaches nothing |
| `PITFALLS` carries no date | an undated pitfall cannot be checked against history |

The rules themselves live in `bin/notice_rules.py`, a pure module with its own self-test.

## Where it is enforced

The pre-commit hook (`hooks/pre-commit`, installed by `bin/install_hooks.py`) runs
`notice_check.py` on every `bin/*.py` staged for commit. A tool without a conforming notice
cannot be committed.

## Known limits

- A `--notice` that writes **outside** its working directory, other than under `HOME`,
  is not detected.
- Every tool of `bin/` meets the contract; `release_check.py` verifies it on the whole tree.
