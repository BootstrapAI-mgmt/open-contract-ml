import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  loadGovernanceConfig,
  validateRepo,
  evaluatePrSubstance,
} from '../tools/governed/check-governed.mjs';
import { runCardCriteria } from '../tools/governed/run-criteria.mjs';
import {
  scrubMeteredEnvironment,
  scoreDiffRisk,
  renderAgentBriefContract,
  classifySessionOutcome,
} from '../tools/governed/spawn-guard.mjs';
import { comparePipelines } from '../tools/governed/ab-telemetry.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

function makeTempGovernedRepo(t) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ocm-gov-fixture-'));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));

  fs.mkdirSync(path.join(dir, 'docs', 'tasks'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'src'), { recursive: true });
  fs.mkdirSync(path.join(dir, 'tests'), { recursive: true });
  fs.mkdirSync(path.join(dir, '.github', 'workflows'), { recursive: true });

  fs.writeFileSync(
    path.join(dir, 'GOVERNANCE.json'),
    JSON.stringify(
      {
        schema_version: 1,
        repo_prefix: 'TC-OCM',
        require_todo_master: false,
        required_status_checks: ['Governed Checks', 'Secrets (gitleaks)'],
        protected_paths: ['GOVERNANCE.json', 'tools/governed/', '.github/workflows/'],
        spec_paths: ['ROADMAP.md', 'ARCHITECTURE.md'],
        coverage: {
          prod_roots: ['src'],
          test_roots: ['tests'],
          allow_import_coverage: true,
          exempt: [],
          legacy_untested_debt: [],
          min_test_count: 1,
        },
      },
      null,
      2
    )
  );
  fs.writeFileSync(path.join(dir, 'ARCHITECTURE.md'), '# Architecture\n\n## Project Structure\n\n- `src/m.mjs` — mod\n');
  fs.writeFileSync(
    path.join(dir, 'ROADMAP.md'),
    '# Roadmap\n\n## Phase 1: Core\n\n**Status:** in-progress\n\n**Verification:**\n1. `node -e "process.exit(0)"` exits 0\n'
  );
  fs.writeFileSync(
    path.join(dir, 'docs', 'tasks', 'phase-1.md'),
    [
      '## TC-OCM98: Active feature card',
      '**Priority:** P0',
      '**Status:** in-progress',
      '**Files to create/modify:**',
      '- `src/m.mjs`',
      '**Acceptance Criteria:**',
      '1. `node -e "process.exit(0)"` exits 0',
      '',
      '---',
      '',
      '## TC-OCM99: Completed historical governance card',
      '**Priority:** P0',
      '**Status:** complete',
      '**Governance Files Allowlist:**',
      '- `GOVERNANCE.json`',
      '**Files to create/modify:**',
      '- `src/m.mjs`',
      '**Acceptance Criteria:**',
      '1. `node -e "process.exit(0)"` exits 0',
      '',
    ].join('\n')
  );
  fs.writeFileSync(path.join(dir, 'src', 'm.mjs'), 'export const X = 1;\n');
  fs.writeFileSync(
    path.join(dir, 'tests', 'm.test.mjs'),
    'import test from "node:test";\nimport { X } from "../src/m.mjs";\ntest("x", () => {});\n'
  );
  fs.writeFileSync(
    path.join(dir, '.github', 'workflows', 'governed-ci.yml'),
    'steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n'
  );
  return dir;
}

test('open-contract-ml passes 4-pillar validateRepo with zero silent exemptions', () => {
  const cfg = loadGovernanceConfig(REPO_ROOT);
  assert.deepEqual(cfg.coverage.exempt, []);
  assert.equal(cfg.coverage.allow_import_coverage, true);
  assert.deepEqual(cfg.required_status_checks, ['Governed Checks', 'Secrets (gitleaks)']);

  const res = validateRepo(REPO_ROOT);
  assert.equal(res.passed, true, JSON.stringify(res.errors));
  assert.ok(res.stats.cards >= 2);
  assert.ok(res.stats.discoveredTests >= 50);
});

test('GOV-FIREWALL-01 and SUBSTANCE-01 block empty 0-file stub diffs', () => {
  const res = validateRepo(REPO_ROOT, {
    changedFiles: [],
    requireNonEmptyDiff: true,
    mode: 'impl',
    baseHasGovernance: true,
  });
  assert.equal(res.passed, false);
  assert.ok(res.errors.some((e) => e.rule === 'GOV-FIREWALL-01'));

  const subErrs = evaluatePrSubstance([], { requireNonEmptyDiff: true });
  assert.ok(subErrs.some((e) => e.rule === 'SUBSTANCE-01'));
});

test('GOV-FIREWALL-02 blocks unattested edits to protected governance paths', () => {
  const blocked = validateRepo(REPO_ROOT, {
    changedFiles: ['GOVERNANCE.json'],
    mode: 'impl',
    tcIds: ['TC-OCM01'],
    attested: false,
    baseHasGovernance: true,
  });
  assert.equal(blocked.passed, false);
  assert.ok(blocked.errors.some((e) => e.rule === 'GOV-FIREWALL-02'));

  const allowed = validateRepo(REPO_ROOT, {
    changedFiles: ['GOVERNANCE.json'],
    mode: 'governance',
    tcIds: ['TC-OCM01'],
    attested: true,
    baseHasGovernance: true,
  });
  assert.equal(allowed.passed, true, JSON.stringify(allowed.errors));
});

