# Brief checker

## Question

Does a brief that passed the brief checker succeed more often at the first delegation
attempt than a faulty brief sent without the filter?

## Method

15 small code tasks, 3 repetitions x 2 conditions, delegated to a remote model through
the delegation tool, one attempt only:

- **C0** — the faulty brief is sent with a waiver (`--brief-waiver`) even though
  `brief_check.py` refuses it.
- **C1** — the brief is corrected after the checker's "To fix" block, and the corrected
  brief is sent.

Each task has a `brief_fixed.md`, a `brief_faulty.md` that differs by exactly one
fault, a hidden oracle `check.py` and a `reference/prog.py`. Validate the set with
`python3 public/bench/brief/tasks/validate.py`. The faults are limited to three rules:
E21 (a fixture only described, not given verbatim), E13 (a value's exact location not
said) and E3 (the reading filter not stated). The checker is
`public/bin/brief_check.py` with `public/config/brief_rules.json`.

## Results

| condition | executions | successes | success rate | Wilson 95 % |
| --- | ---: | ---: | ---: | ---: |
| C0 | 45 | 11 | 24.4 % | 14.2-38.7 |
| C1 | 45 | 44 | 97.8 % | 88.4-99.6 |

Difference C1 - C0: +73.3 points (95 % CI 56.3-83.7). The checker refused 45/45 faulty
briefs and 0/45 corrected briefs.

## Verdict

**USEFUL (proven).**

## Limits

The fault is by construction the removal of a needed piece of information, so a
brief that fixes it is bound to help; the result holds for one model (one remote model)
and for faults limited to the rules E21, E13 and E3. It does not say how the checker
performs on arbitrary real-world briefs.

## Run it yourself

```bash
python3 public/bench/brief/run_brief_bench.py run --tasks public/bench/brief/tasks --bin public/bin --models MODELS_JSON --home HOME --role ROLE --out OUT --reps 3
python3 public/bench/brief/run_brief_bench.py report --out OUT
```

Raw lines: `results.jsonl`.
