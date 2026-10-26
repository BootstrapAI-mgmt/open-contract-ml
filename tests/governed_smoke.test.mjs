import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import { validateRepo } from '../tools/governed/check-governed.mjs';
import { runCardCriteria } from '../tools/governed/run-criteria.mjs';
import { scrubMeteredEnvironment, scoreDiffRisk } from '../tools/governed/spawn-guard.mjs';
import { comparePipelines } from '../tools/governed/ab-telemetry.mjs';

const REPO_ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..');

test('open-contract-ml passes 4-pillar validateRepo checks', () => {
  const res = validateRepo(REPO_ROOT);
  assert.equal(res.passed, true, JSON.stringify(res.errors));
  assert.ok(res.stats.cards >= 1);
  assert.ok(res.stats.discoveredTests >= 50);
});

test('GOV-FIREWALL-01 blocks empty 0-file stub diffs', () => {
  const res = validateRepo(REPO_ROOT, {
    changedFiles: [],
    requireNonEmptyDiff: true,
    mode: 'impl',
    baseHasGovernance: true,
  });
  assert.equal(res.passed, false);
  assert.ok(res.errors.some((e) => e.rule === 'GOV-FIREWALL-01'));
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
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'ocm-gov-zombie-'));
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
        protected_paths: ['GOVERNANCE.json', 'tools/governed/', '.github/workflows/'],
        spec_paths: ['ROADMAP.md', 'ARCHITECTURE.md'],
        coverage: { prod_roots: ['src'], test_roots: ['tests'], exempt: [], min_test_count: 1 },
      },
      null,
      2
    )
  );
  fs.writeFileSync(path.join(dir, 'ARCHITECTURE.md'), '# Architecture\n\n## Project Structure\n\n- `src/m.py` — mod\n');
  fs.writeFileSync(
    path.join(dir, 'ROADMAP.md'),
    '# Roadmap\n\n## Phase 1: Core\n\n**Status:** in-progress\n\n**Verification:**\n1. `node -e "process.exit(0)"` exits 0\n'
  );
  fs.writeFileSync(
    path.join(dir, 'docs', 'tasks', 'phase-1.md'),
    [
      '## TC-OCM99: Completed historical governance card',
      '**Priority:** P0',
      '**Status:** complete',
      '**Governance Files Allowlist:**',
      '- `GOVERNANCE.json`',
      '**Files to create/modify:**',
      '- `GOVERNANCE.json`',
      '**Acceptance Criteria:**',
      '1. `node -e "process.exit(0)"` exits 0',
      '',
    ].join('\n')
  );
  fs.writeFileSync(path.join(dir, 'src', 'm.py'), 'X = 1\n');
  fs.writeFileSync(path.join(dir, 'tests', 'test_m.py'), 'def test_x():\n    assert True\n');
  fs.writeFileSync(
    path.join(dir, '.github', 'workflows', 'governed-ci.yml'),
    'steps:\n  - uses: actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1\n'
  );

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

test('Pillar 1/4 criteria dry-run, billing firewall scrub, and A/B comparator execute cleanly', (t) => {
  const receipt = runCardCriteria(REPO_ROOT, 'TC-OCM01', { dryRun: true });
  assert.equal(receipt.passed, true);
  assert.equal(receipt.criteria.length, 4);

  const scrubbed = scrubMeteredEnvironment({ ANTHROPIC_API_KEY: 'test-token', PATH: '/usr/bin' });
  assert.equal(scrubbed.env.ANTHROPIC_API_KEY, undefined);
  assert.deepEqual(scrubbed.stripped, ['ANTHROPIC_API_KEY']);

  assert.equal(scoreDiffRisk(['GOVERNANCE.json'], ['GOVERNANCE.json']).tier, 'high');

  const tmpJsonl = path.join(os.tmpdir(), `ocm-ab-${process.pid}.jsonl`);
  t.after(() => fs.rmSync(tmpJsonl, { force: true }));
  const cmp = comparePipelines(tmpJsonl);
  assert.equal(cmp.verdict, 'MAINTAIN_DUAL_TRIAL');
});
