---
description: Run the FrugalFlow closing pass (frugalflow close)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
frugalflow close
```

If `frugalflow` is not on the PATH, say so and ask the user to run it from their clone: `python3 public/bin/frugalflow.py close`.

This command checks the vault and says whether the handoff is ready. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it.
