# Changelog

Notable changes to `open-contract-ml`, newest first, in the Keep a Changelog
format. The package version and the version of the Contract a release
implements are separate numbers: `opencontractml.__version__` is the first,
`opencontractml.verify.CONTRACT_VERSION` the second.

## [Unreleased]

### Changed

- `open-contract-ml check` holds every manifest to the contract-v1 manifest
  schema this package ships, `schemas/contract-v1/manifest.schema.json`, which
  it did not read before. A manifest the schema rejects is no longer
  conformant (new rule `M018`): a missing required key such as `lineage`, an
  `id` that breaks the id pattern, an `invocation.timeout_s` of zero, or an
  `uncertainty.form`, input `file_kind` or `modality` outside its enumeration.
  The checker applies the schema with its own standard-library walker, so it
  still needs nothing beyond the standard library; a schema it cannot apply in
  full is an error (new rule `E003`), never a skip. Three of the producer
  fixture copies fail `M018` and are kept as they are, with their findings
  recorded in `tests/fixtures/producer_packages/known-findings.json`, which
  the suite and the CI `package` job hold each copy to exactly.
- Every file a manifest names must be inside the package directory: an
  artifact path, the `model_card` and the `validation.report` that is
  absolute, or that resolves outside the package through `..` or a symbolic
  link, is a finding (`M012`, `M009`, `M010`), and the checker neither hashes
  nor reads it. An artifact's `bytes` must be a non-negative integer (`M012`);
  before, any other value silently skipped the byte-count comparison.
- A `float` input or output must state its `units` (`M004`, `M005`); a
  dimensionless quantity says so, for example `units: dimensionless`. An
  input's `range` must run from a smaller to a larger bound (`M004`): a
  reversed or zero-width range was accepted before.
- The falsifier benchmark (`examples/falsifier-benchmark/`) names its d=5
  verdict values for the quantities they hold and prints the `[V12]` verdict
  classes as explains, other way and neither; no number it computes changed.
  Its captured output stays the original run's, with a dated note at the top
  that maps the labels it still carries.
- The falsifier benchmark states the tolerance unit of its IC-1 check, one
  standard deviation of the chosen configuration's five CV-fold NRMSEs, as
  its own, both above that check's table and in its how-to-read block. Its
  captured output carries the same two lines, edited by hand rather than
  re-run, so every number in it is still the original run's.
- Examples and docs: the problem-spec contract defines the rule ids of its
  `reads` column where they first appear, and the other files that use them
  point there; the corpus-consumer walkthrough reproduces the mesh-only
  corpus failure with an empty rules file; the corpus-consumer README no
  longer qualifies field targets with labels it never defines.
- Wording in the package: the checker's module docstring, a docstring and a
  comment of the manifest validator, and the model-card template describe
  the applications that use a package without naming one.

## [0.1.1]

### Added

- `CHANGELOG.md`, which the source distribution carries; `CONTRIBUTING.md`
  (setting up, running the checks, amending the Contract); `SECURITY.md`
  (reporting a vulnerability, and the safe-loading policy); and `CLAUDE.md`,
  working notes for coding agents.
- `FG11` resolves to `B6_integrated_quantities` in
  `opencontractml.verify.LEGACY_ALIASES` and in the vocabulary that
  `open-contract-ml vocabulary` emits. It is the cloud ladder's
  integrated-quantities check, which that ladder used to call `FG7`. A new
  map, `RETIRED_ALIASES` (vocabulary key `legacy_aliases_retired`), records
  the rename, and `legacy_key("cloud", "FG7")` still returns
  `B6_integrated_quantities`, so a report written before it stays readable.

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
  require; it said nine. The rewording changed no key, type or constraint.
- `opencontractml.gate`: two V3 declarations are renamed to say what they hold.
  `validation_anchor` is the independent evidence the model is to be validated
  against beyond its training corpus, such as physical test data; the reference
  package's `C4_deployment_readiness` check declares it under the same name.
  `validation_anchor_status` says whether that evidence is available yet.
  `inference_target` is unchanged. Only these three names are read, and the
  model card's `V3` block carries them: a rules file written for 0.1.0 names the
  anchor and its status differently and fails V3 until it uses these names.
- `open-contract-ml check`: the `V011` message says the two validation
  ladders' reproducibility tolerances are four orders of magnitude apart, as
  the specification does (1e-6 against 2e-2); it said three.
- `opencontractml.model_card` requires the same eleven H2 sections as
  `open-contract-ml check` (rule `C003`): it reads them from
  `opencontractml.verify.CARD_SECTIONS`. 0.1.0 required nine, so a card that
  passed `load_model_card`, `opencontractml.manifest.load_model` or
  `python -m opencontractml.manifest` now also needs
  `## Training configuration` after `## Architecture` and `## Provenance`
  after `## Known failure modes`. The package's model-card template carries
  both sections.
- `open-contract-ml check`: rules `V010` (the A3 UQ-calibration check) and
  `V011` (the A5 reproducibility check) grade only a check that ran. A check
  reported as `NOT_RUN` is skipped by both, as `NOT_APPLICABLE` already was;
  in 0.1.0 both rejected it for lacking measurements that a check which did
  not run cannot have. `NOT_RUN` still blocks: the recomputed `overall` is
  `FAIL`, and `V008` rejects a report that declares otherwise.
- The package-v1 manifest schema accepts letters of either case after the
  first character of an input name: `inputs[].name` matches
  `^[a-z][A-Za-z0-9_]*$`, where 0.1.0 required `^[a-z][a-z0-9_]*$`. A unit
  suffix can keep its case (`peak_temp_K` for kelvin, rather than
  `peak_temp_k`, which reads as kilo). Every name 0.1.0 accepted is still
  accepted.
- `opencontractml.cc_common` names its tuple of the five corpus target
  columns (`T_max_K`, `T_min_K`, `T_mean_K`, `pass_fail_status`,
  `margin_K`) `CORPUS_TARGETS`. 0.1.0 exported the same tuple under a
  different name, which this release does not provide.
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

### Removed

- The `gap` subcommand: `open-contract-ml gap`, also run as
  `python -m opencontractml.verify gap`. It compared the Contract's
  requirements with other producers' source checkouts at machine-specific
  default paths, which an installed package does not have. `check`, `rules`
  and `vocabulary` remain.

## [0.1.0] - 2026-09-17

The first release. Its files have since been withdrawn from the Python Package
Index.
