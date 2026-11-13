---
description: Run the FrugalFlow health checks (frugalflow doctor)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
frugalflow doctor
```

If `frugalflow` is not on the PATH, say so and ask the user to run it from their clone: `python3 public/bin/frugalflow.py doctor`.

This command prints one line per check. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it, and never fix a WARN by editing a setting — report the line instead.
