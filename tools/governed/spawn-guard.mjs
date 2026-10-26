#!/usr/bin/env node
/**
 * Pre-Launch Collision, Billing Firewall, Risk Scorer, ROI Gate, Clean-Abort Contract & Worktree Hygiene (`spawn-guard.mjs`)
 *
 * Distills high-leverage primitives from `BO` + `CC` + `market-lab`:
 *   1. `scrubMeteredEnvironment`: `$0.00` metered API firewall (`TC-BO81` / `TC-BO85`)
 *   2. `detectWaveFileCollisions`: static file-fan-in lock (`FIND-053`, `FIND-334`)
 *   3. `scoreDiffRisk`: 3-axis blast-radius scorer (`risk_tier.py`) — classifies `{low, medium, high}`, never grants permission
 *   4. `evaluateRoiGate`: `market-lab` reservation-wage (`r* = $125/hr`) + `GovernanceTax` gate
 *   5. `ensureWorktreeScratchExcludes`: writes `.git/info/exclude` for `.agent-context/` & `.agent-output/` (`FIND-315`, `FIND-399`, `FIND-469`)
 *   6. `scanTranscriptForFallbackTrap`: aborts on silent `model_refusal_fallback` (`FIND-393`)
 *   7. `renderAgentBriefContract` & `classifySessionOutcome`: `TC-BO86` / `RC-1A` anti-gaming substance framing + `AGENT_ABORT:` / `.agent-stop` clean-abort handoff
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const TOK_POOL_SIMULATED = 'POOL_' + 'SIMULATED';

function loadGovernanceConfig(root) {
  const cfgPath = path.join(root, 'GOVERNANCE.json');
  return fs.existsSync(cfgPath) ? JSON.parse(fs.readFileSync(cfgPath, 'utf8')) : {};
}

function parseTaskCards(root) {
  const tasksDir = path.join(root, 'docs', 'tasks');
  const cards = new Map();
  if (!fs.existsSync(tasksDir)) return cards;
  for (const entry of fs.readdirSync(tasksDir).filter((f) => f.endsWith('.md')).sort()) {
    const content = fs.readFileSync(path.join(tasksDir, entry), 'utf8').replace(/\r\n/g, '\n');
    for (const sec of content.split(/(?=^##\s+TC-[A-Z0-9-]+:)/m)) {
      const m = sec.match(/^##\s+(TC-[A-Z0-9-]+):\s*(.+)$/m);
      if (!m) continue;
      const filesSection = sec.match(/\*\*Files to (?:create\/modify|create|modify):\*\*\s*\n([\s\S]*?)(?=\n\*\*[A-Z]|\n---|\n## |$)/);
      const declaredFiles = [];
      if (filesSection) {
        for (const line of filesSection[1].split('\n')) {
          const item = line.match(/^\s*-\s*`?([^\s`([]+)`?/);
          if (item) declaredFiles.push(item[1].trim());
        }
      }
      cards.set(m[1], { id: m[1], title: m[2].trim(), declaredFiles });
    }
  }
  return cards;
}

export function scrubMeteredEnvironment(env, cfg = {}, { allowMetered = false } = {}) {
  const copy = { ...env };
  const stripped = [];
  const guard = cfg.cost_guardrails || {};
  const vars = guard.metered_env_vars || [
    'ANTHROPIC_API_KEY',
    'GEMINI_API_KEY',
    'GOOGLE_API_KEY',
    'GOOGLE_GENAI_API_KEY',
    'OPENAI_API_KEY',
    'VERTEX_API_KEY',
  ];

  const humanOverride = allowMetered || copy.LW_ALLOW_METERED_API === '1';
  if (guard.subscription_only_default !== false && !humanOverride) {
    const upperTarget = new Set(vars.map((v) => v.toUpperCase()));
    for (const key of Object.keys(copy)) {
      if (upperTarget.has(key.toUpperCase())) {
        delete copy[key];
        stripped.push(key);
      }
    }
  }
  return { env: copy, stripped, meteredAllowed: humanOverride };
}

export function detectWaveFileCollisions(root, candidateCardIds) {
  const cards = parseTaskCards(root);
  const fileOwners = new Map();
  const collisions = [];

  for (const id of candidateCardIds) {
    const card = cards.get(id);
    if (!card) throw new Error(`Unknown task card in wave: ${id}`);
    for (const rawFile of card.declaredFiles) {
      const f = rawFile.replace(/\\/g, '/');
      if (!fileOwners.has(f)) fileOwners.set(f, []);
      fileOwners.get(f).push(id);
    }
  }

  for (const [file, owners] of fileOwners.entries()) {
    if (owners.length > 1) {
      collisions.push({ file, cards: owners });
    }
  }

  return {
    safeToParallelize: collisions.length === 0,
    collisions,
  };
}

export function scoreDiffRisk(changedFiles, protectedPaths = []) {
  const normProtected = protectedPaths.map((p) => p.replace(/\\/g, '/'));
  const touchesProtected = changedFiles.some((raw) => {
    const f = raw.replace(/\\/g, '/');
    return normProtected.some((p) => (p.endsWith('/') ? f.startsWith(p) : f === p));
  });
  if (touchesProtected) {
    return { tier: 'high', autoMergeEligible: false, reason: 'touches_protected_governance_surface' };
  }
  if (changedFiles.length > 8) {
    return { tier: 'high', autoMergeEligible: false, reason: 'blast_radius_gt_8_files' };
  }
  if (changedFiles.length > 3) {
    return { tier: 'medium', autoMergeEligible: true, reason: 'bounded_4_to_8_files' };
  }
  return { tier: 'low', autoMergeEligible: changedFiles.length > 0, reason: 'bounded_le_3_files' };
}

export function evaluateRoiGate({
  deltaEvUsd = 0,
  pSuccess = 1.0,
  pConversion = 1.0,
  computeUsd = 0,
  humanHours = 0.25,
  unmonetizedGovHours = 0,
  reservationWageUsdPerHr = 125.0,
} = {}) {
  const governanceTaxUsd = unmonetizedGovHours * reservationWageUsdPerHr;
  const netValueUsd = deltaEvUsd * pSuccess * pConversion - computeUsd - governanceTaxUsd;
  const totalHours = Math.max(humanHours + unmonetizedGovHours, 0.01);
  const impliedHourlyUsd = netValueUsd / totalHours;

  let verdict = 'UNDER_THRESHOLD_CAP';
  if (netValueUsd < 0) verdict = 'KILL_FIREWALL';
  else if (impliedHourlyUsd >= 2 * reservationWageUsdPerHr) verdict = 'PRIORITY_EXECUTE';
  else if (impliedHourlyUsd >= reservationWageUsdPerHr) verdict = 'EXECUTE';

  return {
    verdict,
    netValueUsd: Number(netValueUsd.toFixed(2)),
    governanceTaxUsd: Number(governanceTaxUsd.toFixed(2)),
    impliedHourlyUsd: Number(impliedHourlyUsd.toFixed(2)),
  };
}

export function ensureWorktreeScratchExcludes(gitDirOrRepoRoot) {
  const infoDir = fs.existsSync(path.join(gitDirOrRepoRoot, '.git'))
    ? path.join(gitDirOrRepoRoot, '.git', 'info')
    : path.join(gitDirOrRepoRoot, 'info');
  fs.mkdirSync(infoDir, { recursive: true });
  const excludePath = path.join(infoDir, 'exclude');
  const existing = fs.existsSync(excludePath) ? fs.readFileSync(excludePath, 'utf8') : '';
  const entries = ['.agent-context/', '.agent-output/', 'evidence/'];
  const toAppend = entries.filter((e) => !existing.includes(e));
  if (toAppend.length > 0) {
    fs.appendFileSync(excludePath, (existing.endsWith('\n') || !existing ? '' : '\n') + toAppend.join('\n') + '\n', 'utf8');
  }
  return { excludePath, added: toAppend };
}

export function scanTranscriptForFallbackTrap(transcriptText, expectedModel = null) {
  if (/model_refusal_fallback/i.test(transcriptText)) {
    return { ok: false, reason: 'FIND-393: silent model_refusal_fallback detected in session transcript' };
  }
  if (expectedModel) {
    const modelMatch = transcriptText.match(/"model"\s*:\s*"([^"]+)"/);
    if (modelMatch && modelMatch[1] !== expectedModel) {
      return { ok: false, reason: `FIND-393: model mismatch (expected ${expectedModel}, got ${modelMatch[1]})` };
    }
  }
  return { ok: true, reason: null };
}

/**
 * RC-1A / TC-BO86 Anti-Gaming & Clean-Abort Context-Pack Framing (`Gap LW-2`)
 */
