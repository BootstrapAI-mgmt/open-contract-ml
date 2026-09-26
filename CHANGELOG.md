# Changelog

Notable changes to `open-contract-ml`, newest first, in the Keep a Changelog
format. The package version and the version of the Contract a release
implements are separate numbers: `opencontractml.__version__` is the first,
`opencontractml.verify.CONTRACT_VERSION` the second.

## [Unreleased]

### Added

- `CHANGELOG.md`, which the source distribution carries; `CONTRIBUTING.md`
  (setting up, running the checks, amending the Contract); `SECURITY.md`
  (reporting a vulnerability, and the safe-loading policy); and `CLAUDE.md`,
  working notes for coding agents.

### Changed

- `opencontractml.safeload` keeps a checkpoint's non-tensor payload (`kind`,
  `config`, `norm`, `extra`) in the safetensors metadata under the key
  `__opencontractml__`, with the format name `opencontractml-safetensors-1`, and
  reads only that key. A checkpoint written by 0.1.0's `save_checkpoint` used a
  different key, which this release does not read: `load_checkpoint` returns
  that file's tensors under `state_dict` and none of its saved payload, without
  an error. To migrate such a file, read its metadata with
  `safetensors.safe_open(path, framework="pt").metadata()` (the payload is the
  one entry whose value is a JSON object with `format`, `state_key` and
  `payload` fields) and write the rebuilt checkpoint back with
  `save_checkpoint`. No compatibility alias is provided.
- The package-v1 manifest schema's descriptions say what each field means
  rather than how one particular application displays it, and the
  `model_card` description names the eleven sections the card validators
  require; it said nine. No key, type or constraint changed.
- `opencontractml.gate`: two V3 declarations are renamed to say what they hold.
  `validation_anchor` (formerly `rung4_anchor`) is the independent evidence the
  model is to be validated against beyond its training corpus, such as physical
  test data; the reference package's `C4_deployment_readiness` check declares
  it under the same name. `validation_anchor_status` (formerly
  `stage8_status`) says whether that evidence is available yet.
  `inference_target` is unchanged. The model card's `V3` block carries the new
  names and, until 0.2.0, the former names beside them.
- `open-contract-ml check`: the `V011` message says the two validation
  ladders' reproducibility tolerances are four orders of magnitude apart, as
  the specification does (1e-6 against 2e-2); it said three.
- The brake-disc worked example's model card (`examples/brake_disc_tmf_v1/`)
  marks its training-data source, its sampling bias and its cited validation
  report as illustrative; no such dataset or report exists.
- Worked cells and docs: comments that pointed at rules or notes outside this
  repository now name what they meant, and `docs/STANDARDS-ALIGNMENT.md`
  describes the Contract's licence in the present tense. Every generator
  still writes byte-identical data.
- Tests: names that still counted nine card sections, and comments that
  described an application outside this repository, are reworded. No test's
  behaviour changed.

### Deprecated

- `rung4_anchor` and `stage8_status` in the `v3` block of a gate rules file,
  and the same keys in the model card's `V3` block. A rules file that uses them
  is still read, with a `DeprecationWarning`; both are removed in 0.2.0.

## [0.1.0] - 2026-09-17

The first release. Its files have since been withdrawn from the Python Package
Index.
