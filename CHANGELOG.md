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

## [0.1.0] - 2026-09-17

The first release. Its files have since been withdrawn from the Python Package
Index.
