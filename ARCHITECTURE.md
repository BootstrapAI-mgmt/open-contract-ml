# Architecture — open-contract-ml

Current-state architecture for `open-contract-ml`: the Contract v1 engineering-ML package standard, its zero-dependency conformance checker, validation/gate libraries, byte-exact repository falsifiers, out-of-tree wheel CI, and 4-pillar Governed Lightweight verification apparatus.

## Core Subsystems

1. **Standard-Library Conformance Checker (`src/opencontractml/verify.py`):** Implements the normative Contract v1.0–1.2 rules (`E001`–`E004`, `M001`–`M024`, `C001`–`C006`, `V001`–`V013`, `S001`–`S003`) using only the Python standard library (using `PyYAML` when available). Validates `manifest.yaml` with a built-in JSON Schema walker, verifies the eleven required `model_card.md` sections, recomputes `validation_report.json` comparator verdicts, enforces `M013` sha256 and byte-count artifact pins, checks `taxonomy_cell` and `taxonomy_registry` against the pinned vocabulary, executes optional `stdio_json` entrypoint smoke frames (`--smoke`), and emits machine-readable conformance records (`--json`).
2. **Validation, Gate & Safe-Deserialization Libraries (`src/opencontractml/`):**
   - `manifest.py` and `model_card.py` provide typed `package-v1` manifest and model-card validation backed by `pydantic`, `jsonschema`, and `pyyaml`.
   - `gate.py`, `corpus_gate.py`, `cc_common.py`, `train_b1.py`, and `synth_corpus.py` implement the scalar `V1`/`V2`/`V3` model validation ladder and `G1` corpus acceptance gate (`open-contract-ml[gate]`).
   - `safe_artifact.py` and `safeload.py` enforce restricted unpickling and safe tensor-checkpoint loading (`open-contract-ml[tensors]`), guarded by an AST gate in `tests/test_safe_artifact.py` forbidding unpinned `pickle.load`, `joblib.load`, `dill.load`, or `allow_pickle=True` elsewhere in the tree.
3. **Packaged Schemas, Vocabulary & Reference Artifacts:**
   - Schemas (`src/opencontractml/schemas/contract-v1/`, `src/opencontractml/schemas/package-v1/`) and `src/opencontractml/templates/model_card.template.md` ship inside the wheel via `importlib.resources`.
   - `examples/reference-package/` and `examples/reference-field-package/` (rebuilt byte-for-byte via `examples/build_reference_field_package.py --check`) provide conformant scalar and field reference packages; `examples/falsifier-benchmark/` exercises adversarial defect detection; `tests/fixtures/producer_packages/` holds real producer package fixtures pinned against `tests/fixtures/producer_packages/known-findings.json`.
4. **Repository Falsifiers (`PROVENANCE.yaml`, Link & Citation Gates, Out-of-Tree Wheel CI):**
   - `tests/test_provenance.py` requires every non-gitignored file in `git ls-files --cached --others --exclude-standard` to carry a literal path, rationale, and exact committed-blob `sha256` in [PROVENANCE.yaml](PROVENANCE.yaml), with LF line endings enforced by [.gitattributes](.gitattributes).
   - `tests/test_link_integrity.py` verifies that every relative markdown link resolves inside the tracked tree and every bibliography key resolves to [docs/REFERENCES.md](docs/REFERENCES.md).
   - [.github/workflows/ci.yml](.github/workflows/ci.yml) runs the source-tree `pytest` suite and builds the wheel, installing it into an isolated virtualenv outside the checkout to verify installed `importlib.resources` resolution against reference and producer packages.
5. **4-Pillar Governed Lightweight Apparatus (`GOVERNANCE.json`, `tools/governed/`, `governed-ci.yml`):**
   - Enforces structural documentation parity (`DOC-01`, `ARCH-01`, `ROAD-01..05`, `TC-01..08`, `DELIV-01`, `MANUAL-GATE-01`), 40-hex SHA action pinning (`ACT-PIN-01`), credential/host-path redaction (`SEC-REDACT-01`), two-mode spec/implementation/governance firewall (`GOV-FIREWALL-01..04`), deterministic PR diff substance and anti-gaming checks (`SUBSTANCE-01..05`), production-to-test mapping with zero silent exemptions and explicit legacy-debt tracking (`COV-01..03`), SHA-256 task-card acceptance-criteria receipts (`run-criteria.mjs`), pre-launch wave collision, clean-abort classification, and metered-API scrubbing (`spawn-guard.mjs`), and dual-pipeline A/B comparison telemetry (`ab-telemetry.mjs`).

