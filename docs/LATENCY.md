# Hook latency

What the FrugalFlow PreToolUse hook costs on every Claude Code tool call.

## How this is measured

`public/bench/latency/latency_bench.py` initializes a throwaway FrugalFlow home
in active mode, then runs the installed hook command — `python3 -I public/bin/guard_hook.py --hook`
with the tool-call JSON on stdin — once per measured call, exactly as Claude Code launches it.
Five call kinds, each with a realistic payload that the guard allows: `Read` (read a file),
`Write` (a new file), `Edit` (replace a string), `Bash_simple` (`ls -l`), and `Bash_pipeline`
(a five-segment command with a pipe, `&&` and a redirect to `/dev/null`). Wall time per call
with `time.perf_counter`; p50 and p95 are the values at rank ceil(0.50 n) and ceil(0.95 n)
of the sorted list, max is the worst call.

Replay:

```bash
python3 public/bench/latency/latency_bench.py --runs 50 --json latency.json
```

## Results

Measured 2026-11-12 on macOS-26.6.2, Python 3.14.5, 50 runs per kind:

| Kind | p50 ms | p95 ms | max ms |
|---|---|---|---|
| Read | 31.0 | 35.5 | 38.4 |
| Write | 31.9 | 32.5 | 33.8 |
| Edit | 32.2 | 32.8 | 33.1 |
| Bash_simple | 33.4 | 34.0 | 34.4 |
| Bash_pipeline | 47.0 | 47.6 | 47.6 |

## Reading the numbers

One allowed call costs about 31 to 47 ms at the median, of which about 13 ms is the fresh
`python3 -I` interpreter startup measured on its own; a five-segment shell pipeline costs
about 14 ms more than a plain `ls`, the guard's parsing of each segment. Over a 200-tool-call
session the hook adds roughly 6 to 9 seconds in total — real, but small next to the model's
own time per call.
