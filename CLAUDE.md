# Notes for coding agents

For an AI coding agent, or anyone, about to change this repository. `README.md`
says what the package is, and `CONTRIBUTING.md` covers setup, the checks and
amending the specification; this file says what the tests hold a change to, and
what not to do.

## What is here

The Contract (`docs/spec/CONTRACT-v1.md`) and its checker
(`src/opencontractml/verify.py`, standard library only); the package-v1
validators (`manifest.py`, `model_card.py`); a scalar gate engine (`gate.py`,
`corpus_gate.py`, `train_b1.py`); two safe loaders (`safe_artifact.py`,
`safeload.py`); a conformant reference package (`examples/reference-package/`);
and copies of producer packages the checker must keep accepting
(`tests/fixtures/producer_packages/`).

## Commands

```console
python -m pip install -e ".[dev]"     # Python 3.11+: pytest, build and the [gate] extra
python -m pytest -q -rs               # the suite; -rs prints each skip and its reason
python -m opencontractml.verify check examples/reference-package tests/fixtures/producer_packages/*/
python -m opencontractml.verify rules
python -m opencontractml.manifest examples/brake_disc_tmf_v1
python -m build
```

Two tests fail on a fresh install, for reasons `.github/workflows/ci.yml` gives;
CI deselects them and fails if either starts passing. Any other failure is
yours to explain.

## What the tests hold a change to

- **Provenance.** Every file that `git ls-files --cached --others
  --exclude-standard` lists has a record in `PROVENANCE.yaml` with the sha256
  of its bytes (`tests/test_provenance.py`). For a tracked file the test hashes
  the copy in the index, so an edit is invisible to it until it is staged:
  stage the file, then re-pin it. A new file needs its record before the next
  test run, not only before the commit.
- **Negative tests.** Every `ERROR` rule of the checker has a mutation in
  `tests/test_verify.py` that makes it fire.
- **Pinned artifacts.** The files of `examples/reference-package/` and
  `tests/fixtures/producer_packages/` are pinned by sha256 and byte count in
  their manifests (rule `M013`), and `.gitattributes` keeps them LF. An edit
  there is re-pinned in the manifest, in `PROVENANCE.yaml` and, for a producer
  fixture, in its README.
- **References.** No relative markdown link may leave the tracked tree, every
  `[AuthorYear]` citation needs a row in `docs/REFERENCES.md`, and third-party
  text is cited rather than copied (`tests/test_link_integrity.py`,
  `tests/test_provenance.py`). The provenance test also rejects a retired name
  for the Contract.
- **Pickle.** No file but `safe_artifact.py` and its test calls `pickle.load`,
  `pickle.loads`, `joblib.load` or `dill.load`, or passes `allow_pickle=True`
  (an AST test in `tests/test_safe_artifact.py`).
- **One section list.** The package-v1 card validator and the checker share
  `verify.CARD_SECTIONS`, the eleven sections of a model card.

## Never

- Loosen a rule, a threshold or a test to make a package pass. A gate that
  cannot fail is the defect this repository exists to catch.
- Re-pin a digest to cover a change you did not mean to make.
- Add a flag, environment variable or any other switch that lets the safe
  loaders read an untrusted pickle. The only escape hatch is a caller naming a
  file's exact sha256.
- Give `opencontractml.verify` a dependency outside the standard library.
- Commit build output, virtual environments, datasets, model weights or caches.
- Tag a release, publish to PyPI, or add a publishing step to CI; releases are
  the maintainer's.
- Rewrite or force-push `main`.
- Put personal data, credentials, hostnames or paths from your own machine into
  the tree, a commit message or a pull request.

## Before a pull request

Run the suite and the checker, build the package, run `git diff --check`, add a
line under `[Unreleased]` in `CHANGELOG.md` for anything a user would notice,
and say in the pull request what changes for someone who uses the package.
