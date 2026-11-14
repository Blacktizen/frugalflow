---
description: Run the FrugalFlow closing pass (frugalflow close)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
python3 -I "${CLAUDE_PLUGIN_ROOT}/public/bin/plugin_hook.py" frugalflow close
```

This command checks the vault and says whether the handoff is ready. It changes no FrugalFlow setting: never add `mode`, `config`, `on` or `off` to it.
