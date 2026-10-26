#!/usr/bin/env node
/**
 * Governed Lightweight Validator (`check-governed.mjs`)
 *
 * Zero-dependency Node.js governance & substance gate (<100ms runtime) enforcing:
 *   - Pillar 1: Spec, Cross-Doc, Runnable Falsifier, Manual-Gate (`MANUAL-GATE-01`),
 *               SHA-Pinning (`ACT-PIN-01`) & Secret/PII Integrity (`SEC-REDACT-01`)
 *   - Pillar 2: Two-Mode Boundary Governance Firewall (`GOV-FIREWALL-01..04`) +
 *               Deterministic PR Substance & Anti-Gaming Verifier (`SUBSTANCE-01..05`,
 *               porting Command Center `TC-CC1271` / `FIND-472` + `RC-1B` / `RC-2D` / `RC-3A`)
 *   - Pillar 3: Production-to-test coverage (`COV-01` basename + target-import verification)
 *               & non-vacuous test floor (`COV-02`)
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

// Assembled via concatenation so this source never carries contiguous placeholder literals.
const TOK_POOL_SIMULATED = 'Pool' + 'Simulated';
const TOK_POOL_SIMULATED_UPPER = 'POOL_' + 'SIMULATED';
const TOK_SOLANA_POOL_SIMULATED = 'solana:raydium:' + TOK_POOL_SIMULATED;
const SELF_CHECK_DUMP_MAX_ADDED_LINES = 2000;

const JS_HARNESS_OR_STDLIB = new Set([
  'vitest', 'jest', '@jest/globals', 'mocha', 'chai', 'assert',
  'node:assert', 'node:assert/strict', 'node:test',
  'fs', 'node:fs', 'fs/promises', 'node:fs/promises',
  'path', 'node:path', 'os', 'node:os', 'url', 'node:url',
  'crypto', 'node:crypto', 'util', 'node:util',
  'child_process', 'node:child_process', 'stream', 'node:stream',
]);

const PY_STDLIB_OR_HARNESS = new Set([
  'pytest', 'unittest', 'hypothesis', '__future__', 'typing', 'typing_extensions',
  'os', 'sys', 're', 'json', 'math', 'time', 'datetime', 'pathlib', 'collections',
  'itertools', 'functools', 'dataclasses', 'enum', 'abc', 'io', 'copy', 'shutil',
  'tempfile', 'subprocess', 'hashlib', 'random', 'statistics', ' decimal', 'fractions',
  'ast', 'inspect', 'types', 'warnings', 'contextlib', 'logging', 'argparse', 'csv',
]);

export function loadGovernanceConfig(root) {
  const cfgPath = path.join(root, 'GOVERNANCE.json');
  if (!fs.existsSync(cfgPath)) {
    return {
      schema_version: 1,
      repo_prefix: 'TC',
      protected_paths: ['GOVERNANCE.json', 'scripts/check-governed.mjs', 'scripts/run-criteria.mjs', '.github/workflows/'],
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
    if ((first.startsWith('./') || first.startsWith('scripts/') || first.startsWith('tools/')) && span.includes(' ')) {
      return true;
    }
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

export function parseOpenOperatorGates(root) {
  const openGates = new Set();
  const candidates = [
    path.join(root, 'docs', 'ACTIONS-DECISIONS.md'),
    path.join(root, 'ACTIONS-DECISIONS.md'),
  ];
  for (const p of candidates) {
    if (!fs.existsSync(p)) continue;
    const lines = fs.readFileSync(p, 'utf8').replace(/\r\n/g, '\n').split('\n');
    for (const line of lines) {
      const gateMatches = [...line.matchAll(/\b(GA-\d+|GD-\d+|[A-Z]{2,8}-(?:ACT|DEC)-\d+)\b/g)].map((m) => m[1]);
      if (gateMatches.length === 0) continue;
      // Unchecked checklist item `- [ ] **GA-1**` or markdown table row with open/pending/awaiting/blocked status
      const isUncheckedBox = /^\s*-\s*\[\s\]/.test(line);
      const isTableRow = line.trim().startsWith('|');
      const isOpenTable =
        isTableRow &&
        /\|\s*(?:`|\*\*)?(?:open|pending|blocked|awaiting|action-required|todo|in-progress|active)(?:`|\*\*)?\s*\|/i.test(line) &&
        !/\|\s*(?:`|\*\*)?(?:closed|resolved|done|complete|completed|superseded)(?:`|\*\*)?\s*\|/i.test(line);
      if (isUncheckedBox || isOpenTable) {
        for (const g of gateMatches) openGates.add(g);
      }
    }
  }
  // Also support HTD-style dedicated open-gate ledgers (`docs/operator/OPERATOR-ACTIONS.md` & `OPERATOR-DECISIONS.md`)
  for (const opFile of [
    path.join(root, 'docs', 'operator', 'OPERATOR-ACTIONS.md'),
    path.join(root, 'docs', 'operator', 'OPERATOR-DECISIONS.md'),
  ]) {
    if (!fs.existsSync(opFile)) continue;
    const lines = fs.readFileSync(opFile, 'utf8').replace(/\r\n/g, '\n').split('\n');
    for (const line of lines) {
      const hm = line.match(/^#{2,3}\s+(GA-\d+|GD-\d+)\b/);
      if (hm) openGates.add(hm[1]);
    }
  }
  return openGates;
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

      const manualAttestMatch = sec.match(/\*\*Manual Attestation:\*\*\s*(.+)/i);
      const manualAttestation = manualAttestMatch ? manualAttestMatch[1].trim() : null;

      const allowlist = [];
      const allowMatch = sec.match(/\*\*Governance Files Allowlist:\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
      if (allowMatch) {
        for (const line of allowMatch[1].split('\n')) {
          const item = line.match(/^\s*-\s*`([^`]+)`/);
          if (item) allowlist.push(item[1].trim());
        }
      }

      const filesSection = sec.match(/\*\*Files to (?:create\/modify|create|modify):\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
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

      const referencedGates = [
        ...new Set([...sec.matchAll(/\b(GA-\d+|GD-\d+|[A-Z]{2,8}-(?:ACT|DEC)-\d+)\b/g)].map((gm) => gm[1])),
      ];

      cards.set(id, {
        id,
        title,
        status,
        priority,
        manualAttestation,
        referencedGates,
        allowlist,
        declaredFiles,
        acLines,
        file: rel,
        raw: sec,
      });
    }
  }
  return cards;
}

function matchesPrefix(relPath, prefixes) {
  const norm = relPath.replace(/\\/g, '/').replace(/^\.\//, '');
  return prefixes.some((rawP) => {
    const p = rawP.replace(/\\/g, '/').replace(/^\.\//, '');
    return p.endsWith('/') ? norm.startsWith(p) : norm === p;
  });
}

function isTestPath(normPath) {
  const lower = normPath.toLowerCase();
  const base = path.posix.basename(lower);
  if (base.startsWith('test_') && base.endsWith('.py')) return true;
  if (base.endsWith('_test.py')) return true;
  if (base.includes('.test.') || base.includes('.spec.')) return true;
  if (
    /\/(?:fakes|fixtures|helpers|__fixtures__|__mocks__)\//.test(`/${lower}`) ||
    base === 'conftest.py' ||
    base === 'fixtures.mjs' ||
    base === 'serve.mjs'
  ) {
    return false;
  }
  return lower.startsWith('tests/') || lower.includes('/tests/') || lower.includes('/__tests__/');
}

function checkJsTautologicalTest(normPath, sourceText) {
  if (!sourceText.trim()) {
    return `newly added JS/TS test file ${normPath} is empty`;
  }
  const importRe = /(?:^\s*import\s+(?:[\s\S]+?\s+from\s+)?['"]([^'"]+)['"]|require\(\s*['"]([^'"]+)['"]\s*\))/gm;
  const imports = [];
  for (const m of sourceText.matchAll(importRe)) {
    const spec = (m[1] || m[2] || '').trim();
    if (spec) imports.push(spec);
  }
  const hasTargetImport = imports.some((imp) => !JS_HARNESS_OR_STDLIB.has(imp));
  const invokesProjectScript = /\b(?:execFileSync|spawnSync|execSync)\s*\([\s\S]{0,160}?(?:scripts\/|tools\/|src\/)/m.test(
    sourceText
  );
  if (hasTargetImport || invokesProjectScript) return null;

  const lines = sourceText.split(/\r?\n/);
  const assertLines = lines.map((l) => l.trim()).filter((l) => /\b(?:expect|assert)\s*(?:\.\s*\w+\s*)?\(/.test(l));
  if (assertLines.length === 0) {
    return `${normPath} imports zero project/target modules and contains zero assertions`;
  }
  const trivialLineRe =
    /^(?:expect\(\s*(?:true|false|null|undefined|\d+(?:\s*[+\-*/]\s*\d+)?|'[^']*'|"[^"]*")\s*\)\.(?:toBe|toEqual|toStrictEqual|toBeTruthy|toBeFalsy)\(\s*(?:true|false|null|undefined|\d+|'[^']*'|"[^"]*")?\s*\)|assert(?:\.ok|\.strictEqual|\.equal)?\(\s*(?:true|1\s*===?\s*1|'[^']*'|"[^"]*")(?:\s*,\s*(?:true|1|'[^']*'|"[^"]*"))?\s*\))\s*;?$/;
  if (assertLines.every((l) => trivialLineRe.test(l))) {
    return `${normPath} imports zero project/target modules and all ${assertLines.length} assertion(s) evaluate literals only`;
  }
  return `${normPath} imports zero project/target modules (must import or invoke real repository code under test)`;
}

