# Reading guard

## Question

Does the read guard `read_intake` (through the hook) cut input tokens?

## Method

Hook with only the `intake` check on, 8 log/inventory tasks x 3 repetitions, driven by
a remote hosted model. Condition C0 has the hook off, C1 has it on. The task files are 2 500
lines each (not 5-50 k), so the guard has only a moderate read to refuse.

## Results

| condition | input tokens | solved | turns |
| --- | ---: | ---: | ---: |
| C0 | 3 403 936 | 24/24 | 167 |
| C1 | 3 190 312 | 24/24 | 186 |

Ratio C1/C0 input tokens: 0.94.

Per-task ratio C1/C0 input tokens:

| task | ratio |
| --- | ---: |
| t09 | 0.94 |
| t10 | 0.78 |
| t11 | 0.56 |
| t12 | 1.70 |
| t13 | 1.06 |
| t14 | 1.37 |
| t15 | 1.20 |
| t16 | 0.76 |

## Verdict

**NOT PROVEN** (the ratio sits at 0.94, inside the 0.9-1.1 band). The hook was shown
to refuse a whole read of a 2 500-line file, but across these tasks it does not cut
tokens enough to claim a saving.

Raw lines: `results/c0.jsonl`, `results/c1.jsonl`; per-rep tokens in `b6_tokens.txt`.
