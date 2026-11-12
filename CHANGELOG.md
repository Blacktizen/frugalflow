# Changelog

## 0.1.7

- Guard: `eval` bodies, python subprocess calls and git alias bodies are
  judged as shell commands; aliases built from a frugalflow substitution are
  followed (I1).
- `git rm --cached` is free in a vault (I2).

Found by: independent adversarial review (5 bypasses).

## 0.1.6

- Guard: a frugalflow subcommand given by a command substitution is resolved
  when the substitution is a literal echo (H1).
- Every other substitution form is refused rather than guessed.

Found by: independent adversarial review (3 bypasses).

## 0.1.5

- Guard: a frugalflow command hidden behind a substitution, an alias or a
  link is judged as frugalflow (F1).
- Guard: same-command variables are resolved; frugalflow settings run through
  `eval`, `xargs`, `sh -c`, hidden heads and links called by name are refused
  (G1).
- A protected file copied into a folder is judged by its final name (G2).
- `git rm` in a vault is refused, except `--cached` (F2).

Found by: independent adversarial review (13 bypasses).

## 0.1.4

- Guard: every python option before the script is scanned; sub-tools refuse
  under Claude Code without a terminal (D1); readers and commit messages are
  free, interpreter bodies stay judged (D12).
- Hooks run `python -I` and doctor checks it; `.pth`, `usercustomize.py` and
  `sitecustomize.py` are protected (D2).
- Delegate replays the host rule before any route (D3); receipts carry
  `models_path` and `models_sha256` (D7).
- The install manifest, its backups and the session logs are protected;
  uninstall only restores inside the install folders (D4, D5).
- Git in a vault: `read-tree`, `checkout-index`, `cherry-pick`, `revert`,
  `am`, `stash pop/apply`, `worktree add` and `reset --keep/--merge` are
  refused (D6); branch creation is free (D11).
- Commands over 1000 segments are refused fast (D8); `verify_worktree` fails
  closed past the watch limit and watches `.git/config` and hooks (D9); more
  code extensions, file names and late shebangs (D10).

Found by: independent adversarial review (12 bypasses).

## 0.1.3

- Guard: FrugalFlow setting changes are refused through any interpreter or
  shell form (C1); disarm by env only with `allow_env_disarm`; the guard's own
  code is protected (C11, C12).
- Guard: folders holding protected files and vault markers are protected
  (C2, C3, C7, C9); dependency folders are skipped in the container walk, and
  the vault walk-up stops before HOME.
- Guard: `git -C`/`--work-tree` and vault-aware destructive git refusals
  (C4, C10, C19).
- Guard: notebook cells, wider code extensions, byte and cumulative
  thresholds.
- R1 lifts only on a real journal entry (C6) and recognises git global
  options (C16).
- Delegate: `--models` only for bench or the home models.json, receipt records
  its path and sha256 (C5); location and trust follow the endpoint host (C8);
  ceilings always from FRUGALFLOW_HOME.

Found by: independent adversarial review (19 bypasses).

## 0.1.2

- Protected zone: paths are compared by casefold, NFC and inode (C1); the
  case-folding bypass on macOS is closed.
- Reading gate: Bash writes into reading vaults are gated like Write, with an
  attestation after a refused unresolved write; the gate is armed on install
  and flagged in doctor (C2).
- Journal and settings guards stay active in disarmed mode; Claude settings
  files and `.githooks` are protected from the assistant.
- The guard hook closes when its interpreter is gone (C6); `same_target`
  matches absolute targets only.

Found by: independent AI review session of 0.1.1 (case folding bypass on macOS).

## 0.1.1

- Packaging and version fixes.

## 0.1.0

- First public toolkit (MIT).
