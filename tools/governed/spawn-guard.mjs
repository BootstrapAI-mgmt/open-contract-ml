#!/usr/bin/env node
/**
 * Pre-Launch Collision, Billing Firewall, Risk Scorer, ROI Gate & Worktree Hygiene (`spawn-guard.mjs`)
 *
 * Distills high-leverage primitives from `BO` + `CC` + `market-lab`:
 *   1. `scrubMeteredEnvironment`: `$0.00` metered API firewall (`ANTHROPIC_API_KEY`, `GEMINI_API_KEY`, etc.)
 *   2. `detectWaveFileCollisions`: static file-fan-in lock (`FIND-053`, `FIND-334`)
 *   3. `scoreDiffRisk`: 3-axis blast-radius scorer (`risk_tier.py`) — classifies `{low, medium, high}`, never grants permission
 *   4. `evaluateRoiGate`: `market-lab` reservation-wage (`r* = $125/hr`) + `GovernanceTax` gate
 *   5. `ensureWorktreeScratchExcludes`: writes `.git/info/exclude` for `.agent-context/` & `.agent-output/` (`FIND-315`, `FIND-399`, `FIND-469`)
 *   6. `scanTranscriptForFallbackTrap`: aborts on silent `model_refusal_fallback` (`FIND-393`)
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

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
      cards.set(m[1], { id: m[1], declaredFiles });
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
    'OPENAI_API_KEY',
  ];

  const humanOverride = allowMetered || copy.LW_ALLOW_METERED_API === '1';
  if (guard.subscription_only_default !== false && !humanOverride) {
    for (const key of vars) {
      if (key in copy) {
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

function main() {
  const argv = process.argv.slice(2);
  let root = process.cwd();
  const cards = [];
  for (let i = 0; i < argv.length; i++) {
    if (argv[i] === '--root') root = path.resolve(argv[++i]);
    else if (argv[i] === '--cards') cards.push(...argv[++i].split(',').map((s) => s.trim()).filter(Boolean));
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
