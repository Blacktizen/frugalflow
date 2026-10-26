# The FrugalFlow bench

Measure before promising. The same tasks are given to the same orchestrator under three conditions, and the cost per
solved task is compared. Every run, including the disappointing ones, is published in `results/`.

## The tasks

`tasks.json` lists 20 small, public, neutral tasks (8 `code`, 4 `logs`, 4 `inventory`, 4 `tests`). Each folder
`tasks/<id>/` holds the instruction (`task.md`), the starting folder (`setup/`), an optional deterministic `prepare.py`
that builds the large inputs, a `check.py` that exits 0 only when the task is solved, and a reference `solution/` that is
never shown to the orchestrator. `public/tests/e2e_bench.py` replays every reference solution through the bench runner.

## The three conditions

| Condition | What the orchestrator gets |
|---|---|
| `alone` | the task, nothing else |
| `discipline` | the task and a short `CLAUDE.md` of context rules (read targeted parts, script the counting, short messages) |
| `frugal` | the same rules, plus FrugalFlow installed by `frugalflow.py init --mode active`: hooks, guard, delegation to a local model |

Each run gets a fresh configuration folder: no hook, setting or memory of the operator leaks into it.

## Run it yourself

```bash
python3 public/bin/bench_run.py run-all --tasks public/bench/tasks.json --conditions <your conditions.json> --out results.jsonl --reps 3
python3 public/bin/bench_report.py results.jsonl --out report.md
```

A conditions file names, per condition, the command that runs your orchestrator (any command printing a Claude Code
`--output-format json` result), its environment, an optional context file, the delegation log to sum, and the prices per
million tokens used to compute the cost. `run-all` resumes where it stopped; `bench_run.py --notice` gives the full contract.

## Results

Orchestrator: Claude Code driven by a remote hosted model through an Anthropic-compatible endpoint, chosen to keep
the bench affordable; anyone can rerun it with another orchestrator. Delegated model (`frugal` only): a local
quantized open-weight model (mid-size context window). Prices: the remote provider's off-peak list prices of the day,
0.66 USD per million input tokens, 0.022 cached, 1.98 output. 20 tasks, 3 conditions, 3 repetitions: 180 runs per bench.

| Bench | `alone` solved / cost per solved task | `discipline` | `frugal` |
|---|---|---|---|
| v2 | 60/60, 0.0150 USD | 59/60, 0.0138 USD | 58/60, 0.0273 USD |

What these numbers say, plainly:
- On tasks this small, **FrugalFlow costs more, not less**. Context discipline alone is the cheapest condition (about 8 % below `alone` in v2).
- A run that delegated nothing because of a broken install measures nothing and is not published. After v2, refused
  orchestrators still read the source code to guess the brief rules; v3 measures the fix.
- The whole extra cost of `frugal` in v2 sits in the four `tests` tasks, where a 30 to 40 line file must be delegated.
- v3 replays only the four `tests` tasks under `frugal`, with the hint pointed to `frugalflow.py lint`: 12/12 solved,
  0.410 USD instead of 0.912 in v2 (9 to 17 turns instead of 22 to 36), still above `alone` on the same tasks (0.175 USD).
  Projected over the 20 tasks, `frugal` would cost about a fifth more than `alone`.
- No claim of savings is made until a bench shows one.

Raw lines: `results/bench-v2.jsonl` (v2), `results/bench-v3-tests.jsonl` (v3),
with their reports beside them.

## Per-tool benches

Each tool is also measured alone, on a neutral made-up set, with and without it; each folder has its own README and results.
Verdicts are strict: a result obtained on a set written after seeing earlier results, or after tuning on that set, is not proven.

| Folder | Bench | Question | Key figure | Verdict |
|---|---|---|---|---|
| `anon/` | B1 | does `anon_check.py` stop leaks a model reread lets through? | 16.2 % of planted leaks delivered, against 42.5 % for the reread and 100 % with no check; 0 false positives on 40 decoys | proven on this bench's synthetic set |
| `verify/` | B2 | does the check judge refuse checks that verify nothing? | 80.0 % of hollow checks on the first set, 47.6 % (10/21) on a fresh set | not proven |
| `oracle/` | B3 | how often does a model announce green tests that fail the oracle? | 1.7 % (1/60) on these tasks, too easy to tell | not proven |
| `agentic/` | B3 | does an outside oracle catch the false greens an agent announces? | 3.3 % and 8.3 % on the first set; 10.0 % on a second set written after seeing the first; 0 wrong delivered | not proven (promising; needs a pre-registered set) |
| `oracle-prereg/` | B3 | pre-registered set: how often does the local model announce green on failing code, and does the oracle catch it? | 10.0 % (12/120, interval 5.8-16.7 %); all 12 caught at the second attempt, 1.11x tokens; 11 of 12 on 4 tasks | useful at the exact threshold, fragile (see the results file in that folder) |
| `fidelity/` | B4 | how much typography does a model lose, and does `fidelity.py` give it back? | 69.9 % of lines drift without the tool (498/712), 0 of 712 with it, no content changed | proven on this bench's short texts, line comparison |
| `brief/` | B5 | does a brief that passed the brief checker win more first attempts? | 24.4 % to 97.8 % (+73.3 points); the fault tested is a removed fact | proven on this bench's set, with that limit |
| `reading/` | B6 | does the read guard `read_intake` cut input tokens? | 0.94x | not proven |
| `memory/` | B7 | does resuming from a previous session cut tokens? | 1.86x as built (harmful), 0.77x after correction | not proven |

The B3 pre-registered set (`oracle-prereg/`) keeps its task statements (`tasks/*/task.md` and the statement list in `B3-PREREG.md`) in their original language, French, which is the language of the measurement: they are data sent verbatim to the model, so the bench can be replayed identically. The pre-registration, results and deviations documents are in English.

On a verification task, FrugalFlow is justified only where a bench shows it, and only on that bench's synthetic set (B1, B4, B5; B3 at its exact threshold, fragile). A verdict is not a guarantee.

Replay commands are in each folder README, and the root README lists the offline report commands
(`python3 public/bench/anon/run_b1.py report ...`, `python3 public/bench/brief/run_brief_bench.py report --out public/bench/brief`,
`python3 public/bench/verify/run_b2.py report-judge ...`). B6 and B7 publish raw lines and token files but no one-command report.
