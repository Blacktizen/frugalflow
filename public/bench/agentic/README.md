# Agentic traps

## Question

How often does an agent announce `TESTS: GREEN` while its work actually fails an
outside check, and does an outside oracle with up to 3 attempts catch and fix those
false greens?

## Method

Two conditions on the same tasks, 10 small made-up tasks x 6 repetitions per engine:

- **C0** — believe the announcement: the first attempt's `TESTS: GREEN` line is taken
  at face value.
- **C1** — oracle with up to 3 attempts: after each attempt an outside `check.py` runs
  on the working folder; on failure its message is fed back and the agent retries, up
  to 3 attempts.

Each task folder holds the instruction (`task.md`), the starting files (`setup/`), the
outside oracle (`check.py`), a reference `solution/` and a known-wrong `naive/`
(validate with `python3 public/bench/agentic/tasks/validate.py`). The `hard/` set
reuses the 8 log/inventory tasks of `public/bench/tasks` with their generated data
removed; each `task.md` ends with the same `TESTS:` line so the announcement can be
read. Two engines were run: a local model (qwen3.8-flash-next, IQ3_XXS) and
deepseek-v4-pro.

## Results

Traps set, 10 tasks x 6 repetitions per engine:

| engine | false greens C0 | rate | Wilson 95 % |
| --- | ---: | ---: | ---: |
| a local model (qwen3.8-flash-next, IQ3_XXS) | 2/60 | 3.3 % | 0.9-11.4 |
| deepseek-v4-pro | 5/60 | 8.3 % | 3.6-18.1 |

All 7 false greens are on task t08. After the oracle loop, delivered false greens are
0/60 for each engine. Token ratio C1/C0: 1.02 (local model) and 1.12 (deepseek-v4-pro).
Hard set (logs, inventories): 0/24 (local model) and 0/16 (deepseek-v4-pro) false greens.

## Verdict

**NOT PROVEN.** The criterion was fixed before the run: useful if false greens are
>= 10 % in C0 and < 2 % with the oracle, at <= 2x tokens. Both engines are below 10 %
(3.3 % and 8.3 %), so the criterion is not met.

## Second set: subtle traps (written after the first set showed a ceiling)

10 new tasks (u01-u10): amounts and separators, canonical roman numerals, word wrap,
semantic versions, interval merge, rolling-window limiter, BOM/semicolon CSV, slug,
multi-line log entries, half-away-from-zero rounding. The tasks were written before
any run; every task is red on its naive solution and green on its reference
(`python3 public/bench/agentic/tasks_subtle/validate.py`).

| engine | runs | false greens C0 | rate | Wilson 95 % |
| --- | ---: | ---: | ---: | ---: |
| a local model (qwen3.8-flash-next, IQ3_XXS) | 60 (10 tasks x 6 reps) | 6 | 10.0 % | 4.7-20.2 |
| deepseek-v4-pro | 25 valid | 6 | 24 % | 11.5-43.4 |

Local model: all 6 false greens are on u01 (3) and u04 (3); after the oracle loop,
0 of 60 delivered wrong; resolved 60/60; token ratio C1/C0 = 1.12.

deepseek-v4-pro: only 25 valid runs (the account ran out of credit mid-way; the rest
are not counted); 6 false greens of 25 = 24 %, on u01, u04 and u08. The partial figure
is shown as is; per-attempt lines are in `results/deepseek_subtle.jsonl`.

Verdict for this set: **USEFUL (proven)** for the local model, at the threshold
(10.0 % against the 10 % criterion, lower bound 4.7 % above 0; delivered wrong 0 %;
overhead 1.12x); the deepseek figure is partial.

Overall B3 reading: not proven on easy tasks (3.3 % and 8.3 %), proven on subtle
ones; the oracle caught every false green it was shown.

Raw lines: `results/local_subtle.jsonl`, `results/deepseek_subtle.jsonl`.

## Limits

The tasks are small and easy; on these tasks the oracle rarely lies (7 false greens
across 160 runs), and every false green comes from one task (t08). A larger or harder
set could move the rate, but this bench does not demonstrate it.

## Run it yourself

```bash
python3 public/bench/agentic/run_agentic.py run --taskroot public/bench/agentic/tasks --task t01 --rep 1 --out OUT --agent-cmd "YOUR AGENT COMMAND"
```

The command reads the prompt on stdin and prints a Claude Code `--output-format json`
object. Add `--max-attempts 3 --timeout 900` as needed; `report --out OUT` renders the
table. Raw lines: `results/local_traps.jsonl`, `results/deepseek_traps.jsonl`,
`results/local_hard.jsonl`, `results/deepseek_hard.jsonl`.

Note: in the first set, task t01 had its host column renamed (private-range addresses replaced by `edge-N` names) before publication; the field is not used by the task or its oracle, and the measured runs used the original addresses.
