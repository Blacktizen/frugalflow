# Multi-session bench: does the project memory hold across fresh-context sessions?

## Question

On a real project run over several sessions, with the memory set-up paid once, does FrugalFlow
(condition B) cost fewer tokens, or succeed better, than the assistant alone (condition A)?

## Headline result

25 exercises, 5 sessions of 5, a fresh context each session, one local model, 2 chains per condition.

| | A (assistant alone) | B (FrugalFlow) |
|---|---|---|
| Modules following the project conventions, sessions 2-5, strict reading | 0 % (0/40) | **87.5 % (35/40)** |
| Same, lenient reading (final period accepted in rule T3) | 37.5 % (15/40) | **87.5 % (35/40)** |
| Exercises solved (tests), cumulative at session 5 | 25 and 20 of 25 | 25 and 25 of 25 |
| Cumulative tokens at session 5 (mean of 2 chains) | about 4.04 M | about 6.54 M (about 1.6x) |

- **Conventions are kept.** FrugalFlow carried the project decisions from one session to the next. This is the
  result the memory pillar exists for, and it holds under both readings of the rules.
- **Same test success.** The gap on tests (2.5 exercises) is smaller than the gap between the two A chains
  (5 exercises), so nothing is proven on tests. It comes from one A chain whose session 1 left five modules as
  empty stubs (the agent reported its shell was pinned to an old directory inode); without that session, A and B tie.
- **No token saving yet.** B costs more, not less: the instruction block, the journal and the closing step are
  paid every session, and this bench does not separate the share of each. The cost verdict is **not proven**
  (no session count at which B costs less). Making the memory pay in tokens is on the roadmap.

Official script verdicts (rules fixed in the pre-registration, read without judgement):
`COST: NOT PROVEN`, `SUCCESS: USEFUL`, `OVERALL: USEFUL PROVEN (success)`. The "success" branch comes from the
conventions score (B minus A = 0.90 under the strict reading), not from the tests. See `results/report.md`.

## Contents

```
harness/       the rerunnable harness (plain Python, standard library only)
  prep_exo.py          extracts exercises from the polyglot benchmark clone
  run_chain.py         runs one chain of 5 sessions (condition A or B)
  measure.py           token count from the agent stream; tests run by the harness
  check_rules.py       rules T1-T5 checked by AST after each session
  report.py            per-session table, cumulative curve, verdicts
  analyse_conformite.py   per-session conformity, strict and lenient reading
  plan.json            the pilot and the 5 measured sessions
  tpl/                 the session prompts and the condition-B block (in French, as run)
results/
  A1/A2/B1/B2.results.jsonl   one line per session: tokens, tests, rules
  report.md                   output of report.py on the four chains
  conformity.md               output of analyse_conformite.py
```

Each script carries `--autotest`. The prompt templates and some script messages are in French because that is
what was run; they were left untouched so the run can be replayed as is.

## Protocol (pre-registered before any measurement; translated)

**Data set.** Aider polyglot benchmark, Exercism Python exercises, revision `7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f`.
34 exercises; excluded because their tests or structure do not fit a package: paasio, react, hangman, grep, rest-api.
The `.meta/` folder (reference solution) is never copied into the project. The tests are Exercism's, only the import
is rewritten (`from kata.<module> import`). The oracle is these tests, run by the harness outside the agent
(pytest, 120 s per exercise at most). Pilot (4 exercises, excluded from the measure): S1 proverb, affine-cipher;
S2 pig-latin, bottle-song. Measure, 25 exercises in 5 sessions of 5 (see `harness/plan.json`). Each session receives,
dropped by the harness just before it, the files of its own exercises only (stub, tests, statement); future exercises
are not visible.

**Project and cross-session rules**, given in full in session 1 only (A and B). Sessions 2-5 get only the session
number, the exercise list and one sentence: continue the kata project in the current folder, make these tests pass,
respect the project conventions and decisions.
- T1: `kata/common.py` defines `fail(message: str) -> NoReturn` raising `ValueError(message)`; every module raising a
  `ValueError` does so through `fail`; no `raise ValueError` outside `common.py`.
- T2: public top-level functions and public methods have all parameters and the return type annotated.
- T3: the first line of the module docstring is exactly `Kata: <slug>` (slug with hyphens).
- T4: no module imports `re` or `regex` (a decision taken in session 1).
- T5: the files in `tests/` are never modified (sha256 against what the harness dropped); `common.py` keeps `fail`
  with the same signature.
Checked by script (AST) after each session. Respect score = modules conforming to T1-T4 over modules delivered
(non-empty and different from the stub); T5 is counted apart. "Memory" score = the same restricted to sessions 2-5.

