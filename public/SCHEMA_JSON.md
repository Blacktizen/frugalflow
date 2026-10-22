# The three configuration files

FrugalFlow reads three JSON files. No other file holds a setting, and none of them holds a
secret. This page is the contract: every tool that reads a setting reads it from here, and
`bin/config_check.py` refuses a file that breaks it.

| File | Holds | Where | Who writes it |
|---|---|---|---|
| `models.json` | the models you can reach, the delegation **layers**, and the **roles** | `~/.frugalflow/` | you, or `frugalflow init` |
| `preferences.json` | your ceilings: verbosity, trust, tries, output size, task splitting | `~/.frugalflow/` | you |
| `.frugalflow.json` | per-project settings, which may only **tighten** `preferences.json` | the project root | the project |

`~/.frugalflow/` can be moved with the `FRUGALFLOW_HOME` environment variable, or with
`--home` on the command line. Examples to copy: `config/models.example.json`,
`config/preferences.example.json`, `config/project.example.json`.

## Secrets are never stored

API keys live in **environment variables**. A model entry names the variable in `key_env`;
it never holds the value. `config_check.py` refuses any file where a key whose name contains
`key`, `token`, `secret` or `password` (other than `key_env` itself) carries a non-empty
string, and any string that starts with `sk-`.

## `models.json`

```json
{
  "schema_version": "1",
  "models": [ ... ],
  "layers": [ ... ],
  "roles":  [ ... ]
}
```

### `models` — one entry per reachable model

| Key | Type | Rule |
|---|---|---|
| `id` | string | non-empty, unique; roles point to it |
| `name` | string | non-empty; the name the engine knows |
| `location` | string | `local`, `remote` or `in_session` (the assistant you are talking to) |
| `endpoint` | string | required unless `in_session` |
| `context_window` | integer > 0 | required unless `in_session`; the window the engine **really** serves |
| `paid` | boolean | |
| `trust` | string | `private`, `trusted_third_party` or `untrusted_third_party` |
| `key_env` | string | the **name** of the environment variable holding the key; `""` if none. Uppercase letters, digits and `_`, starting with a letter |
| `sampling` | object, optional | local models: sampling settings you measured (`temperature`, `top_p`, `top_k`, `min_p`, `presence_penalty`, `repetition_penalty`, numbers only); wins over the notice. Checked by `sampling_check.py` |
| `notice` | string, optional | local models: path to the publisher's `generation_config.json` or LM Studio `model.yaml`, relative to this file's folder. With neither `sampling` nor `notice`, a local delegation is **refused**: no setting is guessed |
| `max_output` | integer > 0, optional | the most output tokens asked per call; without it, `delegate.py` needs `--max-tokens` |
| `max_parallel` | integer >= 1, optional | local models: how many delegations may share the engine at once (default 1). Enforced by `engine_lock.py` |

### `layers` — the delegation layers, as data

A layer is a kind of work. Moving a role to another layer is an edit to this file, never to
code.

| Key | Type | Rule |
|---|---|---|
| `name` | string | non-empty, unique |
| `delegable` | boolean | `false` marks work that is **never** delegated |

The example ships four layers: `bulk_reading`, `code_writing`, `review`, and
`kept_judgment` (`delegable: false`).

⚠️ Confidentiality is **not a layer** you can move a role into. It is the `trust` of each
model, capped by `ceilings.max_trust`. A role can change layer; it can never gain the right to
send private content to a third party.

### `roles` — who does each job

| Key | Type | Rule |
|---|---|---|
| `name` | string | non-empty, unique |
| `layer` | string | required; must name a layer |
| `model` | string | must name a model id, **except** in a non-delegable layer, where it must be `""` |

`bin/layers.py` refuses: a role without a layer, a role naming an unknown layer or model, a
layer that no role uses, and a role in a non-delegable layer that was given a model.

## `preferences.json`

Every key is required.

| Key | Type | Meaning |
|---|---|---|
| `verbosity.final_answer_words` | integer > 0 | ceiling on the final answer |
| `verbosity.step_message_words` | integer > 0 | ceiling on a progress message |
| `ceilings.max_trust` | trust level | the least trusted model content may be sent to |
| `ceilings.max_tries` | integer > 0 | attempts before a delegation gives up |
| `ceilings.max_output_tokens` | integer > 0 | ceiling on one delegated answer |
| `splitting.max_proofs_per_task` | integer > 0 | a task needing more proofs is split |
| `splitting.max_brief_lines` | integer > 0 | a longer brief is the sign of a task too big |
| `grouping.independent_calls_same_turn` | boolean | send independent tool calls together |

