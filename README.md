# FrugalFlow

A toolkit around Claude Code that keeps the paid assistant in charge of judging and deciding while delegating bulky mechanical work to a cheaper model under mechanical control. The guards, the journal, and the verification passes are real and tested; the economics are not yet there.

Task flow through the tools is described in [`docs/PIPELINE.md`](docs/PIPELINE.md) with a diagram.

## Why

A paid assistant reads long files, drafts boilerplate, triages logs and judges the draft, all at the same rate. Every token is charged at the orchestrator's rate. FrugalFlow asks a simple question: which of those steps require judgment, and which are mechanical enough to hand to a local model while a paid check still decides whether the result is accepted.

## What you get

108 small Python tools in `public/bin/`, Python 3.11 or newer, standard library only, each carrying `--notice` (its contract) and `--autotest`.

- **Project memory.** `vault_new.py` mounts a vault; `vault_check.py` is the hard closing pass that verifies what is written is true; `reading_gate.py` attests a reading only when a restatement repeats every bearing line of the required pages.
- **Append-only hash-chained journal.** `journal_add.py` appends one sealed entry after checking the existing chain. `session_log.py` and `session_chain.py` seal every session event with the sha256 of the previous line and compare the log with an anchor. `r1_guard.py` blocks the end of a turn while a state-changing command ran with no journal entry after it. `session_digest.py` is the closing pass.
- **Proven guards.** `guard_hook.py` and `guard_rules.py` refuse a code write that cannot point to a recent successful delegation receipt. The shell guard is replayed on a bench of 212 shell commands (0 holes, 0 false refusals). The brief rules are checked on 117 briefs, 65 honest and 52 faulty (0 holes, 0 false refusals). 391 recorded guard attacks are all blocked. 15 end-to-end suites (`public/tests/e2e_*.py`) and the autotest of all 108 tools pass in a fresh checkout. `bite.py` breaks code on purpose to prove a suite goes red. Guards fail closed: a crashed check or any doubt means refusal, with a "To fix:" line.
- **Controlled delegation with an external oracle.** `brief_check.py` judges the brief before sending. `delegate.py` sends the task to the model of a role and, with `--verify`, retries until the check passes and never writes an unchecked attempt to the target. `verify_rules.py` and `verify_sandbox.py` make the check run on the candidate. The model saying "green" is never enough; the independent check decides.
- **Anonymization before publication.** `anon_check.py` refuses files carrying a private name, a personal path, an address, or a secret. `anon_review.py` has the local model reread each file. `send_rules.py` decides what may leave for a third-party model: labels instead of personal data, nothing at all when a secret is found. `release_check.py` stages the public tree and runs the last checks.
- **The refusal loop.** `refusal_loop.py` turns every new refusal into a todo line and blocks a commit while a tool logs no refusal or the bench has a false refusal or a hole. A wrong refusal becomes a patch and a bench case.
- **Per-model notes and configuration.** `model_notes.py` records model quirks. A configuration of three JSON files that a project may only tighten (`config_check.py`). A token receipt per session (`usage_report.py`).

## Honest status

It is not economical today. The bench in `public/bench/` (20 small tasks, 3 conditions, 3 repetitions each, 180 runs total) shows:

| Condition | Solved | USD per solved task |
|---|---|---|
| `alone` | 60/60 | 0.0150 |
| `discipline` | 59/60 | 0.0138 |
| `frugal` | 58/60 | 0.0273 |

On these small tasks, FrugalFlow costs more than the orchestrator alone, and context discipline alone is the cheapest condition. A second bench on the four `tests` tasks only: 12/12 solved, 0.410 USD instead of 0.912, still above `alone` (0.175 USD). In practice most briefs given to the delegate were wrong and the guards produced false refusals; that consumed mostly turns. Full-scale trials could not be run. The optimization is still to do. No saving is claimed until a bench shows one. All runs, disappointing ones included, are published in `public/bench/results/`.

