#!/usr/bin/env node
/**
 * Governed Lightweight Validator (`check-governed.mjs`)
 *
 * Distills Command Center's 500K-LOC governance surface + HTD's doc linter into a
 * zero-dependency <400-LOC Node.js gate (<100ms runtime) enforcing:
 *   - Pillar 1: Spec, Cross-Doc, Runnable Falsifier, SHA-Pinning & Secret/PII Integrity
 *   - Pillar 2: Two-Mode Adversarial Governance Firewall (`impl` vs `spec` vs `governance`),
 *               0-file stub rejection, spec-oracle immutability, and active-only TC allowlists
 *   - Pillar 3: Production-to-test file mapping (`COV-01`) & non-vacuous test floor (`COV-02`)
 */

import fs from 'node:fs';
import path from 'node:path';
import { execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';

const VALID_STATUSES = new Set(['not-started', 'in-progress', 'complete', 'superseded', 'blocked']);
const TERMINAL_STATUSES = new Set(['complete', 'completed', 'superseded', 'done', 'closed']);
const COMMAND_VERBS = new Set([
  'node', 'npm', 'npx', 'python', 'python3', 'pytest', 'bash', 'sh',
  'git', 'grep', 'rg', 'test', '[', 'curl', 'cargo', 'go', 'tsc',
]);

export function loadGovernanceConfig(root) {
  const cfgPath = path.join(root, 'GOVERNANCE.json');
  if (!fs.existsSync(cfgPath)) {
    return {
      schema_version: 1,
      repo_prefix: 'TC',
      protected_paths: ['GOVERNANCE.json', 'tools/governed/check-governed.mjs', 'tools/governed/run-criteria.mjs', '.github/workflows/'],
      spec_paths: ['ROADMAP.md', 'ARCHITECTURE.md'],
      coverage: { prod_roots: ['src'], test_roots: ['tests'], exempt: [], min_test_count: 1 },
      banned_subjective_terms: ['fast enough', 'looks good', 'works well', 'seamless', 'intuitive', 'polished'],
    };
  }
  return JSON.parse(fs.readFileSync(cfgPath, 'utf8'));
}

export function isRunnableCommandSpan(text) {
  const spans = [...text.matchAll(/`([^`]+)`/g)].map((m) => m[1].trim());
  for (const span of spans) {
    const first = span.split(/\s+/)[0];
    if (COMMAND_VERBS.has(first) && (span.includes(' ') || first === 'pytest')) return true;
    if ((first.startsWith('./') || first.startsWith('scripts/') || first.startsWith('tools/')) && span.includes(' ')) return true;
  }
  return false;
}

function walkFiles(dir, out = []) {
  if (!fs.existsSync(dir)) return out;
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (
      entry.name === 'node_modules' ||
      entry.name === '.git' ||
      entry.name === '.claude' ||
      entry.name === '.worktrees' ||
      entry.name === '__pycache__' ||
      entry.name === '.pytest_cache' ||
      entry.name === '.venv' ||
      entry.name === 'venv'
    ) {
      continue;
    }
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) walkFiles(full, out);
    else out.push(full);
  }
  return out;
}

export function parseTaskCards(root) {
  const tasksDir = path.join(root, 'docs', 'tasks');
  const cards = new Map();
  if (!fs.existsSync(tasksDir)) return cards;
  for (const file of walkFiles(tasksDir).filter((f) => f.endsWith('.md'))) {
    const rel = path.relative(root, file).replace(/\\/g, '/');
    const content = fs.readFileSync(file, 'utf8').replace(/\r\n/g, '\n');
    const sections = content.split(/(?=^##\s+TC-[A-Z0-9-]+:)/m);
    for (const sec of sections) {
      const m = sec.match(/^##\s+(TC-[A-Z0-9-]+):\s*(.+)$/m);
      if (!m) continue;
      const id = m[1];
      const title = m[2].trim();
      const statusMatch = sec.match(/\*\*Status:\*\*\s*([a-z-]+)/i);
      const priorityMatch = sec.match(/\*\*Priority:\*\*\s*(P[0-3])/i);
      const status = statusMatch ? statusMatch[1].toLowerCase() : null;
      const priority = priorityMatch ? priorityMatch[1].toUpperCase() : null;

      const allowlist = [];
      const allowMatch = sec.match(/\*\*Governance Files Allowlist:\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
      if (allowMatch) {
        for (const line of allowMatch[1].split('\n')) {
          const item = line.match(/^\s*-\s*`([^`]+)`/);
          if (item) allowlist.push(item[1].trim());
        }
      }

      const filesSection = sec.match(/\*\*Files to create\/modify:\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
      const declaredFiles = [];
      if (filesSection) {
        for (const line of filesSection[1].split('\n')) {
          const item = line.match(/^\s*-\s*`?([^\s`([]+)`?/);
          if (item) declaredFiles.push(item[1].trim());
        }
      }

      const acSection = sec.match(/\*\*Acceptance Criteria:\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
      const acLines = acSection
        ? acSection[1]
            .split('\n')
            .map((l) => l.trim())
            .filter((l) => /^\d+\.\s+/.test(l))
        : [];

      cards.set(id, { id, title, status, priority, allowlist, declaredFiles, acLines, file: rel, raw: sec });
    }
  }
  return cards;
}

function matchesPrefix(relPath, prefixes) {
  const norm = relPath.replace(/\\/g, '/');
  return prefixes.some((p) => (p.endsWith('/') ? norm.startsWith(p) : norm === p));
}

export function validateRepo(root, options = {}) {
  const cfg = loadGovernanceConfig(root);
  const errors = [];
  const warnings = [];
  const fail = (rule, msg) => errors.push({ rule, message: msg });

  // --- PILLAR 1: Document, Roadmap, Cross-Ref, Falsifier & Supply-Chain Integrity ---
  const archPath = path.join(root, 'ARCHITECTURE.md');
  const roadmapPath = path.join(root, 'ROADMAP.md');
  const todoPath = path.join(root, 'docs', 'TODO-MASTER.md');
  const tasksDir = path.join(root, 'docs', 'tasks');

  const requireTodoMaster = cfg.require_todo_master !== false;
  const requiredDocs = [
    ['ARCHITECTURE.md', archPath],
    ['ROADMAP.md', roadmapPath],
    ['docs/tasks/', tasksDir],
  ];
  if (requireTodoMaster) requiredDocs.push(['docs/TODO-MASTER.md', todoPath]);
  for (const [label, p] of requiredDocs) {
    if (!fs.existsSync(p)) fail('DOC-01', `Missing required governance artifact: ${label}`);
  }
  if (errors.length > 0) return { passed: false, errors, warnings };

  // ARCH-01: Current-state path existence inside ## Project Structure
  const archText = fs.readFileSync(archPath, 'utf8').replace(/\r\n/g, '\n');
  const structMatch = archText.match(/##\s+Project Structure([\s\S]*?)(?=\n##\s+|$)/i);
  if (!structMatch) {
    fail('ARCH-01', 'ARCHITECTURE.md missing `## Project Structure` section');
  } else {
    for (const m of structMatch[1].matchAll(/^\s*-\s*`([^`]+)`/gm)) {
      const candidate = m[1].trim();
      if (candidate.includes('*') || candidate.startsWith('http')) continue;
      if (!fs.existsSync(path.join(root, candidate))) {
        fail('ARCH-01', `ARCHITECTURE.md Project Structure references non-existent path: ${candidate}`);
      }
    }
  }

  // ROAD-01..05: Phase statuses, subjective term ban, complete evidence, runnable verification
  const roadText = fs.readFileSync(roadmapPath, 'utf8').replace(/\r\n/g, '\n');
  const phaseBlocks = roadText.split(/(?=^###?\s+Phase\s+\d+)/m).filter((b) => /^###?\s+Phase\s+\d+/m.test(b));
  if (phaseBlocks.length === 0) fail('ROAD-01', 'ROADMAP.md defines zero `## Phase N` blocks');
  for (const block of phaseBlocks) {
    const header = block.split('\n')[0].trim();
    const st = block.match(/\*\*Status:\*\*\s*([a-z-]+)/i);
    if (!st || !VALID_STATUSES.has(st[1].toLowerCase())) {
      fail('ROAD-04', `${header}: missing or invalid **Status:** (${st ? st[1] : 'missing'})`);
    } else if (st[1].toLowerCase() === 'complete') {
      const ev = block.match(/\*\*Evidence:\*\*\s*(.+)/i);
      if (!ev || !/(PR\s*#\d+|#[1-9]\d*|[0-9a-f]{7,40})/i.test(ev[1])) {
        fail('ROAD-05', `${header}: complete phase must cite PR #N or commit SHA in **Evidence:**`);
      }
    }
    const ver = block.match(/\*\*Verification:\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n##|$)/i);
    const verLines = ver ? ver[1].split('\n').map((l) => l.trim()).filter((l) => /^(\d+\.|-)\s+/.test(l)) : [];
    if (verLines.length === 0) {
      fail('ROAD-03', `${header}: missing numbered/bulleted **Verification:** steps`);
    } else {
      for (const vl of verLines) {
        if (!/\(\s*manual\s*:\s*true\s*\)/i.test(vl) && !isRunnableCommandSpan(vl)) {
          fail('ROAD-03-RUN', `${header}: verification step is neither runnable backticked command nor (manual: true): "${vl}"`);
        }
      }
    }
    for (const term of cfg.banned_subjective_terms || []) {
      if (block.toLowerCase().includes(term.toLowerCase())) {
        fail('ROAD-02', `${header}: contains banned subjective weasel term "${term}"`);
      }
    }
  }

  // Task Cards & optional TODO-MASTER parity (TC-01..08, XDOC-01..02)
  // Note: setting `"require_todo_master": false` in GOVERNANCE.json enables pure single-source
  // task-card frontmatter mode, eliminating Bucket 1A's 57 TODO-MASTER / flip-sweep failure modes!
  const cards = parseTaskCards(root);
  const hasTodoMaster = requireTodoMaster && fs.existsSync(todoPath);
  const todoItems = new Map();
  if (hasTodoMaster) {
    const todoText = fs.readFileSync(todoPath, 'utf8').replace(/\r\n/g, '\n');
    for (const line of todoText.split('\n')) {
      const m = line.match(/^\s*-\s*\[([ xX])\]\s*\*\*\[(TC-[A-Z0-9-]+)\]\*\*/);
      if (m) {
        todoItems.set(m[2], { checked: m[1].toLowerCase() === 'x', line });
      }
    }

    for (const [id, item] of todoItems) {
      const card = cards.get(id);
      if (!card) {
        fail('XDOC-01', `TODO-MASTER references ${id} which has no ## ${id}: card in docs/tasks/`);
        continue;
      }
      const cardTerminal = card.status === 'complete' || card.status === 'superseded';
      if (item.checked && !cardTerminal) {
        fail('XDOC-02', `Ghost completion on ${id}: checked [x] in TODO-MASTER but card Status is "${card.status}"`);
      }
      if (!item.checked && cardTerminal) {
        fail('XDOC-02', `Unflipped TODO on ${id}: card Status is "${card.status}" but TODO-MASTER is [ ]`);
      }
    }
  }

  for (const [id, card] of cards) {
    if (hasTodoMaster && !todoItems.has(id)) {
      fail('XDOC-01', `Card ${id} in ${card.file} has no checklist row in docs/TODO-MASTER.md`);
    }
    if (!card.priority) fail('TC-01', `${id}: missing **Priority:** P0..P3`);
    if (!card.status || !VALID_STATUSES.has(card.status)) fail('TC-02', `${id}: missing/invalid **Status:**`);
    if (card.declaredFiles.length === 0) fail('TC-04', `${id}: missing **Files to create/modify:** entries`);
    if (card.acLines.length === 0) {
      fail('TC-05', `${id}: missing numbered **Acceptance Criteria:**`);
    } else {
      for (const ac of card.acLines) {
        if (!/\(\s*manual\s*:\s*true\s*\)/i.test(ac) && !isRunnableCommandSpan(ac)) {
          fail('TC-08', `${id}: AC is neither a runnable command nor (manual: true): "${ac}"`);
        }
        for (const term of cfg.banned_subjective_terms || []) {
          if (ac.toLowerCase().includes(term.toLowerCase())) {
            fail('TC-08', `${id}: AC contains subjective weasel term "${term}"`);
          }
        }
      }
    }
  }

  // ACT-PIN-01: 40-char commit SHA pinning on GitHub Actions `uses:`
  const wfDir = path.join(root, '.github', 'workflows');
  const actPinExempt = new Set((cfg.act_pin_exempt || []).map((p) => p.replace(/\\/g, '/')));
  for (const wf of walkFiles(wfDir).filter((f) => f.endsWith('.yml') || f.endsWith('.yaml'))) {
    const rel = path.relative(root, wf).replace(/\\/g, '/');
    if (actPinExempt.has(rel)) continue;
    const lines = fs.readFileSync(wf, 'utf8').replace(/\r\n/g, '\n').split('\n');
    lines.forEach((line, idx) => {
      const m = line.match(/^\s*-?\s*uses:\s*([^\s#]+)/);
      if (!m) return;
      const target = m[1].trim().replace(/^['"]|['"]$/g, '');
      if (target.startsWith('./')) return; // local composite action
      if (!/@[0-9a-f]{40}$/.test(target)) {
        fail('ACT-PIN-01', `${rel}:${idx + 1} unpinned GitHub Action "${target}" (must pin to 40-hex commit SHA)`);
      }
    });
  }

  // SEC-REDACT-01: Secret & hardcoded user home path check across docs and evidence
  const scanDirs = [path.join(root, 'docs'), path.join(root, 'evidence'), archPath, roadmapPath];
  const redactExempt = new Set((cfg.sec_redact_exempt || []).map((p) => p.replace(/\\/g, '/')));
  const secretRegex = /(sk-ant-[a-zA-Z0-9_-]{12,}|AIzaSy[a-zA-Z0-9_-]{20,}|ghp_[a-zA-Z0-9]{20,})/;
  const homePathRegex = /([A-Za-z]:\\Users\\[A-Za-z0-9_.-]+|\/Users\/[A-Za-z0-9_.-]+)\b/;
  for (const item of scanDirs) {
    const files = fs.existsSync(item) && fs.statSync(item).isDirectory() ? walkFiles(item) : fs.existsSync(item) ? [item] : [];
    for (const f of files) {
      const rel = path.relative(root, f).replace(/\\/g, '/');
      if (redactExempt.has(rel)) continue;
      const txt = fs.readFileSync(f, 'utf8');
      if (secretRegex.test(txt)) fail('SEC-REDACT-01', `${rel}: contains secret-shaped credential token`);
      if (homePathRegex.test(txt)) fail('SEC-REDACT-01', `${rel}: contains unredacted host user path`);
    }
  }

  // --- PILLAR 3: Coverage Mapping (`COV-01`) & Non-Vacuous Test Floor (`COV-02`) ---
  const cov = cfg.coverage || { prod_roots: ['src'], test_roots: ['tests'], exempt: [], min_test_count: 1 };
  const testFiles = [];
  for (const tr of cov.test_roots || ['tests']) {
    walkFiles(path.join(root, tr), testFiles);
  }
  const testBasenames = new Set(testFiles.map((f) => path.basename(f)));
  for (const pr of cov.prod_roots || ['src']) {
    for (const pf of walkFiles(path.join(root, pr))) {
      const rel = path.relative(root, pf).replace(/\\/g, '/');
      if ((cov.exempt || []).includes(rel)) continue;
      const ext = path.extname(pf);
      const stem = path.basename(pf, ext);
      const hasMatch =
        testBasenames.has(`${stem}.test${ext}`) ||
        testBasenames.has(`${stem}.test.mjs`) ||
        testBasenames.has(`${stem}.test.js`) ||
        testBasenames.has(`test_${stem}.py`);
      if (!hasMatch) {
        fail('COV-01', `Production module ${rel} has no matching test file (${stem}.test${ext})`);
      }
    }
  }

  let discoveredTests = 0;
  for (const tf of testFiles) {
    const txt = fs.readFileSync(tf, 'utf8');
    const matches = txt.match(/\b(test|it)\s*\(|^\s*def\s+test_/gm);
    discoveredTests += matches ? matches.length : 0;
  }
  if (discoveredTests < (cov.min_test_count ?? 1)) {
    fail('COV-02', `Discovered ${discoveredTests} test(s), below non-vacuous floor min_test_count=${cov.min_test_count}`);
  }

  // --- PILLAR 2: Adversarial Two-Mode Governance Firewall (`GOV-FIREWALL-01..04`) ---
  let changedFiles = options.changedFiles ?? null;
  let diffTextByFile = options.diffTextByFile ?? {};
  let baseHasGovernance = options.baseHasGovernance ?? true;
  if (!changedFiles && options.diffBase) {
    try {
      execFileSync('git', ['-C', root, 'cat-file', '-e', `${options.diffBase}:GOVERNANCE.json`], { stdio: 'ignore' });
      baseHasGovernance = true;
    } catch {
      baseHasGovernance = false;
    }
    const out = execFileSync('git', ['-C', root, 'diff', '--name-only', `${options.diffBase}...HEAD`], {
      encoding: 'utf8',
    });
    changedFiles = out.split(/\r?\n/).map((s) => s.trim()).filter(Boolean);
    for (const cf of changedFiles) {
      if (cf.startsWith('docs/tasks/') || cf === 'ROADMAP.md') {
        diffTextByFile[cf] = execFileSync('git', ['-C', root, 'diff', `${options.diffBase}...HEAD`, '--', cf], {
          encoding: 'utf8',
        });
      }
    }
  }

  if (changedFiles !== null) {
    const mode = !baseHasGovernance && (!options.mode || options.mode === 'impl') ? 'bootstrap' : options.mode || 'impl';
    const tcIds = options.tcIds || [];
    const attested =
      options.attested !== undefined
        ? Boolean(options.attested)
        : process.env.LW_OPERATOR_ATTESTATION === 'human-approved';

    if (options.requireNonEmptyDiff && changedFiles.length === 0) {
      fail('GOV-FIREWALL-01', 'Empty 0-file PR/branch stub refused (changedFiles == 0)');
    }

    const touchedProtected = changedFiles.filter((f) => matchesPrefix(f, cfg.protected_paths || []));
    if (touchedProtected.length > 0) {
      if (mode !== 'bootstrap' && (mode !== 'governance' || !attested)) {
        fail(
          'GOV-FIREWALL-02',
          `Protected governance file(s) modified without --mode governance + human attestation: ${touchedProtected.join(', ')}`
        );
      } else {
        // Active-only TC card allowlist check (excludes complete/superseded zombie cards — FIND/PR #1320 guard)
        const activeAllowlist = new Set();
        for (const id of tcIds) {
          const card = cards.get(id);
          if (!card) continue;
          if (TERMINAL_STATUSES.has(card.status || '')) {
            fail('GOV-FIREWALL-03', `Task card ${id} has terminal Status "${card.status}" and cannot grant firewall allowlist permissions`);
            continue;
          }
          for (const p of card.allowlist) activeAllowlist.add(p);
        }
        const unallowlisted = touchedProtected.filter((f) => !matchesPrefix(f, [...activeAllowlist]));
        if (unallowlisted.length > 0) {
          fail(
            'GOV-FIREWALL-03',
            `Protected file(s) not declared in an active TC card **Governance Files Allowlist:** ${unallowlisted.join(', ')}`
          );
        }
      }
    }

    if (mode === 'impl') {
      // Implementation PRs cannot mutate existing Acceptance Criteria or ROADMAP Verification steps (FIND-241 self-grading guard)
      for (const cf of changedFiles) {
        if (cf === 'ROADMAP.md') {
          fail('GOV-FIREWALL-04', 'Implementation PR (--mode impl) cannot modify ROADMAP.md (open a --mode spec PR first)');
        }
        if (cf.startsWith('docs/tasks/') && diffTextByFile[cf]) {
          const removedLines = diffTextByFile[cf]
            .split(/\r?\n/)
            .filter((l) => l.startsWith('-') && !l.startsWith('---'));
          const mutatedAc = removedLines.filter((l) => /^-\s*\d+\.\s+/.test(l));
          if (mutatedAc.length > 0) {
            fail(
              'GOV-FIREWALL-04',
              `Implementation PR (--mode impl) mutated/deleted existing Acceptance Criteria in ${cf} (self-grading forbidden)`
            );
          }
        }
      }
    } else if (mode === 'spec') {
      const touchedProd = changedFiles.filter((f) =>
        (cfg.coverage?.prod_roots || ['src']).some((r) => matchesPrefix(f, [`${r.replace(/\/$/, '')}/`]))
      );
      if (touchedProd.length > 0) {
        fail('GOV-FIREWALL-04', `Spec PR (--mode spec) cannot modify production code in the same PR: ${touchedProd.join(', ')}`);
      }
    }
  }

  return { passed: errors.length === 0, errors, warnings, stats: { cards: cards.size, discoveredTests } };
}

function main() {
  const argv = process.argv.slice(2);
  let root = process.cwd();
  let diffBase = null;
  let mode = 'impl';
  let requireNonEmptyDiff = false;
  const tcIds = [];
  let jsonOut = false;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') root = path.resolve(argv[++i]);
    else if (a === '--diff-base') diffBase = argv[++i];
    else if (a === '--mode') mode = argv[++i];
    else if (a === '--require-non-empty-diff') requireNonEmptyDiff = true;
    else if (a === '--tc') tcIds.push(...argv[++i].split(',').map((s) => s.trim()).filter(Boolean));
    else if (a === '--json') jsonOut = true;
  }

  const res = validateRepo(root, { diffBase, mode, requireNonEmptyDiff, tcIds });
  if (jsonOut) {
    process.stdout.write(JSON.stringify(res, null, 2) + '\n');
  } else if (res.passed) {
    process.stdout.write(
      `[PASS] Governed Lightweight check passed (${res.stats.cards} card(s), ${res.stats.discoveredTests} test(s) verified).\n`
    );
  } else {
    process.stderr.write(`[FAIL] Governed Lightweight check failed with ${res.errors.length} error(s):\n`);
    for (const e of res.errors) {
      process.stderr.write(`  - [${e.rule}] ${e.message}\n`);
    }
  }
  process.exit(res.passed ? 0 : 1);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
