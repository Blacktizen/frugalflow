# Benchmarks: what was measured, and how far it holds

Every figure on this page comes from a bench published in [`public/bench/`](../public/bench/README.md), with its raw results. Each verdict states the criterion that was written down before the run. A verdict means "the criterion was met on this bench's set". It is not a guarantee about your data, your models or other tasks, and a set written by the same project that built the tool can favour what the tool recognises. We publish the disappointing runs as well: see [`METHOD.md`](METHOD.md), principle 9.

## The whole toolkit on small tasks

The bench in `public/bench/` (20 small tasks, 3 conditions, 3 repetitions each, 180 runs in total) compares the paid assistant alone, with context discipline only, and with FrugalFlow:

| Condition | Solved | USD per solved task |
|---|---|---|
| `alone` | 60/60 | 0.0150 |
| `discipline` | 59/60 | 0.0138 |
| `frugal` | 58/60 | 0.0273 |

On these small tasks, FrugalFlow costs more than the orchestrator alone, and context discipline alone is the cheapest condition. A second bench on the four `tests` tasks only: 12/12 solved, 0.410 USD instead of 0.912, still above `alone` (0.175 USD). In practice most briefs given to the delegate were wrong and the guards produced false refusals; that consumed mostly turns. Full-scale trials could not be run yet. No saving is claimed until a bench shows one. All runs, disappointing ones included, are published in `public/bench/results/`.

## Per-tool benches (B1 to B7)

Seven per-tool benches ran on neutral made-up (synthetic) sets, each with a verdict criterion written down before the run. Three results are proven on their own bench's set only (B1, B4, B5), B3 meets its criterion exactly on its pre-registered set and is fragile; the others do not, and one was harmful as first built. The verdict column is the strict one: where a criterion was met only after the set was written or tuned with knowledge of earlier results, it says not proven.

| Bench | Tool | Key figure | Verdict |
|---|---|---|---|
| B1 | `anon_check.py` | Planted leaks delivered: 16.2 % (13/80) with the tool, 42.5 % (34/80) with a model reread alone, 100 % with no check; 0 false positives on 40 decoys | **Proven on this bench's synthetic set** |
| B2 | `verify_rules.py` | Hollow checks refused: 80.0 % on the first set (6.7 % good checks wrongly refused); after two tuning loops 47.6 % (10/21) on a fresh set | **Not proven** |
| B3 | external oracle (`delegate.py --verify`) | Pre-registered set (30 tasks, 4 repetitions): model announced green on failing work 10.0 % (12/120, 95 % interval 5.8-16.7 %); the oracle caught all 12 at the second attempt for 1.11x tokens, 0 wrong delivered. Earlier, unregistered sets: 1.7 %, 3.3 %, 8.3 %, 10.0 % | **Useful at the exact threshold, fragile** (10.0 % is the criterion itself; 11 of the 12 false greens sit on 4 tasks, two of them with arguable oracles) |
| B4 | `fidelity.py` | Lines with drifted typography: 69.9 % (498/712) without the tool, 0.0 % (0/712) with it; no content line changed (replay counts, see the line-count note in `public/bench/fidelity/README.md`) | **Proven on this bench's set of short texts, line-by-line comparison** |
| B5 | `brief_check.py` | First-attempt success: 24.4 % with a faulty brief, 97.8 % with the corrected one (+73.3 points); 0 false refusals on 45 sound briefs | **Proven on this bench's set**, within the limit below |
| B6 | `read_intake` read guard | Input tokens 0.94x of the unguarded run, same tasks solved | **Not proven** |
| B7 | session note / resume | Tokens 1.86x with a vault to explore (harmful as built); 0.77x after correction, 4 of 10 projects at or under 0.7x | **Not proven** |

## Multi-session project bench (memory across fresh-context sessions)

Pre-registered, in [`public/bench/multisession/`](../public/bench/multisession/README.md): 25 Exercism Python exercises in one package, 5 sessions of 5 exercises, a fresh context each session, 4 chains (2 per condition), one local model. Project conventions are given in full in session 1 only.

| | Assistant alone | FrugalFlow |
|---|---|---|
| Modules following the conventions, sessions 2-5, strict reading | 0 % (0/40) | **87.5 % (35/40)** |
| Same, lenient reading | 37.5 % (15/40) | **87.5 % (35/40)** |
| Exercises solved at session 5 (2 chains) | 25 and 20 of 25 | 25 and 25 of 25 |
| Cumulative tokens at session 5 (mean) | about 4.04 M | about 6.54 M (about 1.6x) |

**Result.** FrugalFlow kept the project's decisions from one session to the next, with test success equal within run-to-run noise (the one gap comes from an assistant chain whose first session left five stubs; without it the two tie). It does not yet save tokens: the cost verdict is *not proven*, and cutting the per-session cost is on the roadmap. The script's overall verdict is "useful proven (success)", carried by the conventions score and not by the tests.

