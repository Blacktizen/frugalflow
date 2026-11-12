# Refusal loop

[← Back to the README](../README.md)

Every tool logs its own refusals. Each new refusal becomes a todo line, then a bench case; a wrong refusal becomes a fix that must keep every other case green (`refusal_loop`). A commit waits while a false refusal is still open. The tools improve from their own use, every day.
