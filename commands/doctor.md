---
description: Run the FrugalFlow health checks (frugalflow doctor)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
python3 -I "${CLAUDE_PLUGIN_ROOT}/public/bin/plugin_hook.py" frugalflow doctor
```

This command prints one line per check. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it, and never fix a WARN by editing a setting — report the line instead.
