# Bench: typographic drift when a model rewrites a text, and what `fidelity.py` gives back

30 short neutral texts (15 French, 15 English, 8 lines each) full of curly apostrophes, quotes, dashes, ellipses and
non-breaking spaces. The model is asked to replace one word everywhere and change nothing else. Each output line is compared
with the expected text: exact, typography-only difference, or other.

| | exact lines | typography-only lines | other |
|---|---|---|---|
| C0, raw output (90 runs, 712 lines) | 214 | 498 (69.9 %) | 0 |
| C1, after `fidelity.py --write` | 712 | 0 (0.0 %) | 0 |

Line counts, reconciled: 30 texts x 3 repetitions x 8 lines = 720 lines expected. The first reports (`report_original_tool.json`,
`report_after_fix.json`) count 720 lines (68.1 % drifted without the tool). The replay with the published tool
(`report_replay.json`) counts 712 lines (69.9 % drifted, 498/712) because one run changed the number of lines
(`structure_changed` = 1) and its 8 lines are not compared. The figures quoted in this repository are those of the replay
(712 lines). The 720 lines and the 68.3 % quoted before are superseded: 68.3 % is reproduced by neither report.

Lines whose content was changed by `fidelity.py`: 0 (the tool only gives typography back; the folded text of every line is unchanged).
The first version of the tool only repaired lines the model had left untouched; the lines it had changed (3 of 8 here) kept their
straight quotes, and 26 % of the lines were still damaged (`results/report_original_tool.json`). `restore_line` repairs the
untouched pieces of a changed line too (`results/report_after_fix.json`, then `results/report_replay.json` with this tool).

Limits: it undoes a typographic change you asked for on purpose (turn the straight quotes into curly ones), and it compares
by line, so a model that reflows paragraphs defeats it.

```bash
python3 public/bench/fidelity/gen_b4.py --pools public/bench/fidelity/pools_b4.json --out /tmp/fid --seed 251 --n 30
python3 public/bench/fidelity/run_b4.py run --texts /tmp/fid --reps 3 --bin public/bin --models YOUR_MODELS.json \
  --fidelite public/bin/fidelity.py --out /tmp/fid/res.json
python3 public/bench/fidelity/run_b4.py report --result /tmp/fid/res.json --texts /tmp/fid
```
