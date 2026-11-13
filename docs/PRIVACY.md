# Privacy and anonymization

[← Back to the README](../README.md)

Before anything goes to a hosted model, including models hosted abroad, `anon_check` refuses names, personal paths, addresses and secrets, and `send_rules` decides what may leave. `frugalflow scan` finds secrets in a folder or a repo, with no model and no setup, and works as a pre-commit hook or a CI step.

When a rule flags a value that is actually public — a repository URL that contains the owner handle, for example — the project declares it in `.frugalflow-public`, at the root of the scanned folder (the git root with `--staged`): one exact literal per line, `#` for comments, values shorter than 8 characters ignored with a warning. A finding is set aside only when the text it recognized sits entirely inside an occurrence of a declared value on the same line; the same word elsewhere on that line is still a leak, so the rule stays armed everywhere else. The number of set-aside matches is reported on the `CLEAN` or `FOUND` line, and the declaration file itself is never scanned.
