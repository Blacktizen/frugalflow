# Memory (resume)

## Question

Does giving a session the memory of a previous session (a resume note, a vault, or a
resume tool) cut the tokens needed to finish a half-done project?

## Method

10 made-up projects (`m01`..`m10`), each a half-done Python project: `SPEC.md` lists
the whole work, `tests/` holds visible tests, `stock/` holds partial code, `check.py`
is a hidden oracle and `solution/` holds the reference. Conditions:

- **C0** — no memory: the task and the project as-is.
- **C1** — the project plus a `vault/` of session notes (todo, log, decisions).
- **C2** — the agent runs the `resume_note.py` tool over the vault.
- **C3** — the resume note is pasted directly into the prompt.

C0 and C1 are the planned set (repetitions 1-2); repetitions 3-4 are the single
doubling and are appended to the `c0.jsonl` and `c3.jsonl` results. The numbers below
are from repetitions 1-2. Tokens are the sum over repetitions.

## Results (C0 vs C1, repetitions 1-2)

| project | C0 tokens | C1 tokens | C1/C0 | C0 turns | C1 turns |
| --- | ---: | ---: | ---: | ---: | ---: |
| m01 | 301 325 | 682 686 | 2.27 | 37 | 44 |
| m02 | 420 635 | 633 267 | 1.51 | 37 | 61 |
| m03 | 440 598 | 762 345 | 1.73 | 46 | 58 |
| m04 | 350 734 | 621 202 | 1.77 | 35 | 23 |
| m05 | 374 753 | 540 119 | 1.44 | 40 | 46 |
| m06 | 393 281 | 483 277 | 1.23 | 42 | 52 |
| m07 | 407 147 | 1 178 688 | 2.89 | 37 | 78 |
| m08 | 327 293 | 721 349 | 2.20 | 40 | 43 |
| m09 | 327 444 | 464 619 | 1.42 | 31 | 53 |
| m10 | 350 233 | 781 185 | 2.23 | 39 | 69 |
| **total** | **3 693 443** | **6 868 737** | **1.86** | **384** | **527** |

## Verdict

**C1, a vault to explore: harmful.** The total is 1.86x, and 0/10 projects are at <= 0.7x (2 repetitions).

Two correction loops followed (the plan allows two):

- **C2** (resume tool run by the agent): 5 564 346 tokens, 1.51x C0.
- **C3** (resume text pasted in the prompt, the form a session-start hook would give): 0.72x C0 on repetitions 1-2,
  then the sample was doubled once as the plan allows (repetitions 3-4, 40 runs per arm, all solved first try):
  C0 7 184 846 tokens, C3 5 501 964, **0.77x**; 4/10 projects at <= 0.7x (criterion: 8/10); one project worse (m06, 1.03).
  Verdict for the final form: **NOT PROVEN** (a real saving of about a quarter, short of the 30 % criterion).
  The `results/c0.jsonl` and `results/c3.jsonl` files hold the four repetitions.

## Limits

The complete `SPEC.md` already makes the project state cheap to reread, so the note
adds files to read without saving any reading; on a project where the state is costly
to reconstruct the note might pay for itself. One model, one set of 10 projects.

Raw lines: `results/c0.jsonl`, `results/c1.jsonl`, `results/c2.jsonl`,
`results/c3.jsonl`; per-rep tokens in `b7_tokens.txt`. Rebuild the C3 prompts from C0
and C1 with `make_resume_prompts.py`.
