# Quickstart

Under two minutes to a first useful result, then five steps to a closed session.
Every tool answers `--notice` (what it reads, writes, and what already went wrong); read one only when a step fails.

## 0. Install and scan (no model needed)

```bash
pipx install git+https://github.com/Blacktizen/frugalflow     # PyPI: pipx install frugalflow (soon)
frugalflow scan .                                               # exit 0 clean, 12 leak found
```

`frugalflow scan` finds secrets and private data in a folder or a git repo and never prints the value it found.
`--staged` scans only the git index (a pre-commit hook), `--quiet` prints one summary line, `--rules FILE` adds your own patterns.
From a clone, replace `frugalflow` by `python3 public/bin/frugalflow.py` in every command below.

## 1. Set up

```bash
frugalflow setup            # guided: detects Ollama, LM Studio, a typed endpoint, *_API_KEY names; ends with doctor
frugalflow setup --yes      # same without questions, first engine found (CI)
frugalflow uninstall        # puts every touched file back, byte for byte
```

`setup` copies every file it is about to touch into `~/.frugalflow/setup-backups` first. Options: `--engine ollama|lmstudio|openai|key|none`,
`--endpoint URL`, `--model NAME`, `--key-env VAR` (only the variable name is stored), `--mode observe|active|silent`, `--no-doctor`.
The older layer-by-layer walk is `frugalflow setup --layers`. The manual route still works:

```bash
python3 public/bin/frugalflow.py init --lmstudio-url http://127.0.0.1:8000
python3 public/bin/frugalflow.py doctor
```

`--lmstudio-url` takes any OpenAI-compatible server (LM Studio, vLLM, llama.cpp, ...), with or without `/v1`.
`init` writes four settings files in `~/.frugalflow` (models, preferences, guard, anonymization), the FrugalFlow block in
`~/.claude/CLAUDE.md` and its hook in `~/.claude/settings.json`; it starts in `observe` mode, where the guards log what they would refuse but block nothing (`doctor` prints a `WARN guard mode: OBSERVE` line until you run `mode active`). Python 3.11 or newer is required.
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