test('GOV-FIREWALL-03 rejects completed zombie task-card allowlists', (t) => {
  const dir = makeTempGovernedRepo(t);
  const res = validateRepo(dir, {
    changedFiles: ['GOVERNANCE.json'],
    mode: 'governance',
    tcIds: ['TC-OCM99'],
    attested: true,
    baseHasGovernance: true,
  });
  assert.equal(res.passed, false);
  assert.ok(res.errors.some((e) => e.rule === 'GOV-FIREWALL-03'));
});

test('GOV-FIREWALL-04 blocks self-grading Acceptance Criteria and ROADMAP edits in impl mode', () => {
  const acEdit = validateRepo(REPO_ROOT, {
    changedFiles: ['docs/tasks/phase-1-governed-contract.md'],
    mode: 'impl',
    baseHasGovernance: true,
    diffTextByFile: {
      'docs/tasks/phase-1-governed-contract.md':
        '--- a/docs/tasks/phase-1-governed-contract.md\n+++ b/docs/tasks/phase-1-governed-contract.md\n-1. `npm test` exits 0\n+1. `node -e "process.exit(0)"` exits 0\n',
    },
  });
  assert.equal(acEdit.passed, false);
  assert.ok(acEdit.errors.some((e) => e.rule === 'GOV-FIREWALL-04'));

  const roadmapEdit = validateRepo(REPO_ROOT, {
    changedFiles: ['ROADMAP.md'],
    mode: 'impl',
    baseHasGovernance: true,
  });
  assert.equal(roadmapEdit.passed, false);
  assert.ok(roadmapEdit.errors.some((e) => e.rule === 'GOV-FIREWALL-04'));
});

test('evaluatePrSubstance enforces SUBSTANCE-02..05 anti-gaming checks', () => {
  const synthToken = 'Pool' + 'Simulated001';
  const skipStmt = 'test.' + 'skip("bypass suite", () => {});';
  const diffs = [
    { path: '.agent-context/brief.md', status: 'A', patch: '+transient scratch\n' },
    { path: '.agent-output/self-check.txt', status: 'A', patch: '+Repository: foreign-repo\n' },
    { path: 'replay/run1.json', status: 'A', patch: `+{"pool":"${synthToken}"}\n` },
    { path: 'evidence/log.foam', status: 'A', patch: '+PID : 1000\n+ExecutionTime = 0.25 s\n' },
    { path: 'src/eval.js', status: 'M', patch: '+if (effectiveRate < minPassRate && effectiveRate < 0.5) return false;\n' },
    { path: 'tests/skip.test.mjs', status: 'M', patch: `+${skipStmt}\n` },
    {
      path: 'tests/taut.test.mjs',
      status: 'A',
      patch: '+import test from "node:test";\n+import assert from "node:assert/strict";\n+test("sham", () => {\n+  assert.ok(true);\n+});\n',
    },
    {
      path: 'tests/test_taut.py',
      status: 'A',
      patch: '+import pytest\n+def test_sham():\n+    assert 1 + 1 == 2\n',
    },
  ];
  const errs = evaluatePrSubstance(diffs, { repoName: 'open-contract-ml', attested: false });
  const rules = errs.map((e) => e.rule);
  assert.equal(rules.filter((r) => r === 'SUBSTANCE-02').length, 2);
  assert.equal(rules.filter((r) => r === 'SUBSTANCE-03').length, 2);
  assert.equal(rules.filter((r) => r === 'SUBSTANCE-04').length, 2);
  assert.equal(rules.filter((r) => r === 'SUBSTANCE-05').length, 2);
});

test('MANUAL-GATE-01 and runCardCriteria block unattested completion on (manual: true) criteria', (t) => {
  const realReceipt = runCardCriteria(REPO_ROOT, 'TC-OCM01', { dryRun: true });
  assert.equal(realReceipt.automated_passed, true);
  assert.equal(realReceipt.pending_manual_count, 1);
  assert.equal(realReceipt.completion_eligible, false);
  assert.equal(realReceipt.criteria[4].passed, null);

  const dir = makeTempGovernedRepo(t);
  fs.writeFileSync(
    path.join(dir, 'docs', 'tasks', 'phase-1.md'),
    [
      '## TC-OCM98: Card with manual ruleset step',
      '**Priority:** P0',
      '**Status:** complete',
      '**Files to create/modify:**',
      '- `src/m.mjs`',
      '**Acceptance Criteria:**',
      '1. `node -e "process.exit(0)"` exits 0',
      '2. Operator verifies ruleset active on GitHub (manual: true)',
      '',
    ].join('\n')
  );
  const unattested = validateRepo(dir);
  assert.equal(unattested.passed, false);
  assert.ok(unattested.errors.some((e) => e.rule === 'MANUAL-GATE-01'));

  fs.appendFileSync(
    path.join(dir, 'docs', 'tasks', 'phase-1.md'),
    '\n**Manual Attestation:** Verified by operator on 2026-10-26\n'
  );
  const attested = validateRepo(dir);
  assert.equal(attested.passed, true, JSON.stringify(attested.errors));
  const eligibleReceipt = runCardCriteria(dir, 'TC-OCM98', { dryRun: true });
  assert.equal(eligibleReceipt.completion_eligible, true);
});

