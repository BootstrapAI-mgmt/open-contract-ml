#!/usr/bin/env node
/**
 * Executable Acceptance-Criteria Verifier & Evidence Receipt Emitter (`run-criteria.mjs`)
 *
 * Parses runnable backticked commands in `docs/tasks/*.md` `**Acceptance Criteria:**`,
 * executes them cleanly inside `--root`, and emits SHA-256 tamper-evident receipts
 * (`evidence/<card-id>.receipt.json`) binding git HEAD + command exit codes + output hashes.
 *
 * RC-2D / Gap LW-3 Guard: `(manual: true)` criteria are NEVER recorded as `passed: true`.
 * They record `passed: null, manualPending: true` unless attested, setting
 * `completion_eligible: false` so automated runs cannot mark human-gated cards complete.
 */

import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { spawnSync, execFileSync } from 'node:child_process';
import { fileURLToPath } from 'node:url';
import { parseTaskCards, isRunnableCommandSpan } from './check-governed.mjs';

export function extractCommandFromAc(acLine) {
  const spans = [...acLine.matchAll(/`([^`]+)`/g)].map((m) => m[1].trim());
  for (const span of spans) {
    if (isRunnableCommandSpan(`\`${span}\``)) return span;
  }
  return null;
}

export function runCardCriteria(root, cardId, { dryRun = false, outDir = null } = {}) {
  const cards = parseTaskCards(root);
  const card = cards.get(cardId);
  if (!card) throw new Error(`Unknown task card: ${cardId}`);

  let headSha = 'uncommitted-worktree';
  try {
    headSha = execFileSync('git', ['-C', root, 'rev-parse', 'HEAD'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    }).trim();
  } catch {
    // non-git fixture directory allowed in unit tests
  }

  const hasManualAttestation = Boolean(card.manualAttestation && card.manualAttestation.trim().length > 0);
  const results = [];
  for (let idx = 0; idx < card.acLines.length; idx++) {
    const line = card.acLines[idx];
    if (/\(\s*manual\s*:\s*true\s*\)/i.test(line)) {
      results.push({
        index: idx + 1,
        line,
        mode: 'manual',
        passed: hasManualAttestation ? true : null,
        manualPending: !hasManualAttestation,
        exitCode: null,
        outputHash: null,
      });
      continue;
    }
    const cmd = extractCommandFromAc(line);
    if (!cmd) {
      results.push({ index: idx + 1, line, mode: 'unrunnable', passed: false, exitCode: null, outputHash: null });
      continue;
    }
    if (dryRun) {
      results.push({ index: idx + 1, line, command: cmd, mode: 'dry-run', passed: true, exitCode: 0, outputHash: null });
      continue;
    }
    const proc = spawnSync(cmd, {
      cwd: root,
      shell: true,
      encoding: 'utf8',
      timeout: 120_000,
      env: { ...process.env, PYTHONUTF8: '1' },
    });
    const combined = `${proc.stdout || ''}${proc.stderr || ''}`;
    const outputHash = crypto.createHash('sha256').update(combined).digest('hex');
    results.push({
      index: idx + 1,
      line,
      command: cmd,
      mode: 'executed',
      passed: proc.status === 0,
      exitCode: proc.status,
      outputHash,
    });
  }

  const automatedCriteria = results.filter((r) => r.mode !== 'manual');
  const pendingManualCount = results.filter((r) => r.manualPending).length;
  const automatedPassed = automatedCriteria.every((r) => r.passed === true);
  const completionEligible = automatedPassed && pendingManualCount === 0;

  const receiptPayload = {
    schema_version: 1,
    card_id: cardId,
    git_head: headSha,
    dry_run: dryRun,
    timestamp_utc: new Date().toISOString(),
    passed: automatedPassed,
    automated_passed: automatedPassed,
    pending_manual_count: pendingManualCount,
    completion_eligible: completionEligible,
    criteria: results,
  };
  const receiptDigest = crypto
    .createHash('sha256')
    .update(
      JSON.stringify({
        card_id: cardId,
        git_head: headSha,
        automated_passed: automatedPassed,
        pending_manual_count: pendingManualCount,
        completion_eligible: completionEligible,
        criteria: results,
      })
    )
    .digest('hex');
  receiptPayload.receipt_sha256 = receiptDigest;

  if (outDir) {
    fs.mkdirSync(outDir, { recursive: true });
    fs.writeFileSync(path.join(outDir, `${cardId}.receipt.json`), JSON.stringify(receiptPayload, null, 2) + '\n', 'utf8');
  }
  return receiptPayload;
}

function main() {
  const argv = process.argv.slice(2);
  let root = process.cwd();
  let dryRun = false;
  let all = false;
  let requireCompletionEligible = false;
  let outDir = null;
  const cardIds = [];

  for (let i = 0; i < argv.length; i++) {
    const a = argv[i];
    if (a === '--root') root = path.resolve(argv[++i]);
    else if (a === '--dry-run') dryRun = true;
    else if (a === '--all') all = true;
    else if (a === '--require-completion-eligible') requireCompletionEligible = true;
    else if (a === '--out') outDir = path.resolve(argv[++i]);
    else if (a === '--card') cardIds.push(...argv[++i].split(',').map((s) => s.trim()).filter(Boolean));
  }

  const cards = parseTaskCards(root);
  const targets = all ? [...cards.keys()] : cardIds;
  if (targets.length === 0) {
    process.stderr.write(
      'Usage: node scripts/run-criteria.mjs (--card <TC-ID> | --all) [--dry-run] [--require-completion-eligible] [--out <dir>]\n'
    );
    process.exit(2);
  }

  let allPassed = true;
  for (const id of targets) {
    const receipt = runCardCriteria(root, id, { dryRun, outDir });
    const ok = requireCompletionEligible ? receipt.completion_eligible : receipt.automated_passed;
    if (!ok) allPassed = false;
    const manualSuffix =
      receipt.pending_manual_count > 0 ? `, ${receipt.pending_manual_count} manual gate(s) pending` : '';
    process.stdout.write(
      `[${ok ? 'PASS' : 'FAIL'}] ${id}: ${receipt.criteria.length} criteria (${dryRun ? 'dry-run' : `sha256:${receipt.receipt_sha256.slice(0, 12)}`}${manualSuffix})\n`
    );
  }
  process.exit(allPassed ? 0 : 1);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
