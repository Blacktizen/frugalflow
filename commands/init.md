---
description: Mount the FrugalFlow vault in the current git repository (frugalflow init --here)
---

Run this command in the terminal with the Bash tool and show its output verbatim, without summarizing or editing it:

```
python3 -I "${CLAUDE_PLUGIN_ROOT}/public/bin/plugin_hook.py" frugalflow init --here
```

It mounts the vault of the current git repository. Inside a Claude Code session the mount is refused by design (it changes a setting): if it is refused, say so and tell the user to run frugalflow init --here in their own terminal. Never add `mode`, `config`, `on` or `off` to it.