export function renderAgentBriefContract({ cardId = 'TC-UNKNOWN', targetRepo = 'repo' } = {}) {
  return [
    `### Substance, falsifiability & scratch hygiene (${cardId} / TC-BO86)`,
    '',
    `- **No synthetic evidence or threshold weakening:** NEVER commit placeholder replay tokens (e.g. \`${TOK_POOL_SIMULATED}\`), fabricated solver/benchmark logs lacking genuine runtime telemetry, skipped-test inflation (\`it.skip\` / \`test.skip\` / \`pytest.mark.skip\`), or weakened evaluation \`minPassRate\` / dual-threshold conjunction bypasses (deterministic \`SUBSTANCE-01..05\` checks refuse these at CI/merge).`,
    '- **Falsifiable tests only:** Every newly added test file MUST import the real target module under test and assert concrete outcomes — zero-import `assert True` / `expect(true).toBe(true)` stubs are refused (`SUBSTANCE-05`).',
    `- **Scratch & transcript hygiene:** NEVER stage or commit \`.agent-context/\` or \`.agent-output/\` scratch files unless explicitly listed in \`${cardId}\`'s \`**Files to create/modify:**\`; stage explicit file paths only (never \`git add -A\` or \`git add -f\`).`,
    '- **Human-gated completion rule:** NEVER flip a task card to `Status: complete` or `[x]` while `(manual: true)` criteria or open operator gates (`GA-*` / `GD-*` / `*-ACT-*`) remain unattested (`MANUAL-GATE-01`).',
    `- **Blocked-session clean-abort rule:** If genuinely blocked by a missing host binary/solver, missing credential, external rate limit, or unresolvable contract conflict in \`${targetRepo}\`, emit \`AGENT_ABORT: <clear blocker reason>\` (or write \`fail: <reason>\` to \`.agent-stop\`) and exit cleanly rather than pushing empty \`0\`-file commits or placeholder stubs.`,
  ].join('\n');
}

