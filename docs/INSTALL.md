# Install

[← Back to the README](../README.md)

![Terminal demo: install, scan finds a planted key, setup --yes, doctor is green](demo.svg)

Three commands, about two minutes. Python 3.11 or newer is the only prerequisite.

```
pipx install git+https://github.com/Blacktizen/frugalflow    # works today, no PyPI needed
frugalflow scan .                                              # step 2: the door in, no model needed
frugalflow setup                                               # step 3: guided, ends with doctor
```

Without pipx: `python3 -m venv ~/.ff && ~/.ff/bin/pip install git+https://github.com/Blacktizen/frugalflow`, then run `~/.ff/bin/frugalflow`. Coming soon: `pipx install frugalflow` from PyPI (soon, not published yet).

**Start with `scan`.** `frugalflow scan [PATH]` looks for secrets and private data (API keys, private key blocks, passwords in clear, personal paths, e-mail and IP addresses) in a folder or a git repo. It needs no model, no key and no setup. It prints one line per leak with file, line, type and label, never the value found. Exit code 0 means clean, **12 means a leak was found**, so it works as a pre-commit hook or a CI step:

```
frugalflow scan .                 # a folder or a repo (git-aware: it respects .gitignore)
frugalflow scan --staged .        # only what is staged: the pre-commit form
frugalflow scan --quiet .         # one summary line
```

Pre-commit hook (`.git/hooks/pre-commit`, then `chmod +x`): `exec frugalflow scan --staged "$(git rev-parse --show-toplevel)"`. CI step: `frugalflow scan .`. Your own names and patterns go in `~/.frugalflow/anonymization.json`, or pass `--rules FILE`.

**Then `setup`.** `frugalflow setup` detects Ollama (:11434), LM Studio (:1234), a typed OpenAI-compatible endpoint (`--endpoint URL`) and any `*_API_KEY` variable (only its name is stored, never its value), asks which one to use, copies every file it is about to touch into `~/.frugalflow/setup-backups`, writes the configuration, and finishes with `doctor`. `frugalflow setup --yes` takes the first engine found without asking (for CI). `frugalflow uninstall` puts every file back as it was, byte for byte; a file you edited since is kept and only the FrugalFlow block is cut out of it. The older walk over the model layers is now `frugalflow setup --layers`.

**From a clone.** Everything also runs from a checkout, with the same arguments, as `python3 public/bin/frugalflow.py COMMAND`, and `python3 public/tests/run_all.py` runs the tests.

`doctor` prints one `OK`, `INFO` or `WARN` line per check; a `WARN` saying the engine does not answer is expected until your model server runs, and nothing else needs it for the tests. `init` starts in `observe` mode: rules watch and log but **do not block anything**. `doctor` shows the effective guard mode and warns while it is `observe`; `frugalflow mode active` turns enforcement on. Start a project with `frugalflow new-project demo --root ~/projects`. See [`public/QUICKSTART.md`](public/QUICKSTART.md).

`run_all.py` exits 1 if any item failed, after running all (`--fail-fast` stops at the first). It judges only exit codes, never the words a test prints. Verify one tool with `python3 public/bin/<tool>.py --autotest`.

To check a tree before sharing it, use a clean copy with no `.git` and no cache files:

```
git clone . ../ff-check && rm -rf ../ff-check/.git
python3 public/bin/release_check.py check --tree ../ff-check --skip-e2e
```

The last line is `RELEASE READY` when every check passes.
