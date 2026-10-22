# FrugalFlow threat model

Draft of the security model for FrugalFlow, the tool that lets a paid coding assistant
delegate bulky work (reading, writing code, triaging) to cheaper models, local or remote,
without dropping the security bar. It is written for the operator who installs the guard.

The guard works on one principle: it fails closed. A crashed check, a failed shell
analysis, an unreadable delegation log, an unreadable write target — every doubt refuses,
with a "To fix:" line that says how to repair it. Nothing is let through because the
guard could not decide.

## Scope

This model covers what the guard protects:

- **The project code.** Source files the operator works on. The guard refuses to write
  code that did not come from a recent, successful delegation. A receipt covers only its
  exact file, and the content must match what was delegated.
- **The operator's secrets.** Environment variables and files outside the project. They
  are never sent to a model, and a verification check runs without sensitive variables.
- **The guard's own logs.** The delegation log (`delegations.jsonl`, the receipts), the
  refusal logs under `blocks/` (one per refusing tool, plus `guard.jsonl`), and the guard
  settings (`guard.json`). They are the proof of what was delegated and what was refused;
  only the delegation tool may write them.
- **Private data sent to a third-party model.** Names, paths, addresses and secrets must
  not leave for a remote model: they are labelled or refused before sending.

A receipt is the line the delegation tool writes to the delegation log when a verified
candidate replaces its target; the guard checks that receipt before it allows any later
write to that file.

The operator's settings live outside the repository, under the home directory, as
`models.json`, `preferences.json` and `anonymization.json`; an optional project file may
only tighten the ceilings. API keys are read from the environment variable that
`models.json` names (`key_env`); the key itself is never written to a configuration file.

## Actors and trust

- **Operator** — trusted. They own the machine, the keys, the settings and the ceilings.
  They choose what may be delegated and to whom.
- **Main assistant** (the paid coding assistant) — limited trust. It may be wrong or be
  manipulated, so none of its tool calls is taken on faith: every one goes through the
  guard hook before it runs.
- **Delegated models** — a local model is private: its answers stay on the machine. A
  remote model is a third party and is not trusted. Three trust levels exist:
  `private`, `trusted_third_party`, `untrusted_third_party`.
- **Content that is read** (files, notes, web pages, tool outputs) — DATA, never
  instructions. A note that says "write this file" is data; the write it seems to ask
  for still has to pass the guard like any other.

## Trust boundaries

- **The guard hook, before every tool call.** The PreToolUse hook reads the call, asks
  the guard rules for a decision, writes one line to the audit log, and prints the
  refusal on stdout when the call is denied. It always exits 0. It also refuses a call
  that writes, deletes, moves or links the guard's own logs.
- **The send to a model.** Outbound text is filtered by trust level: everything to a
  private model, labels instead of personal data to a third party, and nothing (a
  refusal) when a secret is found. The labels are stable, so the model's answer can be
  put back into the original text afterwards.
- **The `--verify` check in a temporary working folder.** A delegation's check runs in a temporary folder
  holding only the useful files, without sensitive variables, under a time limit; the
  folder is removed afterwards. It is not isolated from the system: the check can still read any file its user can read. Any write it still makes into the project is reported.
- **The commit gate.** The pre-commit hook runs the notice check, the anonymization scan and the
  language check on the staged files and blocks the commit if one is refused, so a tool cannot be
  committed without a conforming notice, and a private name or secret cannot be committed by accident.

## Threats and mitigations

The first column names the threat, the second the control that stands in its way, and
the third the replayable attack that proves the control still bites.

On the happy path, a delegation runs like this: the assistant writes a task file;
`delegate.py` sends it to the role's model; the answer lands in a candidate file next to
the target; the `--verify` check runs on that candidate in a temporary working folder, without system isolation; only a
verified candidate replaces the target, atomically; and one line, with its duration, is
added to the delegation log. Each threat below tries to step around one link of this
chain.

| Threat | Mitigation | Test |
|---|---|---|
| Writing code without a delegation. | The guard refuses: a code file of more than a few lines must come from a recent, successful delegation (`guard_rules`, `shell_rules`). | `juge_attaques`, E2E |
| Forging a receipt or disarming the guard by writing its logs. | `journal_guard` refuses any call that writes, deletes, moves or links a protected guard file; only the delegation tool writes them. | `attaque_forge1` |
| The verification writes into the project, reads secrets, or never ends. | `verify_sandbox` runs the check in a temporary folder with only the useful files, without sensitive variables, under a time limit; exit code 124 on timeout, 125 when it wrote into the project. | `attaque_verify_isole` |
| Writing through a symbolic or hard link, or `--out` into a guard file. | `delegate.py` resolves the real path, refuses guard paths, creates the candidate exclusively and replaces the target atomically. | `attaque_d4b` |
| Private data leaks to a third-party model. | Anonymization by trust level: labels instead of personal data, refusal when a secret is found. | anonymizer attacks |
| Disguised writes (exec, eval, a target taken from the environment, renaming into code). | Closed mode: a write of code whose target cannot be read is refused. | `attaque_trous_anciens` <!-- lang-ok --> |
| An instruction injected into a note or a file that is read (prompt injection). | Read content is never an instruction; any write it would cause still passes through the guard. The reading gate never takes a page from `raw/`, reads `SCHEMA.md` only at the vault root, and skips lines hidden in YAML front matter, code blocks and comments. | `attaque_note_piegee` |
| An unlogged refusal stops the tools from improving. | Every refusal writes its line: `block_log` appends the refused input, `exit_log` logs every non-zero exit. | `attack_refus_journalises`, E2E security suite |

## Known limits

- A script run as `python3 script.py` is not inspected: the guard judges the command and
  its inline code, not the contents of a script named in the command. Inline code is
  judged statically: a write whose target is not a readable literal (or a constant bound
  to a name) is refused, and so is code run through `exec`, `eval`, `compile` or
  `runpy`, or reached through a namespace dictionary (`__dict__`, `vars`, `globals`).
- A secret whose name does not look sensitive is not removed. The anonymizer labels only
  what its lists recognize, so an unrecognized secret leaves unchanged; a recognized name
  (a connection string such as `DATABASE_URL`) refuses the whole send instead.
- The guard judges text. It does not contain a determined attacker who controls the
  machine or the assistant's own process.
- An agent without operating-system isolation can read everything its user can read: the guard
  gates writes, not reads.

## Out of scope

The model assumes the ground it stands on is intact. The following are trusted anchors,
not things the guard defends:

- Compromise of the machine or of the assistant's own process.
- Compromise of the models themselves (their engines or their answers).
- Compromise of a package repository or any dependency supply chain.

## Status

Draft, 2026-10-03.

Every row of the threats table points to a replayable attack. The attacks are rerun
together before every commit of the project, with the end-to-end suites and
`guard_probes.py` (the probes of the previous guard, one fresh home per probe): an attack
that turns red means a hole was opened again. A fix that lifts a false refusal is
accepted only if a bank of disguised writes, replayed against the old and the new guard,
shows no new pass. The document will tighten as the attack suite grows.
