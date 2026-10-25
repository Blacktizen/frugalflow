# B3 pre-registered: results (night run, measurement of 25/10/2026, 02:18 to 02:38)

Pre-registration: `B3-PREREG.md` (commit 385d0dd, before any measurement). Deviations: `B3-DEVIATIONS.md` (D1 to D5).
Sole means: the local model (a local quantized model, effort medium). No remote-model calls.

## Verdict per the pre-registration (read by `report.py`, no judgment)
**USEFUL PROVEN**, at the exact threshold and with a strong reservation (see "Fragility").

| Metric | Value | Pre-registered threshold |
|---|---|---|
| Valid tasks / trials | 30 / 120 (4 complete rounds) | 30 tasks, 4 reps |
| GREEN announcements on the 1st trial | 120 / 120 (0 RED, 0 without announcement) | - |
| False greens C0 (GREEN + oracle red) | 12 / 120 = 10,0 % | >= 10 % |
| 95% Wilson CI of the rate | 5,8 % to 16,7 % | lower bound >= 5 % |
| 1st response that passes the oracle (R0) | 90,0 % | - |
| Resolved in 3 trials at most (R1) | 100 % (all at the 2nd trial at most) | C1 failure <= 2 % |
| False deliveries with the oracle (FG1) | 0 / 120 | - |
| Tokens C0 (1st responses) / C1 (all) | 228 853 / 254 957 | ratio <= 2,0 |
| Token ratio C1 / C0 | 1,11 | <= 2,0 |
| Tokens per correct delivery | 2 119 (C0) / 2 125 (C1) | - |
| Infra | 0 | - |

Duration of the measurement: 20 minutes for 120 trials and 12 retries. Tokens of the local model: 255 k for the measurement; approximately 0,35 M to build the benchmark (58 generations) and the 3 tools. Dollar cost: 0.

## What produces the false greens (per task)
12 false greens on 5 tasks only; 25 tasks: 0 false green over 100 trials.
- t16 `parse_ranges`: 4 / 4. The oracle expects `ValueError` for spaces inside an interval ("1 - 3"); the task statement only says "spaces around elements permitted". Oracle plausibly too strict.
- t20 `human_join`: 3 / 4. The model writes "a, b and c" instead of "a, b, and c": the task statement is clear, genuine model error.
- t07 `flatten`: 2 / 4. The model returns `{'': {}}` for an empty first-level dict; the task statement does not resolve this case. Oracle debatable.
- t19 `title_case`: 2 / 4. Small words in hyphenated compounds: genuine error, clear rule.
- t31 `normalize_path`: 1 / 4. `../../foo` overwrites to `foo`: genuine error.

## Fragility (post-hoc analysis, NOT pre-registered, to be read as such)
- 12 / 120 = 10,0 % precisely: the threshold is met without margin. A single false green fewer would have yielded NOT PROVEN.
- The trials of a given task are not independent (4 trials per task, 4 tasks concentrate 11 false greens out of 12). The Wilson CI assumes independence; at the task level, 5 / 30 = 16,7 % have at least one false green, and the actual lower bound is wider than 5,8 %.
- If one removes the two tasks whose oracle is debatable (t16, then t07), the same script yields NOT PROVEN: 8 / 116 = 6,9 % (CI 3,5 to 13,0), then 6 / 112 = 5,4 % (CI 2,5 to 11,2). I do not retain it as a verdict (removing post-hoc is exactly what the pre-registration forbids), but it shows that the "useful proven" rests on two oracles that are too strict.
- What holds in all cases: when the model announces GREEN incorrectly, the oracle catches it every time (12 / 12) on the second trial, for 11 % more tokens. The model never announces RED (120 / 120 GREEN): its announcement carries no information, therefore trusting it (C0) delivers 7 to 10 % wrong code on this benchmark.

## Limitations
- A single model, a single quantization, a benchmark of 30 small functions written by a model (the oracles too, controlled only by the validity guard: naive red, reference green). Two oracles out of thirty are plausibly stricter than the task statement.
- Two-stage benchmark: 5 tasks out of 35 excluded before measurement, 3 generations instead of 2 (D1) to reach 30.
- The launcher is that of the local model as delivered (4 self-tests out of 5 green at measurement time, D3; 5 out of 5 after correcting the erroneous delegate of the self-test, D6) and the wrapper `delegate_wrap.py` corrects the token reading (D4). `report.py` and the launcher are in the repository; the verdict is replayable.
- C1 is the launcher loop (oracle + returned output, 3 trials), not a call to `delegate.py --verify` itself; same logic, not the same code.
- "Useful" here means: it catches false greens at low cost. It says nothing about a stronger model or larger tasks.

## Replaying
```bash
R=public/bench/oracle-prereg
FRUGAL_REAL_DELEGATE=/path/to/your/delegate.py python3 $R/runner.py.partiel.py run --tasks $R/tasks \
  --ids $(ls $R/tasks | paste -sd, -) --reps 4 --out results.jsonl --delegate $R/delegate_wrap.py
python3 $R/report.py report --results results.jsonl --ids $(ls $R/tasks | paste -sd, -)
```
(The wrapper expects a delegate whose token line is of the form `[model ... tokens]` on the error output. The published copies of the wrapper and of the launcher carry this neutral prefix instead of the name of the maintainer's own delegate tool; adapt it to yours.)

## Proposed README line (not merged)
> External oracle: on 30 pre-registered small code tasks, the local model announces "green tests" incorrectly 10 % of the time (12 / 120); the oracle catches it every time for 11 % more tokens. The threshold is met without margin and hinges on two debatable oracles: to read as "cheap, plausibly useful", not as "proven".
