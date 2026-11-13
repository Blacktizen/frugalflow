---
description: Print the FrugalFlow handoff for a new session (frugalflow resume)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
frugalflow resume
```

If `frugalflow` is not on the PATH, say so and ask the user to run it from their clone: `python3 public/bin/frugalflow.py resume`.

This command reads the vault and the sealed journal and prints the handoff. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it.