## What the benchmarks prove

Seven per-tool benches (B1 to B7) ran on neutral made-up sets, each with a verdict criterion written down before the run. Three tools are proven; the others are not, and one was harmful as first built. The verdict column is the strict one: where a criterion was met only after the set was written or tuned with knowledge of earlier results, it says not proven.

| Bench | Tool | Key figure | Verdict |
|---|---|---|---|
| B1 | `anon_check.py` | Planted leaks delivered: 16.2 % (13/80) with the tool, 42.5 % (34/80) with a model reread alone, 100 % with no check; 0 false positives on 40 decoys | **Proven** |
| B2 | `verify_rules.py` | Hollow checks refused: 80.0 % on the first set (6.7 % good checks wrongly refused); after two tuning loops 47.6 % (10/21) on a fresh set | **Not proven** |
| B3 | external oracle (`delegate.py --verify`) | Model announced green on failing work: 1.7 % (1/60) on single-call tasks; 3.3 % and 8.3 % on agent tasks; 10.0 % (6/60) on a second set; after the oracle loop, 0 wrong delivered | **Not proven** |
| B4 | `fidelity.py` | Lines with drifted typography: 69.9 % (498/712) without the tool, 0.0 % (0/712) with it; no content line changed (replay counts, see the line-count note in `public/bench/fidelity/README.md`) | **Proven** |
| B5 | `brief_check.py` | First-attempt success: 24.4 % with a faulty brief, 97.8 % with the corrected one (+73.3 points); 0 false refusals on 45 sound briefs | **Proven**, within the limit below |
| B6 | `read_intake` read guard | Input tokens 0.94x of the unguarded run, same tasks solved | **Not proven** |
| B7 | session note / resume | Tokens 1.86x with a vault to explore (harmful as built); 0.77x after correction, 4 of 10 projects at or under 0.7x | **Not proven** |

Why each verdict, plainly:

- **B1.** The criterion (30 points fewer leaks than no check) is a low bar, and the tool's rules file knows the planted private names while the reread does not, which favours the deterministic tool on names. Capital-letter names, split keys and base64 evaded both. Before one correction (documentation values such as `@example.com` and reserved IP blocks raised false alarms) the first 60-file run gave 3/20 false positives and was not proven; the verdict rests on the corrected tool and a 120-file set that includes 60 new files.
- **B2.** The judge works on the patterns it was tuned on (100 % on the sets that shaped it) and fewer than half on commands it had not seen. The honest reading is that a pattern list does not generalise.
- **B3.** The first easy set could not tell (the model almost never lied). A second, subtler set of tasks was then written after seeing the easy results; it reached exactly the 10 % threshold for the local model. Because that set was built knowing the first outcome, the result is promising, not proven: it needs a pre-registered set. The only fully proven fact is that every false green seen was caught by the oracle (0 wrong delivered), at 1.0 to 1.2x tokens. The second set's figure for a remote model (6/25) is partial: the account ran out of credit.
- **B4.** The original tool left 26 % of lines drifted; a second pass fixed that. Limit: it also cancels a typographic change you ask for on purpose, and it compares line by line.
- **B5.** Limit that matters: the fault tested is, by construction, a removed piece of information the oracle needs. The bench shows the tool catches that fault (45/45) without false refusals; it does not show how many real briefs are faulty that way, nor that it catches faults its rule list does not know. One delegated model.
- **B6.** The model already reads large files in pieces; the hook refuses a whole read of a 2 500-line file, but per task the ratio ranges from 0.56 to 1.70, which is noise around no saving.
- **B7.** The vault made the agent read more, not less. Pasting a short summary into the prompt recovered a quarter of the tokens but missed the pre-set 30 % criterion. The projects are small with a complete spec, so the state is cheap to reread anyway.

Taken together with the bench of the whole toolkit above: **on a verification task, FrugalFlow is justified only where a bench proves it**, that is, anonymization checking, typographic fidelity and brief checking. Everywhere else the cost is real and the saving is not shown.

