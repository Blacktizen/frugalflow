# Releasing frugalflow on PyPI

Publishing is a human gesture: only the maintainer runs `twine upload`. Everything before it is
reversible and local; nothing here needs a secret except the token, which is never written
in this repository.

## 1. Build the distribution (local, no network beyond pip)

```bash
python3 -m venv .venv-build
.venv-build/bin/pip install build twine
.venv-build/bin/python -m build --outdir dist .
.venv-build/bin/twine check --strict dist/*
```

`twine check --strict` must pass for both the `.tar.gz` and the `.whl`. It checks the
long description (rendered from `docs/PYPI_README.md`), the license field and the metadata.

Smoke-test the wheel before uploading, in a throwaway environment:

```bash
python3 -m venv .venv-test
.venv-test/bin/pip install dist/*.whl
env -u CLAUDECODE HOME=/tmp/ffhome FRUGALFLOW_HOME=/tmp/ffhome/ff .venv-test/bin/frugalflow --help
env -u CLAUDECODE HOME=/tmp/ffhome FRUGALFLOW_HOME=/tmp/ffhome/ff .venv-test/bin/frugalflow run scan /tmp/ffhome
```

## 2. Create the PyPI token (once, on pypi.org)

- Sign in to <https://pypi.org>, open *Account settings → API tokens*.
- Add a token with **Scope: "Project: frugalflow"** (not "Entire account"), for both
  *PyPI* and *Test PyPI* if you test first. A project-scoped token cannot touch any
  other project if it leaks.
- Copy it into `~/.pypirc` (mode 600, never committed) or paste it at the prompt when
  `twine` asks. Never put it in a shell history-visible command, a file in the
  repository, or a CI log.

## 3. Upload

```bash
.venv-build/bin/twine upload dist/*
```

PyPI rejects a version that already exists: bump `version` in `pyproject.toml` and add a
`CHANGELOG.md` entry first, in the same commit.

## 4. Verify the published package

```bash
pipx install frugalflow
frugalflow --help
frugalflow run scan .
pipx uninstall frugalflow
```

Also check the project page: <https://pypi.org/project/frugalflow/> shows the rendered
description, the license (MIT), and the Changelog / Security / Documentation links.

## 5. Test PyPI first (optional, recommended for the first upload)

```bash
.venv-build/bin/twine upload --repository testpypi dist/*
pipx install --pip-args "--index-url https://test.pypi.org/simple/" frugalflow
```

## Notes

- `docs/PYPI_README.md` is the PyPI long description (set by `readme` in
  `pyproject.toml`); `README.md` stays the repository front page. If you change a link
  in one, check whether the other needs it too — relative links are dead on PyPI.
- The classifiers do **not** include `License :: OSI Approved :: MIT License`: PEP 639
  (setuptools ≥ 77) forbids it next to `license = "MIT"`, and the build fails if both
  are present. The license shows on PyPI through the expression and `license-files`.
- The wheel carries everything the CLI reads at runtime: `frugalflow_app/bin/*.py`,
  `config/`, `data/`, `examples/`, `hooks/`.