## Project Structure

- `docs/spec/CONTRACT-v1.md` — Normative Contract v1.2 specification
- `docs/spec/PROVENANCE-SIGNING.md` — Detached provenance signature sidecar design note
- `docs/STANDARDS-ALIGNMENT.md` — Alignment with ASME VVUQ, DNV, NASA, BV, and MIL-STD frameworks
- `docs/standards/crosswalk-7009B-RP0513.md` — Clause-by-clause mapping of all 50 checker rules and 15 ladder keys
- `docs/REFERENCES.md` — Repository bibliography for citation keys
- `docs/EXTRACTION.md` — Provenance extraction notes and scope boundaries
- `docs/model-onboarding.md` — Producer guide for packaging and validating models
- `docs/model-packages.md` — Model registry layout and consumer validation guide
- `docs/tasks/phase-1-governed-contract.md` — Governed task-card specifications and executable acceptance criteria
- `src/opencontractml/verify.py` — Standard-library Contract v1 conformance checker and CLI entrypoint
- `src/opencontractml/manifest.py` — Typed `package-v1` manifest validator
- `src/opencontractml/model_card.py` — Model-card front-matter and 11-section validator
- `src/opencontractml/gate.py` — Scalar `V1`/`V2`/`V3` model validation gate
- `src/opencontractml/corpus_gate.py` — `G1` corpus acceptance gate
- `src/opencontractml/cc_common.py` — Shared corpus schema, loading, and statistics helpers
- `src/opencontractml/train_b1.py` — Corpus-native baseline trainer for gate verification
- `src/opencontractml/synth_corpus.py` — Synthetic corpus generator with planted defect modes
- `src/opencontractml/safe_artifact.py` — Restricted unpickling loader with exact-digest escape policy
- `src/opencontractml/safeload.py` — Safe tensor-checkpoint loader
- `src/opencontractml/schemas/contract-v1/` — Contract v1 manifest schema, conformance-record schema, rule vocabulary, and pinned taxonomy cells
- `src/opencontractml/schemas/package-v1/` — Package-v1 manifest JSON Schema
- `src/opencontractml/templates/model_card.template.md` — Canonical 11-section model-card template
- `examples/reference-package/` — Conformant scalar reference package with `M013` hash pins
- `examples/reference-field-package/` — Conformant VTK field reference package
- `examples/build_reference_field_package.py` — Deterministic builder and `--check` byte-exact verifier for the field package
- `examples/falsifier-benchmark/` — Adversarial falsifier benchmark and captured output
- `examples/worked-cells/` — Nine worked engineering data contracts and synthetic datasets
- `tests/fixtures/producer_packages/` — Producer package fixtures and `known-findings.json` ratchet
- `tests/test_verify.py` — Conformance checker suite with one negative mutation test per `ERROR` rule
- `tests/test_provenance.py` — Forward, reverse, and sha256 content falsifier over `PROVENANCE.yaml`
- `tests/test_link_integrity.py` — Tracked-tree markdown link and bibliography citation gate
- `tests/governed_smoke.test.mjs` — Node `node:test` suite verifying 4-pillar governance and firewall rules
- `PROVENANCE.yaml` — Per-file origin record and committed-blob sha256 pins
- `GOVERNANCE.json` — Declarative 4-pillar governance, firewall, and coverage configuration
- `ROADMAP.md` — Phase milestones, evidence citations, and runnable verification commands
- `package.json` — Node scripts for 4-pillar governance validation, criteria receipts, and smoke tests
- `tools/governed/check-governed.mjs` — Zero-dependency Pillar 1–3 governance and firewall validator
- `tools/governed/run-criteria.mjs` — Executable task-card acceptance-criteria runner and receipt emitter
- `tools/governed/spawn-guard.mjs` — Pre-launch wave file-collision detector and metered-API scrubber
- `tools/governed/ab-telemetry.mjs` — Dual-pipeline A/B run logger and switchover comparator
- `tools/governed/apply-branch-ruleset.sh` — GitHub branch ruleset installer for `main`
- `.github/workflows/ci.yml` — Source-tree Python test matrix and out-of-checkout wheel verification workflow
- `.github/workflows/governed-ci.yml` — SHA-pinned 4-pillar governance CI and commit-range `gitleaks` workflow
