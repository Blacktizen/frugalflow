---
description: Print the FrugalFlow handoff for a new session (frugalflow resume)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
python3 -I "${CLAUDE_PLUGIN_ROOT}/public/bin/plugin_hook.py" frugalflow resume
```

This command reads the vault and the sealed journal and prints the handoff. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it.