## `.frugalflow.json` — may only tighten

Same keys as `preferences.json`, all optional, **except** `grouping`, which a project may not
set. Every value must be **tighter or equal**: a smaller number, or a trust level no less
private. A project file that loosens a ceiling is **refused**, never silently clamped: a
setting that is quietly ignored is a setting you believe is in force.

Trust levels, from tightest to loosest: `private` < `trusted_third_party` <
`untrusted_third_party`. An unknown level is an error, never a guess.

## Where a value came from

`config_check.py` prints every effective ceiling with its source, `(preferences)` or
`(project)`, so that a wrong value can be traced to the file that set it.

## `anonymization.json` — the operator's own leak patterns

Lives next to the other two, in `~/.frugalflow/` (or `FRUGALFLOW_HOME`, or `--rules`). It is
the only place a private name may be written: the code carries **generic forms** only
(e-mail, personal path, IP, MAC, internal host, machine name, author line, phone number;
and, refused outright, credentials, JWT, API keys, private keys, connection strings).
Example: `config/anonymization.example.json`.

| Key | Type | Meaning |
|---|---|---|
| `anonymizable` | list of `{pattern, label, tag}` | replaced by a stable label `__TAG_N__`, reversible |
| `irreducible` | list of `{pattern, label}` | never replaced: its presence refuses the file |

`pattern` is a Python regular expression that must compile and must not match the empty
string; `tag` is 2 to 12 capital letters. Any other top-level key is an **error**: a misspelt
`anonymisable` would otherwise disarm every rule under it without a word. One error empties
both lists, and `bin/anon_check.py` exits 13; a missing file exits 13 too. An empty file `{}`
is accepted: it keeps the generic forms and drops every private name, which is exactly what
the anonymizer end-to-end test proves.

## `guard.json` — the guard's settings

Read by `bin/guard_hook.py` from `FRUGALFLOW_HOME/guard.json`, else `~/.frugalflow/guard.json`.
A missing file, invalid JSON, or a missing **required** key refuses every call with a message
that names the file: the guard never runs blind. Example: `config/guard.example.json`.

| Key | Type | Default | Meaning |
|---|---|---|---|
| `code_extensions` | list of strings | **required** | file extensions treated as code, e.g. `[".py", ".sh"]` |
| `delegation_logs` | list of paths | **required** | delegation logs whose receipts let a write pass; relative paths are under `FRUGALFLOW_HOME` |
| `audit_log` | path | **required** | where each logged decision is appended, one JSON line |
| `active` | boolean | `true` | `false` lets everything pass (so does `FRUGALFLOW_GUARD=0`) |
| `line_threshold` | integer | `15` | a code write of this many lines or fewer needs no receipt |
| `receipt_minutes` | integer | `60` | how long a delegation receipt stays valid |
| `delegate_tools` | list of strings | `[]` | command names that write code legitimately (they leave the receipt) |
| `fix_hint` | string | `""` | appended to a refusal: how to delegate on this machine |
| `checks` | list of strings | all | entry checks to run, among `quarantine_read`, `intake`, `digest`; an unknown name refuses every call |
| `quarantine_minutes` | integer | `60` | a delegated file cannot be read during this time: run its test instead |
| `read_waiver_minutes` | integer | `15` | how long a read declared in the delegation log stays valid |
| `intake_active` | boolean | `true` | `false` turns the large-file read check off |
| `intake_max_lines` | integer | `400` | a file longer than this is not read whole |
| `intake_max_bytes` | integer | `60000` | same, in bytes |
| `intake_document_extensions`, `intake_image_extensions` | lists of strings | built in | extensions the read check knows |
| `digest_extensions` | list of strings | `[".md", ".log", ".txt", ".jsonl"]` | files a counting command (`sort`, `uniq -c`…) must hand to a model |
| `digest_max_bytes` | integer | `98304` | below this size, counting by hand is allowed |
| `digest_waiver` | string | `"manual-digest"` | a comment `# <waiver>: <reason>` lets one counting command pass, and is logged |

A checks list is the place to **loosen** the guard on purpose; every other key only says how
strict each check is. The guard protects against the **agent**, not against a process running
with all of the user's rights.
