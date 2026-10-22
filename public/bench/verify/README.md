# Bench: does the check judge catch checks that verify nothing?

`verify_rules.judge` refuses a delegation's check command when it cannot fail (`true`, `ls`, `--help`, `|| true` ...).
This bench measures how often it does, and how often it refuses a good check by mistake.

Files:
- `commands_b2.json` (30 hollow + 30 real), `commands_b2_heldout.json` (20 + 20), `commands_b2_fresh.json` (21 + 21):
  check commands with a label. The three sets were written one after another; the second and third were written after the
  rules had been tuned on the previous one, so only the last is a fair test of what the rules generalise to.
- `spec_b2.json` + `mk_candidates.py`: twenty tiny tools, each with a correct and a broken version and an honest `--autotest`.
- `run_b2.py`: `judge` runs every command through the judge and, for hollow ones, on the broken tools; `report-judge`
  prints recall and false refusals; `propose` asks a delegated model for a check on each broken tool (two prompt styles) and
  counts the broken tools that would be delivered with and without the judge; `report-propose` prints the totals.

```bash
python3 public/bench/verify/mk_candidates.py --spec public/bench/verify/spec_b2.json --out /tmp/cand
python3 public/bench/verify/run_b2.py judge --commands public/bench/verify/commands_b2_fresh.json \
  --candidates /tmp/cand/index.json --bin public/bin --out /tmp/judge.json
python3 public/bench/verify/run_b2.py report-judge --result /tmp/judge.json
```

Both scripts have `--autotest`.

## Measured

| Set | Judge | hollow refused | good checks refused |
|---|---|---|---|
| first 60 (30 + 30) | original rules | 24 / 30 (80.0 %) | 2 / 30 (6.7 %) |
| first 60 | after tuning on them | 30 / 30 | 0 / 30 |
| second 40 (20 + 20, written after the first tuning; the second tuning used its misses) | after both | 20 / 20 | 0 / 20 |
| fresh 42 (21 + 21, written last) | original rules | 7 / 21 (33.3 %) | 1 / 21 |
| fresh 42 | after tuning (`verify_extra.py`) | 10 / 21 (47.6 %) | 0 / 21 |

The tuned judge catches `|| true`, `; echo $?`, a pipe into `tail`, `python3 -c pass`, print-only code and a grep that matches
anything; the fresh set shows what it still misses (`touch`, `mkdir -p x && echo done`, `exit 0`, `cargo check`, `gcc -fsyntax-only`...).
A list of known-hollow patterns does not generalise: its recall on commands it has not seen is under half.

Model in the loop (`propose`, 20 broken tools x 3 repetitions, prompt that does not mention the tool's self-test):
the delegated model proposed a check that let a broken tool through in 5 of 60 cases without the judge, 2 of 60 with it
(`results/propose_P1P2.json`); with the self-test mentioned, 0 of 60 in both cases. The model rarely proposes a hollow check, so
the judge has little to catch there. A judge based on a list of known-hollow patterns cannot know the patterns it has not seen:
read the fresh set's recall, not the tuned sets'.