**Limits.** One model (a quantised local model), Python only, exercises the model probably knows, 2 repetitions per condition, a local server (tokens, not money), conformity read on the final project state. The strict reading alone does not measure memory (the assistant missed a convention from session 1, a final period); the lenient reading does, and the result holds under both. Deviations from the pre-registration are listed in the bench README. The Exercism exercises are not redistributed (the polyglot repository has no license file); the README gives the clone command and the extraction script.

## Why each verdict, plainly

- **B1.** The criterion (30 points fewer leaks than no check) is a low bar, and the tool's rules file knows the planted private names while the reread does not, which favours the deterministic tool on names. Capital-letter names, split keys and base64 evaded both. Before one correction (documentation values such as `@example.com` and reserved IP blocks raised false alarms) the first 60-file run gave 3/20 false positives and was not proven; the verdict rests on the corrected tool and a 120-file set that includes 60 new files.
- **B2.** The judge works on the patterns it was tuned on (100 % on the sets that shaped it) and fewer than half on commands it had not seen. The honest reading is that a pattern list does not generalise.
- **B3.** The earlier sets could not settle it: the first was too easy, the second was written after seeing the first results. A pre-registered set was then fixed before any model run (`public/bench/oracle-prereg/`, 30 valid tasks, 4 repetitions, one local model). Result read by `report.py` without judgement: 12 false greens in 120 attempts, 10.0 %, exactly the criterion (95 % Wilson interval 5.8-16.7 %); a single false green fewer would have read "not proven". The attempts of one task are not independent, and 11 of the 12 false greens come from 4 tasks; removing the two tasks whose oracle is arguable (an after-the-fact analysis, which pre-registration forbids as a verdict) gives 6.9 % then 5.4 %. What holds in every reading: when the model announced green wrongly the oracle caught it every time (12/12, at the second attempt, for 11 % more tokens), and the model never announced red (120/120 green), so its own announcement carries no information on this set. Read it as "cheap and plausibly useful", not as a guarantee. One model, one quantisation, 30 small functions with oracles written by a model.
- **B4.** The original tool left 26 % of lines drifted; a second pass fixed that. Limit: it also cancels a typographic change you ask for on purpose, and it compares line by line.
- **B5.** Limit that matters: the fault tested is, by construction, a removed piece of information the oracle needs. The bench shows the tool catches that fault (45/45) without false refusals; it does not show how many real briefs are faulty that way, nor that it catches faults its rule list does not know. One delegated model.
- **B6.** The model already reads large files in pieces; the hook refuses a whole read of a 2 500-line file, but per task the ratio ranges from 0.56 to 1.70, which is noise around no saving.
- **B7.** The vault made the agent read more, not less. Pasting a short summary into the prompt recovered a quarter of the tokens but missed the pre-set 30 % criterion. The projects are small with a complete spec, so the state is cheap to reread anyway.

Taken together: **on a verification task, FrugalFlow is justified where a bench shows it, and only on that bench's set**: anonymization checking, typographic fidelity and brief checking, with the external oracle as a cheap but fragile fourth. Everywhere else the cost is real and the saving is not yet shown, which is exactly where the project wants help (see the Roadmap in the [README](../README.md)).

## Guard corpora

- The shell guard is replayed on a bench of 212 shell commands (0 holes, 0 false refusals).
- The brief rules are checked on 117 briefs, 65 honest and 52 faulty (0 holes, 0 false refusals).
- 391 recorded guard attacks are all blocked.

These counts hold for the corpora named here, which the project itself wrote; they show the guards behave on those cases, not that no bypass exists, and the shell guard is a home-made command parser, not an operating-system policy.

## Replaying

Offline recomputation from the published raw results, or a fresh run with your own model:

```
# B1  recompute the table from the published run
python3 public/bench/anon/run_b1.py report --truth public/bench/anon/results/verite_120.json --collected public/bench/anon/results/collected_120.json
# B2  recompute judge figures and the proposal stage
python3 public/bench/verify/run_b2.py report-judge --result public/bench/verify/results/judge_fresh42_final.json
python3 public/bench/verify/run_b2.py report-propose --result public/bench/verify/results/propose_P1P2.json
# B3  fresh run: oracle/run_b3.py run ... then report; agent sets: agentic/run_agentic.py (see public/bench/agentic/README.md)
# B4  fresh run: gen_b4.py, run_b4.py run, then report (commands in public/bench/fidelity/README.md)
# B5  recompute the table from the published runs
python3 public/bench/brief/run_brief_bench.py report --out public/bench/brief
# Multi-session: clone the exercises, then run_chain.py and report.py (commands in public/bench/multisession/README.md)
# B6, B7  raw lines and per-run token files are published (reading/, memory/); no one-command report exists
```

Raw outputs of B3 (single-call) and B4 are published as reports, not as the raw runs; a fresh run needs your own model server.
