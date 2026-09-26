# Contributing to open-contract-ml

This repository ships a specification, the Contract (`docs/spec/CONTRACT-v1.md`),
and the checker that enforces it (`opencontractml.verify`). Most changes are a
fix to the checker or the library, a new or corrected example, or an amendment
to the specification. Each one arrives as a pull request against `main`.

## Setting up

Python 3.11 or later:

```console
python -m venv .venv
. .venv/bin/activate                  # Windows: .venv\Scripts\activate
python -m pip install -e ".[dev]"
```

`[dev]` installs pytest, build and the `[gate]` extra (numpy, pandas,
scikit-learn). `opencontractml.safeload` also needs the `[tensors]` extra
(torch, safetensors); the suite does not install it.

## Running the checks

```console
python -m pytest -q -rs
python -m opencontractml.verify check examples/reference-package
python -m opencontractml.verify check tests/fixtures/producer_packages/*/
python -m build
python -m pip install twine && python -m twine check dist/*
```

`check` exits 0 when a package is conformant and 1 when it is not, naming each
rule that failed. `-rs` prints every skipped test with its reason: a test that
needs an optional dependency skips when the dependency is absent, and a skipped
test has checked nothing.

Two tests are known to fail on a fresh install. `.github/workflows/ci.yml`
names them, says why, deselects them, and fails the build if either one starts
passing, so the list can only shrink.

On every pull request, CI runs the suite on Python 3.11 on Linux, builds the
wheel, and runs the installed checker from outside the checkout. Python 3.12,
3.13 and Windows run weekly and on manual dispatch.

## What a change must keep true

- **A gate must be able to fail.** A new `ERROR` rule comes with a mutation in
  `tests/test_verify.py` that makes exactly that rule fire;
  `test_every_error_rule_has_a_negative_test` fails otherwise.
- **Every file has a provenance record.** Adding, editing or removing a file
  means adding, re-pinning or removing its record in `PROVENANCE.yaml`: the
  sha256 of its committed bytes and why it is here. `tests/test_provenance.py`
  fails otherwise.
- **Pinned artifacts stay byte-exact.** The files of `examples/reference-package/`
  and `tests/fixtures/producer_packages/` are pinned by sha256 and byte count
  in their manifests (rule `M013`), and `.gitattributes` keeps them LF. Re-pin
  an artifact you edit; never let an editor change its line endings.
- **Nothing dangles.** A relative markdown link must point at a tracked file,
  and every `[AuthorYear]` citation needs a row in `docs/REFERENCES.md`
  (`tests/test_link_integrity.py`). Third-party text is cited, never copied.
- **The checker needs only the standard library**, so it runs from a bare
  interpreter in any CI.
- **User-visible changes are recorded** in `CHANGELOG.md` under
  `[Unreleased]`.

## Amending the Contract

The specification is versioned `MAJOR.MINOR` (section 7 of
`docs/spec/CONTRACT-v1.md`): a MINOR change is additive, because consumers
ignore keys they do not know, and a MAJOR change is breaking, because consumers
refuse a major they do not support. To propose one, open an issue that states
the problem, the text you would change, whether the change is MINOR or MAJOR,
and which packages would stop or start conforming. The pull request that makes
it changes the specification, the checker, the schemas under
`src/opencontractml/schemas/` (regenerating `contract-vocabulary.json` with
`python -m opencontractml.verify vocabulary --out src/opencontractml/schemas/contract-v1/contract-vocabulary.json`),
the tests and `CHANGELOG.md` together, so the text and the checker never
disagree.

## Licence

This repository is licensed under the Apache License, Version 2.0 (`LICENSE`;
`NOTICE` reproduces the notice of its one MIT-licensed component). Unless you
state otherwise, a contribution you submit for inclusion is licensed under the
same terms, as section 5 of the licence provides, with no additional terms or
conditions.
