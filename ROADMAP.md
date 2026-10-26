# Roadmap — open-contract-ml

## Phase 0: Contract v1.0–1.2 Standard, Conformance Checker, Provenance & Wheel CI

**Status:** complete

**Evidence:** Commit `9be49b0` (`v0.3.1` standards crosswalk errata and DNV-RP-0671 / BV NI 692 / MIL-STD-3022 mappings) and commit `36258b0` (`v0.3.0` implementing Contract `1.2` taxonomy cell pinning)

**Milestone:** Ship the normative Contract v1.0–1.2 specification, zero-dependency standard-library conformance checker (`opencontractml.verify` with 50 rules and negative mutation tests for every `ERROR` rule), `package-v1` manifest and model-card validators, scalar/corpus gates, restricted safe loaders, byte-exact scalar and field reference packages (`M013`), `PROVENANCE.yaml` sha256 falsifier, tracked-tree link and bibliography gates, and out-of-checkout wheel CI.

**Verification:**
1. `python -m opencontractml.verify check examples/reference-package examples/reference-field-package` exits 0
2. `python examples/build_reference_field_package.py --check` exits 0
3. `python -m pytest tests/test_provenance.py tests/test_link_integrity.py -q` exits 0

---

## Phase 1: 4-Pillar Governed Lightweight Verification & CI Apparatus

**Status:** in-progress

**Milestone:** Bootstrap the zero-dependency 4-pillar `governed-lightweight` verification apparatus (`TC-OCM01`) in `tools/governed/` with declarative `GOVERNANCE.json` policy (`exempt: []` and explicit `legacy_untested_debt` tracked by `TC-OCM02`), single-source task cards in `docs/tasks/`, two-mode PR firewall and deterministic anti-gaming substance checks (`GOV-FIREWALL-01..04`, `SUBSTANCE-01..05`, `MANUAL-GATE-01`, `DELIV-01`, `COV-01..03`), SHA-256 acceptance-criteria receipts, and 40-char SHA-pinned `Governed CI` + commit-range `gitleaks` secret scanning alongside `.github/workflows/ci.yml`.

**Verification:**
1. `node tools/governed/check-governed.mjs` exits 0
2. `npm test` exits 0
3. `npm run check:criteria` exits 0
4. Operator activates `Governed Checks` and `Secrets (gitleaks)` required status checks on `main` via `bash tools/governed/apply-branch-ruleset.sh BootstrapAI-mgmt/open-contract-ml main` once PR #10 merges (manual: true)
