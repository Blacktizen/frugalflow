# SCHEMA - the rules of ledger's memory

<!-- REQUIRED-READING
overview.md
todo.md
-->

## Rules
- ⛔⛔ One fact lives in one place: link to it, never copy it.
- ⛔⛔ raw/ is immutable: a source is never edited.
- ⛔ log.md is append-only and sealed: add entries with journal_add.py, never edit one.
- ⛔ Every live page is listed in index.md, every raw/ file is cited in sources.md.
- ⭐⭐ Before writing, restate the bearing lines of the required pages (reading_gate.py).
