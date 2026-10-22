# Quickstart

Five commands, from a fresh machine to a closed session. Run them from the folder that holds `public/`.
Every tool answers `--notice` (what it reads, writes, and what already went wrong); read one only when a step fails.

## 1. Install

```bash
python3 public/bin/frugalflow.py init --lmstudio-url http://127.0.0.1:8000
python3 public/bin/frugalflow.py doctor
```

`--lmstudio-url` takes any OpenAI-compatible server (LM Studio, vLLM, llama.cpp, ...), with or without `/v1`.
`init` writes four settings files in `~/.frugalflow` (models, preferences, guard, anonymization), the FrugalFlow block in
`~/.claude/CLAUDE.md` and its hook in `~/.claude/settings.json`; it starts in `observe` mode.
When the server answered, `init` prints `SET local-reader endpoint ...`: the local model is ready.
Otherwise edit `endpoint` and `name` of `local-reader` in `~/.frugalflow/models.json`, then run `doctor` again.

Settings: `frugalflow.py config` lists every preference with its meaning; `frugalflow.py mode active` turns the rules on.

## 2. A project

```bash
python3 public/bin/frugalflow.py new-project demo --root ~/projects
```

creates `~/projects/demo` with its memory vault and the project hooks (session log, end-of-turn receipt, closing guard).

## 3. Delegate work to the local model

Start from the brief template: it passes every rule of the brief checker.

```bash
cp public/examples/brief_template.md ~/projects/demo/task.md     # then replace the task, keep the Rules section
cd ~/projects/demo
python3 <path>/public/bin/delegate.py --role code --file task.md --out count_words.py --verify 'python3 "$FRUGALFLOW_CANDIDATE" --autotest'
```

Nothing reaches the target file until `--verify` passes. A refused brief lists each rule with how to fix it.

## 4. Close the session

The closing reads the session log, and only a Claude Code session started IN the project folder writes one
(`cd ~/projects/demo && claude`: the project hooks log every event in `~/.frugalflow/sessions/<date>/<session id>.jsonl`).
Commands run outside such a session leave no log, so there is nothing to close. From inside the session:

```bash
ls -t ~/.frugalflow/sessions/*/*.jsonl | head -1      # the current session: its file name is the session id
python3 <path>/public/bin/session_digest.py --session <session id> --vault ~/projects/demo/vault
```

It exits 0 with `SESSION HEALTHY`, or says what is missing: a decision without a verdict gets one with
`session_note.py --session <id> --target <seq> --state DONE --text "..."`.

## When something blocks

Every refusal or failure is logged in `~/.frugalflow/blocks/<tool>.jsonl`. That log is how the tool's notice gets
its next PITFALLS line: report it, do not work around it.
