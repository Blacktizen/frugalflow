# Contributing

FrugalFlow is built from receipts: a claim without a proof is not accepted, and a green test
that was never shown red is not a check. This page says where each kind of contribution goes
and what makes it acceptable.

## Propose a brief rule

A brief is the task file you hand to a delegated model. `public/bin/brief_check.py` refuses a
brief that breaks a rule of `public/config/brief_rules.json`, and names each broken rule with
how to fix it. A proposed rule must show what it catches and what it must not catch:

1. Reproduce the bad brief first: `frugalflow.py lint mytask.md` must pass it today.
2. `frugalflow.py lint --explain RULE_ID` shows how the neighbouring rules read; the new rule
   must not contradict them.
3. Add the rule to `public/config/brief_rules.json` with its examples, and make
   `public/bin/brief_bench.py` show the rule biting: red before the fix, green after.

Start from `public/examples/brief_template.md`: it passes every rule, and its Rules section is
what the checker reads.

## Report a model pitfall

Every model has quirks - a window it does not really serve, a sampler that ignores a setting,
a phrasing it misreads. Record the quirk where the next operator will find it:

```bash
python3 public/bin/frugalflow.py notes add-pitfall ...
python3 public/bin/frugalflow.py notes show
python3 public/bin/frugalflow.py notes measure
```

A pitfall without its proof - the command, the model, what happened - is a rumor, and the
notes tools refuse it. `notes check` validates the proofs; `notes merge` folds duplicates.

## Report a false refusal

The barrier refuses mechanically, and a refusal that was wrong costs the operator real work.
Every refusal is already logged, one file per refusing tool, under `~/.frugalflow/blocks/`.
To report one: copy the refused line, say what you were doing, and say what the right answer
was.

A confirmed false refusal enters the refusals' loop (`public/bin/refusal_loop.py`): it becomes
a line of patch to the rule that misfired, and a case added to the bank of disguised writes
that every guard fix is replayed against - a fix is accepted only when the bank shows no new
pass. Do not work around a refusal; report it.

## Tests and receipts

- Each feature ships an end-to-end suite in `public/tests/` (for example `public/tests/e2e_bench.py`):
  it builds a fresh temporary scene, runs the real tool as a subprocess, reads the real exit
  code, prints one PASS or FAIL line per test, and exits 0 only when every test passed.
- Before a suite is trusted, the code it covers is deliberately broken and the suite must go red.
  `public/bin/bite.py` runs that proof and alone writes the receipt in `public/tests/bite/`.
- The bench (`public/bench/README.md`) is the test of the whole promise: run it on your own
  machine with `public/bin/bench_run.py` and `public/bin/bench_report.py`, and publish the
  run, disappointing or not.

## Rules for every change

- English only. `public/bin/lang_check.py` refuses French leftovers and stray accented words.
- No personal data anywhere in the repository. `public/bin/anon_check.py` run with `--scan`
  checks the tree; private names live only in the operator's own `anonymization.json`, never
  in code.
- No secret in any config file: keys are environment variables named by `key_env`
  (`public/SCHEMA_JSON.md`), and `public/bin/config_check.py` refuses a file that breaks this.
- Every tool in `bin/` answers `--notice` with its five sections; `public/bin/notice_check.py`
  enforces the contract at commit time, through the hook installed by
  `public/bin/install_hooks.py`.
- Fail closed: a change that makes a check guess instead of refuse is refused, even when it
  removes friction. A default that guesses manufactures a false red.
- A change to the guard is accepted only with its attack replayed: the rows of
  `public/THREAT_MODEL.md` point to replayable attacks, rerun before every commit.
