# Phase 1 Task Cards — Governed Lightweight Apparatus

## TC-OCM01: Bootstrap 4-pillar governed-lightweight verification & CI apparatus

**Priority:** P0
**Status:** in-progress

**Governance Files Allowlist:**
- `GOVERNANCE.json`
- `tools/governed/`
- `.github/workflows/`

**Files to create/modify:**
- `.gitignore`
- `.github/workflows/governed-ci.yml`
- `ARCHITECTURE.md`
- `CHANGELOG.md`
- `GOVERNANCE.json`
- `PROVENANCE.yaml`
- `ROADMAP.md`
- `docs/tasks/phase-1-governed-contract.md`
- `package.json`
- `tests/governed_smoke.test.mjs`
- `tools/governed/ab-telemetry.mjs`
- `tools/governed/apply-branch-ruleset.sh`
- `tools/governed/check-governed.mjs`
- `tools/governed/run-criteria.mjs`
- `tools/governed/spawn-guard.mjs`

**Acceptance Criteria:**
1. `node tools/governed/check-governed.mjs` exits 0
2. `npm test` exits 0
3. `npm run check:criteria` exits 0
4. `python -m pytest tests/test_provenance.py tests/test_link_integrity.py -q` exits 0
5. Operator activates `Governed Checks` and `Secrets (gitleaks)` required status checks on `main` via `bash tools/governed/apply-branch-ruleset.sh BootstrapAI-mgmt/open-contract-ml main` once PR #10 merges (manual: true)

---

## TC-OCM02: Close legacy unit-test debt on safeload.py, corpus_gate.py, synth_corpus.py, and cc_common.py

**Priority:** P1
**Status:** not-started

**Governance Files Allowlist:**
- `GOVERNANCE.json`

**Files to create/modify:**
- `GOVERNANCE.json`
- `PROVENANCE.yaml`
- `tests/test_cc_common.py`
- `tests/test_corpus_gate.py`
- `tests/test_safeload.py`
- `tests/test_synth_corpus.py`

**Acceptance Criteria:**
1. `python -m pytest tests/test_cc_common.py tests/test_corpus_gate.py tests/test_safeload.py tests/test_synth_corpus.py -q` exits 0
2. `node tools/governed/check-governed.mjs` exits 0 with `"legacy_untested_debt": []` in `GOVERNANCE.json`
3. `python -m pytest tests/test_provenance.py tests/test_link_integrity.py -q` exits 0