**Conditions (same agent).** Claude Code in headless mode (`-p`, stream-json, 80 turns maximum), a fresh process
and context each session (no resume), one session at a time.
- A: the session prompt and the repository. No vault, no journal, no hooks.
- B: `frugalflow new-project` once before session 1 (vault, sealed journal, project hooks), `FRUGALFLOW_HOME` private
  to the chain; `init` is not run; the guard mode stays at its default (observe). Each B session also gets the same
  instruction block (write to the journal at each gesture, close with `session_digest.py`) and, from session 2, the
  text printed by `resume_note.py` pasted at the top of the prompt. The cost of the block, the set-up, the journal
  and the closing is counted in B.
- 4 chains of 5 sessions; order drawn with `random.Random(252).shuffle(["A1","A2","B1","B2"])`, run as B, A, B, A.
  A repetition is a chain (2 per condition). Wall limit 30 minutes per session (killed processes keep their tokens).

**Metrics.** Tokens per session (input + cache creation + cache read, and output, summed from the agent's `usage`
records); cumulative cost per chain and mean per condition; spread between repetitions = |r1 - r2|. Exercises
solved per session and cumulative (external oracle). Respect of T1-T5. Turns, wall time, killed sessions.

**Verdict thresholds (read by script).**
- USEFUL PROVEN (cost): some k <= 5 where Cum_B(k) < Cum_A(k) by more than the larger spread, still true at k = 5.
- USEFUL PROVEN (success): solved at k = 5, B minus A >= 2 exercises and above the larger spread; or respect score
  B minus A >= 0.15 with the same spread criterion.
- HARMFUL: Cum_B(5) above Cum_A(5) beyond the spread, and success and respect of B not above A.
- NOT PROVEN: everything else.

**Stop rules.** Only complete chains count. A session is replayed once on infrastructure failure. No session is
removed or changed after the first measurement call.

## Deviations (the pre-registration was not edited)

- D1 (pilot, before the measure): the test runner used `python3 -I`, which ignores `PYTHONPATH`, so `kata` could not be
  imported and every exercise counted as unsolved. Fixed before the measure; the pilot results recorded before the fix
  were discarded, the pilot token counts stay valid.
- D2: `main` has no `frugalflow resume` subcommand at the time of the run; `resume_note.py` output is pasted instead.
- D3: the harness scripts were written by the local model under the project's delegation guard, each with a green
  autotest. The machine slept for several hours during that generation, which shifted the schedule; the stop time in
  the pre-registration was unchanged.
- D4 (seen in the pilot, not fixed): T3 is read literally; an agent that adds a final period is non-conforming.
- D5: checked that chains did not run in parallel (one agent process at a time).
- D6: assistant A had 0 of 5 conforming modules from session 1 under the strict reading (a final period in
  `Kata: <slug>.`). That is the rule not being followed from the start, not forgetting between sessions, so the strict
  reading alone does not measure memory. The official verdict is unchanged; `analyse_conformite.py` was added to report
  both the strict and the lenient reading, and the headline above states what holds under both.

## Limits

One model (a small open-weight model, quantised to about 3 bits per weight, served locally); one language (Python) and a set the model
probably knows (Exercism); a local server, so cost is in tokens, not money, and the tokens include the context reread
at each turn; 2 repetitions per condition; a success ceiling (25/25) that leaves little room for a gain on tests;
conformity is read on the final state of the project, not at the end of each session; the two conditions do not get the
same session text (B also gets the FrugalFlow block and the pasted summary, which is the method's cost, counted in B);
the guard hooks ran in their default observe mode. In B2, 5 of the 40 later modules missed a convention (missing
annotations, sessions 3 and 5).

## Replay

The Exercism exercises are **not** redistributed here: the polyglot repository has no LICENSE file. Fetch them
yourself at the same revision and extract:

```
git clone https://github.com/Aider-AI/polyglot-benchmark work/polyglot
git -C work/polyglot checkout 7e0611e77b54e2dea774cdc0aa00cf9f7ed6144f
python3 public/bench/multisession/harness/prep_exo.py work/polyglot/python/exercises/practice work/exo

# one chain of 5 sessions; RUNCHAIN_AGENT is any command that behaves like `claude` (default: claude)
export BENCH_MS_W=$PWD/work
python3 public/bench/multisession/harness/run_chain.py --cond B --chain B1 --plan main
python3 public/bench/multisession/harness/run_chain.py --cond A --chain A1 --plan main
# repeat with B2 and A2, then:
python3 public/bench/multisession/harness/report.py work/runs
python3 public/bench/multisession/harness/analyse_conformite.py work/runs
```

`results/report.md` comes from `report.py` run on the four published `*.results.jsonl` files (put each in
`runs/<chain>/results.jsonl` to recompute it). `results/conformity.md` was produced by `analyse_conformite.py` on the
final project of each chain (`runs/<chain>/proj/kata/`); those generated projects and the raw agent streams are not
published here, so it is recomputed only by a fresh run. The agent command is a parameter because the run used a
local model server behind a `claude` wrapper; point `RUNCHAIN_AGENT` at yours.