/**
 * Post-session outcome verifier enforcing `TC-BO86` / `RC-1A` / `RC-2A` / `RC-3A` (`Gap LW-2`)
 */
export function classifySessionOutcome({
  exitCode = 0,
  stdout = '',
  stderr = '',
  stopFileText = '',
  changedFiles = [],
  declaredFiles = [],
} = {}) {
  const combined = `${stdout || ''}\n${stderr || ''}`;
  const abortMatch = combined.match(/^\s*AGENT_ABORT:\s*(.+)$/m);
  if (abortMatch) {
    return {
      status: 'aborted_cleanly',
      ok: false,
      retryable: false,
      escalateHitl: true,
      reapDraftPr: changedFiles.length === 0,
      reason: `agent-abort:${abortMatch[1].trim()}`,
    };
  }
  const stopMatch = (stopFileText || '').match(/^\s*fail:\s*(.+)$/im);
  if (stopMatch) {
    return {
      status: 'aborted_cleanly',
      ok: false,
      retryable: false,
      escalateHitl: true,
      reapDraftPr: changedFiles.length === 0,
      reason: `agent-stop:${stopMatch[1].trim()}`,
    };
  }

  const normDeclared = new Set(declaredFiles.map((p) => p.replace(/\\/g, '/').replace(/^\.\//, '')));
  for (const raw of changedFiles) {
    const norm = raw.replace(/\\/g, '/').replace(/^\.\//, '');
    const declaredAllowed =
      normDeclared.has(norm) ||
      [...normDeclared].some((d) => d.endsWith('/') && norm.startsWith(d));
    if (norm.startsWith('.agent-context/') && !declaredAllowed) {
      return {
        status: 'failed_scratch_pollution',
        ok: false,
        retryable: false,
        escalateHitl: true,
        reapDraftPr: false,
        reason: `scratch-pollution:${norm}`,
      };
    }
  }

  if (exitCode === 0 && changedFiles.length === 0) {
    return {
      status: 'failed_empty_diff',
      ok: false,
      retryable: false,
      escalateHitl: true,
      reapDraftPr: true,
      reason: 'empty-pr-diff:0-changed-files',
    };
  }

  if (exitCode !== 0) {
    return {
      status: 'failed_nonzero_exit',
      ok: false,
      retryable: true,
      escalateHitl: false,
      reapDraftPr: changedFiles.length === 0,
      reason: `exit-code:${exitCode}`,
    };
  }

  return {
    status: 'succeeded',
    ok: true,
    retryable: false,
    escalateHitl: false,
    reapDraftPr: false,
    reason: null,
  };
}

function main() {
  const argv = process.argv.slice(2);
  let root = process.cwd();
  let printBriefFor = null;
  let targetRepo = null;
  const cards = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--root') root = path.resolve(argv[++i]);
    else if (argv[i] === '--cards') cards.push(...argv[++i].split(',').map((s) => s.trim()).filter(Boolean));
    else if (argv[i] === '--brief') printBriefFor = argv[++i];
    else if (argv[i] === '--repo') targetRepo = argv[++i];
  }
  if (printBriefFor) {
    process.stdout.write(
      renderAgentBriefContract({ cardId: printBriefFor, targetRepo: targetRepo || path.basename(root) }) + '\n'
    );
    process.exit(0);
  }
  const cfg = loadGovernanceConfig(root);
  const billing = scrubMeteredEnvironment(process.env, cfg);
  const fanIn = detectWaveFileCollisions(root, cards);

  const report = {
    safeToSpawn: fanIn.safeToParallelize,
    strippedMeteredVars: billing.stripped,
    meteredAllowed: billing.meteredAllowed,
    collisions: fanIn.collisions,
  };
  process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  process.exit(report.safeToSpawn ? 0 : 1);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
