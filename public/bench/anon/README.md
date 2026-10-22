# Bench: does `anon_check` stop leaks that a reread by a model would let through?

120 small files (code, markdown, json, log): 80 carry one planted leak, 40 are clean files built to look suspicious.
Everything is made up and neutral; the planted secrets are assembled at run time from masked fragments, so the repository
itself never contains one.

| Condition | What checks the files |
|---|---|
| C0 | nothing |
| C1 | `anon_review.py`: a local model rereads each file |
| C2 | `anon_check.py`: the deterministic pattern scan |
| C3 | C1 and C2 together |

Leak types (10 files each): private name from the rules list, personal path, e-mail, private IP, API key, token, host name,
third-party file reference. 20 of the 80 are hard: case changed, split over two lines, base64-encoded, or inside a comment.
A leak counts as caught when an alert falls on its line (plus or minus one). A clean file is a false positive when it has any alert.

Measured result (`results/report_120_measured.json`, replayed with these exact scripts in `results/report_120_replay.json`):

| | leaks delivered | 95 % interval | false positives | seconds |
|---|---|---|---|---|
| C0 | 100.0 % | 95.4 - 100 | 0 / 40 | 0 |
| C1 | 42.5 % | 32.3 - 53.4 | 2 / 40 | 415 |
| C2 | 16.2 % | 9.7 - 25.8 | 0 / 40 | 10 |
| C3 | 3.8 % | 1.3 - 10.5 | 2 / 40 | 426 |

The model reread catches every name, path and e-mail but none of the private IPs or tokens; the pattern scan is the reverse.
Read this with its limits: the rules file lists the planted names (as a user's would), the model is told nothing, and the hard
cases that neither tool sees (a name in capitals, a key split over two lines, a base64 blob) are delivered by both.

```bash
python3 public/bench/anon/gen_b1.py --pools public/bench/anon/pools_b1.json --out /tmp/anon --seed 251
python3 public/bench/anon/run_b1.py collect --corpus /tmp/anon/corpus --truth /tmp/anon/verite.json \
  --rules public/bench/anon/anon_rules_bench.json --models YOUR_MODELS.json --bin public/bin --out /tmp/anon/collected.json
python3 public/bench/anon/run_b1.py report --truth /tmp/anon/verite.json --collected /tmp/anon/collected.json
```
`pools_b1_b.json` with `anon_rules_bench_b.json` and `--seed 252` is the second half (new values, new decoys).
Both scripts have `--autotest`.