function checkPythonTautologicalTest(normPath, sourceText) {
  if (!sourceText.trim()) {
    return `newly added Python test file ${normPath} is empty`;
  }
  const imports = [];
  for (const m of sourceText.matchAll(/^\s*(?:from\s+([.\w]+)\s+import|import\s+([\w.]+))/gm)) {
    const raw = (m[1] || m[2] || '').trim();
    if (!raw) continue;
    if (raw.startsWith('.')) {
      imports.push(raw);
    } else {
      imports.push(raw.split('.')[0]);
    }
  }
  const hasTargetImport = imports.some((imp) => imp.startsWith('.') || !PY_STDLIB_OR_HARNESS.has(imp));
  const invokesProjectScript = /\b(?:subprocess|Popen|run|check_output)[\s\S]{0,160}?(?:scripts\/|tools\/|src\/|\.py\b)/m.test(
    sourceText
  );
  if (hasTargetImport || invokesProjectScript) return null;
  return `${normPath} imports zero project/target modules (must import or invoke real repository code under test)`;
}

/**
 * Deterministic PR Diff Substance & Anti-Gaming Verifier (`Gap LW-1` / `TC-CC1271` / `FIND-472`)
 */
export function evaluatePrSubstance(
  fileDiffs,
  { declaredCardFiles = [], repoName = null, requireNonEmptyDiff = false, attested = false } = {}
) {
  const errors = [];
  const fail = (rule, msg) => errors.push({ rule, message: msg });

  if (requireNonEmptyDiff && fileDiffs.length === 0) {
    fail('SUBSTANCE-01', 'EMPTY-DIFF: PR contains 0 changed files (--allow-empty / empty stub diff)');
    return errors;
  }

  const expectedRepoLower = repoName ? repoName.trim().split('/').pop().toLowerCase() : null;
  const dualThresholdRe =
    /\b(effectiveRate|effective_rate|passRate|pass_rate)\s*<\s*(?:minPassRate|min_pass_rate|MIN_PASS_RATE)\s*(?:&&|\band\b)\s*\1\s*<\s*(?:0?\.\d+|0\b)/;
  const zeroMinPassRateRe =
    /^\s*(?:(?:export\s+)?(?:const|let|var)\s+)?(?:minPassRate|min_pass_rate|MIN_PASS_RATE)\s*(?:=|:)\s*0(?:\.0+)?\s*(?:[,;#]|$)/;
  const skipInflationRe =
    /\b(?:it|test|describe)\.skip\s*\(|\bxit\s*\(|\bxtest\s*\(|@pytest\.mark\.skip\b|@unittest\.skip\b/;
  const pid1000Re = /\bPID\s*:\s*1000\b/;
  const synthTimeRe = /(?:\bTime\s*:\s*00:00:00\b|\bExecutionTime\s*=\s*0\.25\s*s\b)/;
  const repoHeaderRe = /^\s*Repository:\s*([^\s#]+)/i;

  for (const fd of fileDiffs) {
    const normPath = (fd.path || '').replace(/\\/g, '/').replace(/^\.\//, '');
    if (!normPath) continue;
    const status = (fd.status || 'M').toUpperCase()[0];
    if (status === 'D') continue;

    const patch = fd.patch || '';
    const addedLines = patch
      .split(/\r?\n/)
      .filter((l) => l.startsWith('+') && !l.startsWith('+++'))
      .map((l) => l.slice(1));
    const lowerPath = normPath.toLowerCase();

    // SUBSTANCE-02: SCRATCH-POLLUTION (.agent-context/* or oversized/foreign self-check dumps)
    if (lowerPath.startsWith('.agent-context/') && !matchesPrefix(normPath, declaredCardFiles)) {
      fail(
        'SUBSTANCE-02',
        `SCRATCH-POLLUTION: committed transient ${normPath} not declared in TC card Files to create/modify`
      );
    }
    if (lowerPath.startsWith('.agent-output/') && lowerPath.endsWith('.txt') && lowerPath.includes('self-check')) {
      if (addedLines.length > SELF_CHECK_DUMP_MAX_ADDED_LINES) {
        fail(
          'SUBSTANCE-02',
          `SCRATCH-POLLUTION: ${normPath} has ${addedLines.length} added lines (exceeds ${SELF_CHECK_DUMP_MAX_ADDED_LINES}-line cap)`
        );
      }
      if (expectedRepoLower) {
        for (const ln of addedLines) {
          const rm = ln.match(repoHeaderRe);
          if (rm) {
            const observed = rm[1].trim().split('/').pop().toLowerCase();
            if (observed && observed !== expectedRepoLower) {
              fail(
                'SUBSTANCE-02',
                `SCRATCH-POLLUTION: ${normPath} declares foreign Repository: ${rm[1]} (expected ${expectedRepoLower})`
              );
              break;
            }
          }
        }
      }
    }

    const isTest = isTestPath(normPath);
    const isGovValidator =
      lowerPath.endsWith('check-governed.mjs') ||
      lowerPath.endsWith('governed-firewall.mjs') ||
      lowerPath.endsWith('spawn-guard.mjs') ||
      lowerPath === 'validator/substance_gate.py';
    const isGovProse = lowerPath.startsWith('docs/findings/') || lowerPath.startsWith('docs/tasks/');

    // SUBSTANCE-03: SYNTHETIC-FABRICATION
    if (!isTest && !isGovValidator && !isGovProse && addedLines.length > 0) {
      if (
        addedLines.some(
          (ln) =>
            ln.includes(TOK_SOLANA_POOL_SIMULATED) ||
            ln.includes(TOK_POOL_SIMULATED) ||
            ln.includes(TOK_POOL_SIMULATED_UPPER)
        )
      ) {
        fail('SUBSTANCE-03', `SYNTHETIC-FABRICATION: ${normPath} contains synthetic placeholder replay token`);
      }
      const inEvalOrReplay =
        /^(?:replay|evaluations|docs\/evaluations|evidence|docs\/evidence)\//.test(lowerPath) ||
        lowerPath.includes('/replay/') ||
        lowerPath.includes('/evaluations/') ||
        lowerPath.includes('/evidence/') ||
        path.posix.basename(lowerPath).startsWith('log.');
      if (inEvalOrReplay) {
        if (addedLines.some((ln) => pid1000Re.test(ln)) && addedLines.some((ln) => synthTimeRe.test(ln))) {
          fail(
            'SUBSTANCE-03',
            `SYNTHETIC-FABRICATION: ${normPath} contains synthetic solver log signature (PID: 1000 + zero/fixed ExecutionTime)`
          );
        }
      }
    }

    // SUBSTANCE-04: THRESHOLD-BYPASS & SKIP-INFLATION
    const isMarkdownOrDocs = lowerPath.endsWith('.md') || lowerPath.startsWith('docs/');
    if (!isTest && !isGovValidator && !isMarkdownOrDocs && addedLines.length > 0) {
      for (const ln of addedLines) {
        if (dualThresholdRe.test(ln)) {
          fail('SUBSTANCE-04', `THRESHOLD-BYPASS: ${normPath} weakens pass-rate gate via dual-threshold conjunction`);
          break;
        }
        if (zeroMinPassRateRe.test(ln)) {
          fail('SUBSTANCE-04', `THRESHOLD-BYPASS: ${normPath} zeroes minimum pass-rate threshold`);
          break;
        }
      }
    }
    if (isTest && !attested && addedLines.length > 0) {
      if (addedLines.some((ln) => skipInflationRe.test(ln))) {
        fail(
          'SUBSTANCE-04',
          `SKIP-INFLATION: ${normPath} introduces skipped test(s) without governance attestation`
        );
      }
    }

    // SUBSTANCE-05: TAUTOLOGICAL-TEST on newly added test files
    if (status === 'A' && isTest && addedLines.length > 0) {
      const addedSource = addedLines.join('\n');
      if (lowerPath.endsWith('.py')) {
        const msg = checkPythonTautologicalTest(normPath, addedSource);
        if (msg) fail('SUBSTANCE-05', `TAUTOLOGICAL-TEST: ${msg}`);
      } else if (/\.(?:mjs|cjs|js|jsx|ts|tsx)$/.test(lowerPath)) {
        const msg = checkJsTautologicalTest(normPath, addedSource);
        if (msg) fail('SUBSTANCE-05', `TAUTOLOGICAL-TEST: ${msg}`);
      }
    }
  }

  return errors;
}

export function validateRepo(root, options = {}) {
  const cfg = loadGovernanceConfig(root);
  const errors = [];
  const warnings = [];
  const fail = (rule, msg) => errors.push({ rule, message: msg });

  // --- PILLAR 1: Document, Roadmap, Cross-Ref, Falsifier, Manual-Gate & Supply-Chain Integrity ---
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

  // Standing workspace scratch-pollution check (`RC-3A`)
  const agentContextDir = path.join(root, '.agent-context');
  if (fs.existsSync(agentContextDir) && walkFiles(agentContextDir).length > 0) {
    fail('SUBSTANCE-02', 'SCRATCH-POLLUTION: .agent-context/ directory present in repository tree');
  }

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

  // Task Cards, Manual-Gate (`MANUAL-GATE-01`), & optional TODO-MASTER parity
  const cards = parseTaskCards(root);
  const openOperatorGates = parseOpenOperatorGates(root);
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
      const hasManualAc = card.acLines.some((ac) => /\(\s*manual\s*:\s*true\s*\)/i.test(ac));
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

      // RC-2B (`DELIV-01`) & RC-2D (`MANUAL-GATE-01`): Completed card deliverables must exist & manual/operator gates attested
      if (card.status === 'complete') {
        const legacyDelivExempt = new Set(cfg.legacy_deliv_exempt_cards || []);
        if (!legacyDelivExempt.has(id)) {
          for (const df of card.declaredFiles) {
            if (!df || df.includes('*') || df.includes('?') || df.includes('<') || df.startsWith('http')) continue;
            if (!fs.existsSync(path.join(root, df))) {
              fail('DELIV-01', `${id}: marked Status: complete but declared file/path does not exist on disk: ${df}`);
            }
          }
        }
        if (hasManualAc && !card.manualAttestation) {
          fail(
            'MANUAL-GATE-01',
            `${id}: marked Status: complete with (manual: true) criteria but missing **Manual Attestation:** record`
          );
        }
        const blockingGates = card.referencedGates.filter((g) => openOperatorGates.has(g));
        if (blockingGates.length > 0 && !card.manualAttestation) {
          fail(
            'MANUAL-GATE-01',
            `${id}: marked Status: complete while operator gate(s) remain open in operator ledgers: ${blockingGates.join(', ')}`
          );
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
    const files =
      fs.existsSync(item) && fs.statSync(item).isDirectory()
        ? walkFiles(item)
        : fs.existsSync(item)
          ? [item]
          : [];
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
  const allowImportCoverage = cov.allow_import_coverage === true;
  const combinedTestCorpus = allowImportCoverage
    ? testFiles.map((tf) => fs.readFileSync(tf, 'utf8')).join('\n')
    : '';
  const legacyDebtSet = new Set((cov.legacy_untested_debt || []).map((p) => p.replace(/\\/g, '/')));
  const exemptSet = new Set((cov.exempt || []).map((p) => p.replace(/\\/g, '/')));
  const CODE_EXTS = new Set(['.py', '.js', '.mjs', '.cjs', '.ts', '.tsx', '.jsx']);

  for (const pr of cov.prod_roots || ['src']) {
    for (const pf of walkFiles(path.join(root, pr))) {
      const rel = path.relative(root, pf).replace(/\\/g, '/');
      if (exemptSet.has(rel) || legacyDebtSet.has(rel)) continue;
      const ext = path.extname(pf);
      if (!CODE_EXTS.has(ext.toLowerCase())) continue;
      const stem = path.basename(pf, ext);
      if (isTestPath(rel)) continue;
      const hasDirectFile =
        testBasenames.has(`${stem}.test${ext}`) ||
        testBasenames.has(`${stem}.test.mjs`) ||
        testBasenames.has(`${stem}.test.js`) ||
        testBasenames.has(`test_${stem}.py`) ||
        testBasenames.has(`${stem}_test.py`);
      const escapedStem = stem.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      const hasImportOrExec =
        allowImportCoverage &&
        new RegExp(`(?:\\b${escapedStem}\\b|/${escapedStem}\\b)`).test(combinedTestCorpus);
      if (!hasDirectFile && !hasImportOrExec) {
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

  // WIRING-01 (`RC-3B` Runtime Entrypoint Reachability / Dead-Island Guard when `cfg.entrypoints` is configured)
  if (Array.isArray(cfg.entrypoints) && cfg.entrypoints.length > 0) {
    const unwiredDebt = new Set((cfg.legacy_unwired_debt || []).map((p) => p.replace(/\\/g, '/')));
    const reachable = new Set();
    const queue = [];
    const resolveCandidate = (baseDir, spec) => {
      const cleanSpec = spec.split('?')[0].split('#')[0];
      const rawTarget = path.resolve(baseDir, cleanSpec);
      const tryPaths = [
        rawTarget,
        `${rawTarget}.ts`,
        `${rawTarget}.tsx`,
        `${rawTarget}.js`,
        `${rawTarget}.mjs`,
        `${rawTarget}.py`,
        cleanSpec.endsWith('.js') ? `${rawTarget.slice(0, -3)}.ts` : null,
        path.join(rawTarget, 'index.ts'),
        path.join(rawTarget, 'index.js'),
        path.join(rawTarget, 'index.mjs'),
        path.join(rawTarget, '__init__.py'),
      ].filter(Boolean);
      for (const tp of tryPaths) {
        if (fs.existsSync(tp) && fs.statSync(tp).isFile()) return tp;
      }
      return null;
    };

    for (const ep of cfg.entrypoints) {
      const absEp = path.join(root, ep);
      if (!fs.existsSync(absEp)) {
        fail('WIRING-01', `Declared runtime entrypoint does not exist: ${ep}`);
        continue;
      }
      reachable.add(path.relative(root, absEp).replace(/\\/g, '/'));
      queue.push(absEp);
    }

    const edgeRe =
      /(?:import|export)\s+(?:[\s\S]*?\s+from\s+)?['"](\.[^'"]+)['"]|import\(\s*['"](\.[^'"]+)['"]\s*\)|require\(\s*['"](\.[^'"]+)['"]\s*\)|<script[^>]+src=['"]([^'"]+)['"]/g;
    while (queue.length > 0) {
      const cur = queue.pop();
      const txt = fs.readFileSync(cur, 'utf8');
      const curDir = path.dirname(cur);
      for (const m of txt.matchAll(edgeRe)) {
        const spec = (m[1] || m[2] || m[3] || m[4] || '').trim();
        if (!spec || spec.startsWith('http')) continue;
        const resolved = resolveCandidate(curDir, spec);
        if (!resolved) continue;
        const rel = path.relative(root, resolved).replace(/\\/g, '/');
        if (!reachable.has(rel)) {
          reachable.add(rel);
          queue.push(resolved);
        }
      }
    }

    for (const pr of cov.prod_roots || ['src']) {
      for (const pf of walkFiles(path.join(root, pr))) {
        const rel = path.relative(root, pf).replace(/\\/g, '/');
        const ext = path.extname(pf).toLowerCase();
        if (!CODE_EXTS.has(ext) || isTestPath(rel)) continue;
        if (exemptSet.has(rel) || unwiredDebt.has(rel)) continue;
        if (!reachable.has(rel)) {
          fail('WIRING-01', `Production module ${rel} is unreachable from declared runtime entrypoints (unwired dead island)`);
        }
      }
    }
  }

  // --- PILLAR 2: Two-Mode Boundary Governance Firewall (`GOV-FIREWALL-01..04`) & Substance Gate (`SUBSTANCE-01..05`) ---
  let changedFiles = options.changedFiles ?? null;
  let diffTextByFile = options.diffTextByFile ?? {};
  let fileDiffs = options.fileDiffs ?? null;
  let baseHasGovernance = options.baseHasGovernance ?? true;

  if (!changedFiles && options.diffBase) {
    try {
      execFileSync('git', ['-C', root, 'cat-file', '-e', `${options.diffBase}:GOVERNANCE.json`], { stdio: 'ignore' });
      baseHasGovernance = true;
    } catch {
      baseHasGovernance = false;
    }
    const nameStatusOut = execFileSync(
      'git',
      ['-C', root, 'diff', '--name-status', `${options.diffBase}...HEAD`],
      { encoding: 'utf8' }
    );
    changedFiles = [];
    fileDiffs = [];
    for (const rawLine of nameStatusOut.split(/\r?\n/).map((s) => s.trim()).filter(Boolean)) {
      const parts = rawLine.split(/\t+/);
      const status = parts[0] || 'M';
      const filePath = parts[parts.length - 1];
      if (!filePath) continue;
      changedFiles.push(filePath);
      const patch =
        status.startsWith('D')
          ? ''
          : execFileSync('git', ['-C', root, 'diff', `${options.diffBase}...HEAD`, '--', filePath], {
              encoding: 'utf8',
            });
      if (filePath.startsWith('docs/tasks/') || filePath === 'ROADMAP.md' || filePath === 'docs/TODO-MASTER.md') {
        diffTextByFile[filePath] = patch;
      }
      fileDiffs.push({ path: filePath, status: status[0], patch });
    }
  } else if (changedFiles !== null && !fileDiffs) {
    fileDiffs = changedFiles.map((cf) => ({
      path: cf,
      status: 'M',
      patch: diffTextByFile[cf] || '',
    }));
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

    // Collect declared card files across active referenced TCs for substance scratch check
    const declaredCardFiles = [];
    for (const id of tcIds) {
      const card = cards.get(id);
      if (card) declaredCardFiles.push(...card.declaredFiles);
    }

    // Run deterministic PR diff substance & anti-gaming checks (`SUBSTANCE-01..05`)
    const substanceErrors = evaluatePrSubstance(fileDiffs || [], {
      declaredCardFiles,
      repoName: options.repoName || path.basename(root),
      requireNonEmptyDiff: false, // handled above as GOV-FIREWALL-01 to preserve rule code backwards-compat
      attested,
    });
    for (const se of substanceErrors) errors.push(se);

    // COV-03: Newly added (`status === 'A'`) production code files cannot be exempted via exempt/legacy_untested_debt
    for (const fd of fileDiffs || []) {
      const norm = (fd.path || '').replace(/\\/g, '/').replace(/^\.\//, '');
      const status = (fd.status || 'M').toUpperCase()[0];
      const ext = path.extname(norm).toLowerCase();
      const inProdRoot = (cov.prod_roots || ['src']).some((r) => matchesPrefix(norm, [`${r.replace(/\/$/, '')}/`]));
      if (
        status === 'A' &&
        inProdRoot &&
        CODE_EXTS.has(ext) &&
        !isTestPath(norm) &&
        path.posix.basename(norm) !== '__init__.py' &&
        (exemptSet.has(norm) || legacyDebtSet.has(norm))
      ) {
        fail('COV-03', `Newly added production module ${norm} cannot bypass COV-01 via coverage.exempt / legacy_untested_debt`);
      }
    }

    const touchedProtected = changedFiles.filter((f) => matchesPrefix(f, cfg.protected_paths || []));
    if (touchedProtected.length > 0) {
      if (mode !== 'bootstrap' && (mode !== 'governance' || !attested)) {
        fail(
          'GOV-FIREWALL-02',
          `Protected governance file(s) modified without --mode governance + human attestation: ${touchedProtected.join(', ')}`
        );
      } else {
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

          // RC-2D / Gap LW-3: Block unattested `--mode impl` completion flip on cards with `(manual: true)` or open operator gates
          if (!attested) {
            for (const id of tcIds) {
              const card = cards.get(id);
              if (!card || card.status !== 'complete') continue;
              const hasManualAc = card.acLines.some((ac) => /\(\s*manual\s*:\s*true\s*\)/i.test(ac));
              const hasOpenGate = card.referencedGates.some((g) => openOperatorGates.has(g));
              if (hasManualAc || hasOpenGate) {
                fail(
                  'MANUAL-GATE-01',
                  `Implementation PR (--mode impl) cannot flip ${id} to Status: complete while (manual: true) criteria or open operator gates exist without human attestation`
                );
              }
            }
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
  let repoName = null;
  const tcIds = [];
  let jsonOut = false;

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') root = path.resolve(argv[++i]);
    else if (a === '--diff-base') diffBase = argv[++i];
    else if (a === '--mode') mode = argv[++i];
    else if (a === '--repo-name') repoName = argv[++i];
    else if (a === '--require-non-empty-diff') requireNonEmptyDiff = true;
    else if (a === '--tc') tcIds.push(...argv[++i].split(',').map((s) => s.trim()).filter(Boolean));
    else if (a === '--json') jsonOut = true;
  }

  const res = validateRepo(root, { diffBase, mode, requireNonEmptyDiff, repoName, tcIds });
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