Replaying (offline recomputation from the published raw results, or a fresh run with your own model):

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
# B6, B7  raw lines and per-run token files are published (reading/, memory/); no one-command report exists
```

Raw outputs of B3 (single-call) and B4 are published as reports, not as the raw runs; a fresh run needs your own model server.

## Install

Prerequisites:

- Python 3.11 or newer (standard library only; no package to install). 3.11 is the floor because `import_betterleaks.py` reads TOML with `tomllib`.
- Claude Code.
- At least one delegated model: a local OpenAI-compatible server (LM Studio, vLLM, llama.cpp, Ollama) or a remote one with an API key kept in an environment variable (config files only name the variable).

Clone the repository, then, from the folder that holds `public/`:

```
python3 public/bin/frugalflow.py init --lmstudio-url http://localhost:8000
python3 public/bin/frugalflow.py doctor
python3 public/bin/frugalflow.py new-project demo --root ~/projects
```

`doctor` prints one `OK`, `INFO` or `WARN` line per check; a `WARN` saying the engine does not answer is expected until your model server runs, and nothing else needs it for the tests below.
`init` starts in `observe` mode: rules watch and log but **do not block anything**. `doctor` shows the effective guard mode on its own line and warns loudly while it is `observe`; `python3 public/bin/frugalflow.py mode active` turns enforcement on. See [`public/QUICKSTART.md`](public/QUICKSTART.md).

To run the test suites:

```
python3 public/tests/e2e_anonymizer.py
```

Each suite prints one `PASS` or `FAIL` line per step, then a summary line, and exits 0 only when every step passed. Run everything (every tool's `--autotest`, then every `e2e_*.py`) with

```
python3 public/tests/run_all.py            # exits 1 if any item failed, after running all
python3 public/tests/run_all.py --fail-fast  # stops at the first failure
```

The runner judges only the exit code of each item, never the words it prints; `public/tests/e2e_run_all.py` proves this with an injected failure. The same command runs in CI (`.github/workflows/tests.yml`, Python 3.11 and 3.12, no key, no model). Verify a single tool with `python3 public/bin/<tool>.py --autotest`.
To check a tree before sharing it, check a clean copy (no `.git`, no cache files), for example:

```
git clone . ../ff-check && rm -rf ../ff-check/.git
python3 public/bin/release_check.py check --tree ../ff-check --skip-e2e
```

The last line is `RELEASE READY` when every check passes (without `--skip-e2e` it also replays the end-to-end suites on a temporary copy).

## Known limits

There is no system isolation. The working folder used to verify a candidate is a temporary folder, not a sandbox. `verify_sandbox.py` strips sensitive variables, applies a time limit, and reports any write into the project, but it does not prevent one. See [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md).

Only tested with a local OpenAI-compatible server and Claude Code.

## Documentation

- [`docs/PIPELINE.md`](docs/PIPELINE.md)
- [`public/QUICKSTART.md`](public/QUICKSTART.md)
- [`public/ARCHITECTURE.md`](public/ARCHITECTURE.md)
- [`public/SCHEMA_JSON.md`](public/SCHEMA_JSON.md)
- [`public/THREAT_MODEL.md`](public/THREAT_MODEL.md)
- [`public/NOTICE.md`](public/NOTICE.md)
- [`public/CREDITS.md`](public/CREDITS.md)
- [`public/bench/README.md`](public/bench/README.md)
- [`public/examples/brief_template.md`](public/examples/brief_template.md)

## Contributing

Three kinds of contribution, described in [`CONTRIBUTING.md`](CONTRIBUTING.md):

- Propose a brief rule.
- Report a model pitfall.
- Report a false refusal.

Every change keeps the tests green and adds a bench case when a refusal was wrong.

## License

MIT. See [`LICENSE`](LICENSE). Reused work is credited in [`public/CREDITS.md`](public/CREDITS.md).
