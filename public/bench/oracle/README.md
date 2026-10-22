# Bench: how often does a model announce green tests that an outside check refuses?

For each task of `public/bench/tasks` that a single answer can solve (t01-t08 fix a function, t17-t20 write unit tests), a
delegated model returns the file and ends with `TESTS: GREEN` or `TESTS: RED`. The hidden `check.py` is the oracle.

- C0: believe the announcement (first answer only).
- C1: run the oracle, give its verdict back to the model, up to 3 attempts.

12 tasks x 5 repetitions, a local `qwen3.8-flash-next` (IQ3_XXS) at medium effort:

| | result |
|---|---|
| C0 announced green | 60 / 60 |
| C0 false greens (announced green, oracle red) | 1 / 60 (1.7 %), one run of t19 |
| C0 passed the oracle | 59 / 60 |
| C1 resolved | 60 / 60, 62 attempts |
| tokens, C1 over C0 | 1.19 x (1280 per solved task, then 1500) |

Same tasks at low effort with thinking off: 60 / 60 on the first answer, no false green, same tokens in both conditions.

What it says: on tasks this small the model rarely announces a green it has not earned, so the oracle loop buys almost nothing
here and costs about a fifth more tokens when it fires. It does not show that an outside check is useless on harder work; it
shows these tasks are too easy to tell. The other 8 tasks (logs, inventories) need tools and are not part of this single-answer bench.

```bash
python3 public/bench/oracle/run_b3.py run --tasks public/bench/tasks --ids t01,t02,t03,t04,t05,t06,t07,t08,t17,t18,t19,t20 \
  --reps 5 --bin public/bin --models YOUR_MODELS.json --out /tmp/b3.json
python3 public/bench/oracle/run_b3.py report --result /tmp/b3.json
```
`--effort LEVEL` and `--no-thinking` pass through to the delegate. `--autotest` runs the script's own checks.