test('DELIV-01, COV-03, and WIRING-01 block ghost deliverables, new-file coverage exemptions, and dead islands', (t) => {
  const dir = makeTempGovernedRepo(t);
  fs.writeFileSync(
    path.join(dir, 'docs', 'tasks', 'phase-1.md'),
    fs.readFileSync(path.join(dir, 'docs', 'tasks', 'phase-1.md'), 'utf8').replace('- `src/m.mjs`\n**Acceptance Criteria:**\n1. `node -e "process.exit(0)"` exits 0\n\n---\n\n## TC-OCM99', '- `src/m.mjs`\n**Acceptance Criteria:**\n1. `node -e "process.exit(0)"` exits 0\n\n---\n\n## TC-OCM99')
  );
  // Point completed TC-OCM99 at a missing deliverable -> DELIV-01
  const cardPath = path.join(dir, 'docs', 'tasks', 'phase-1.md');
  const origCards = fs.readFileSync(cardPath, 'utf8');
  fs.writeFileSync(
    cardPath,
    origCards.replace(
      '## TC-OCM99: Completed historical governance card\n**Priority:** P0\n**Status:** complete\n**Governance Files Allowlist:**\n- `GOVERNANCE.json`\n**Files to create/modify:**\n- `src/m.mjs`',
      '## TC-OCM99: Completed historical governance card\n**Priority:** P0\n**Status:** complete\n**Governance Files Allowlist:**\n- `GOVERNANCE.json`\n**Files to create/modify:**\n- `src/missing_deliverable.mjs`'
    )
  );
  const rDeliv = validateRepo(dir);
  assert.ok(rDeliv.errors.some((e) => e.rule === 'DELIV-01'));
  fs.writeFileSync(cardPath, origCards);

  // Add newly created file listed in legacy_untested_debt -> COV-03 blocks it on status: 'A'
  const cfgPath = path.join(dir, 'GOVERNANCE.json');
  const cfg = JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
  cfg.entrypoints = ['src/m.mjs'];
  cfg.coverage.legacy_untested_debt = ['src/new_untested.mjs'];
  fs.writeFileSync(cfgPath, JSON.stringify(cfg, null, 2));
  fs.writeFileSync(path.join(dir, 'src', 'new_untested.mjs'), 'export const u = 2;\n');

  const rCov03 = validateRepo(dir, {
    changedFiles: ['src/new_untested.mjs'],
    fileDiffs: [{ path: 'src/new_untested.mjs', status: 'A', patch: '+export const u = 2;\n' }],
    mode: 'impl',
    baseHasGovernance: true,
  });
  assert.ok(rCov03.errors.some((e) => e.rule === 'COV-03'));
  assert.ok(rCov03.errors.some((e) => e.rule === 'WIRING-01'));
});

test('classifySessionOutcome, renderAgentBriefContract, scrubMeteredEnvironment, and comparePipelines operate deterministically', (t) => {
  const brief = renderAgentBriefContract({ cardId: 'TC-OCM02', targetRepo: 'open-contract-ml' });
  assert.match(brief, /AGENT_ABORT:/);
  assert.match(brief, /SUBSTANCE-05/);

  const aborted = classifySessionOutcome({
    exitCode: 1,
    stdout: 'AGENT_ABORT: torch wheel unavailable in offline sandbox',
    changedFiles: [],
  });
  assert.equal(aborted.status, 'aborted_cleanly');
  assert.equal(aborted.retryable, false);
  assert.equal(aborted.escalateHitl, true);
  assert.equal(aborted.reapDraftPr, true);

  const emptyExit = classifySessionOutcome({ exitCode: 0, stdout: 'done', changedFiles: [] });
  assert.equal(emptyExit.status, 'failed_empty_diff');

  const scrubbed = scrubMeteredEnvironment({ ANTHROPIC_API_KEY: 'test-token', PATH: '/usr/bin' });
  assert.equal(scrubbed.env.ANTHROPIC_API_KEY, undefined);
  assert.deepEqual(scrubbed.stripped, ['ANTHROPIC_API_KEY']);

  assert.equal(scoreDiffRisk(['GOVERNANCE.json'], ['GOVERNANCE.json']).tier, 'high');

  const tmpJsonl = path.join(os.tmpdir(), `ocm-ab-${process.pid}.jsonl`);
  t.after(() => fs.rmSync(tmpJsonl, { force: true }));
  const cmp = comparePipelines(tmpJsonl);
  assert.equal(cmp.verdict, 'MAINTAIN_DUAL_TRIAL');
});
