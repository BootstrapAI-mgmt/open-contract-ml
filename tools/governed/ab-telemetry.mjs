#!/usr/bin/env node
/**
 * Dual-Pipeline Side-by-Side A/B Telemetry Logger & Switchover Comparator (`ab-telemetry.mjs`)
 *
 * Records normalized per-task outcomes across BOTH pipelines (`cc-bo` vs `governed-lightweight`)
 * into append-only JSONL (`data/ab-pipeline-runs.jsonl`) and computes an objective, falsifiable
 * comparison across:
 *   (a) Governance Fidelity: escaped defects, firewall catches, 0-file stub rate, independent receipt rate
 *   (b) Shipping Velocity & Unit Economics: first-pass merge rate, lead time, API-equiv USD, human shepherd min/task
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

function loadGovernanceConfig(root) {
  const cfgPath = path.join(root, 'GOVERNANCE.json');
  return fs.existsSync(cfgPath) ? JSON.parse(fs.readFileSync(cfgPath, 'utf8')) : {};
}

const VALID_PIPELINES = new Set(['cc-bo', 'governed-lightweight']);

export function validateRunRecord(rec) {
  if (!rec || typeof rec !== 'object') throw new Error('Run record must be an object');
  if (!VALID_PIPELINES.has(rec.pipeline)) {
    throw new Error(`Invalid pipeline "${rec.pipeline}" (expected "cc-bo" or "governed-lightweight")`);
  }
  for (const field of ['repo', 'task_id', 'outcome']) {
    if (!rec[field] || typeof rec[field] !== 'string') throw new Error(`Missing string field: ${field}`);
  }
  if (!['merged', 'stub_aborted', 'failed_gate', 'abandoned'].includes(rec.outcome)) {
    throw new Error(`Invalid outcome "${rec.outcome}"`);
  }
  return {
    schema_version: 1,
    timestamp_utc: rec.timestamp_utc || new Date().toISOString(),
    pipeline: rec.pipeline,
    repo: rec.repo,
    task_id: rec.task_id,
    outcome: rec.outcome,
    lead_time_minutes: Number(rec.lead_time_minutes ?? 0),
    human_shepherd_minutes: Number(rec.human_shepherd_minutes ?? 0),
    api_equiv_cost_usd: Number(rec.api_equiv_cost_usd ?? 0),
    actual_metered_usd: Number(rec.actual_metered_usd ?? 0),
    retries: Number(rec.retries ?? 0),
    changed_files: Number(rec.changed_files ?? 0),
    firewall_verified: Boolean(rec.firewall_verified ?? true),
    criteria_receipt_sha256: rec.criteria_receipt_sha256 || null,
    escaped_defect: Boolean(rec.escaped_defect ?? false),
  };
}

export function appendRunRecord(jsonlPath, rec) {
  const clean = validateRunRecord(rec);
  fs.mkdirSync(path.dirname(jsonlPath), { recursive: true });
  fs.appendFileSync(jsonlPath, JSON.stringify(clean) + '\n', 'utf8');
  return clean;
}

function summarizeCohort(rows) {
  const totalAttempts = rows.length;
  const merged = rows.filter((r) => r.outcome === 'merged' && r.changed_files > 0);
  const stubs = rows.filter((r) => r.outcome === 'stub_aborted' || (r.outcome === 'merged' && r.changed_files === 0));
  const firstPassMerged = merged.filter((r) => r.retries === 0);
  const escapedDefects = rows.filter((r) => r.escaped_defect).length;
  const governedMerged = merged.filter((r) => r.firewall_verified && Boolean(r.criteria_receipt_sha256));

  const sum = (arr, fn) => arr.reduce((acc, x) => acc + fn(x), 0);
  const totalHumanMin = sum(rows, (r) => r.human_shepherd_minutes);
  const totalApiEquiv = sum(rows, (r) => r.api_equiv_cost_usd);
  const totalMetered = sum(rows, (r) => r.actual_metered_usd);
  const medianLead = (() => {
    if (merged.length === 0) return null;
    const sorted = merged.map((r) => r.lead_time_minutes).sort((a, b) => a - b);
    const mid = Math.floor(sorted.length / 2);
    return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2;
  })();

  const shippedCount = merged.length;
  return {
    total_attempts: totalAttempts,
    shipped_non_stub_tasks: shippedCount,
    first_pass_merge_rate: totalAttempts > 0 ? Number((firstPassMerged.length / totalAttempts).toFixed(3)) : 0,
    stub_pr_rate: totalAttempts > 0 ? Number((stubs.length / totalAttempts).toFixed(3)) : 0,
    governed_receipt_rate: shippedCount > 0 ? Number((governedMerged.length / shippedCount).toFixed(3)) : 0,
    escaped_defects: escapedDefects,
    median_lead_time_minutes: medianLead,
    human_shepherd_minutes_per_shipped: shippedCount > 0 ? Number((totalHumanMin / shippedCount).toFixed(2)) : null,
    api_equiv_usd_per_shipped: shippedCount > 0 ? Number((totalApiEquiv / shippedCount).toFixed(2)) : null,
    actual_metered_usd_total: Number(totalMetered.toFixed(2)),
  };
}

export function comparePipelines(jsonlPath, thresholds = {}) {
  const gate = {
    min_tasks_per_pipeline: thresholds.min_tasks_per_pipeline ?? 10,
    max_escaped_defects: thresholds.max_escaped_defects ?? 0,
    max_stub_pr_rate: thresholds.max_stub_pr_rate ?? 0.0,
    min_first_pass_merge_rate: thresholds.min_first_pass_merge_rate ?? 0.8,
    min_shepherd_minutes_reduction_ratio: thresholds.min_shepherd_minutes_reduction_ratio ?? 2.0,
  };

  const lines = fs.existsSync(jsonlPath)
    ? fs.readFileSync(jsonlPath, 'utf8').split(/\r?\n/).filter(Boolean).map((l) => JSON.parse(l))
    : [];

  const ccBo = summarizeCohort(lines.filter((r) => r.pipeline === 'cc-bo'));
  const glk = summarizeCohort(lines.filter((r) => r.pipeline === 'governed-lightweight'));

  let verdict = 'MAINTAIN_DUAL_TRIAL';
  const reasons = [];

  if (
    ccBo.shipped_non_stub_tasks < gate.min_tasks_per_pipeline ||
    glk.shipped_non_stub_tasks < gate.min_tasks_per_pipeline
  ) {
    reasons.push(
      `Sample size below threshold (${gate.min_tasks_per_pipeline} shipped tasks/arm required; cc-bo=${ccBo.shipped_non_stub_tasks}, governed-lightweight=${glk.shipped_non_stub_tasks})`
    );
  } else {
    const shepherdRatio =
      glk.human_shepherd_minutes_per_shipped > 0
        ? ccBo.human_shepherd_minutes_per_shipped / glk.human_shepherd_minutes_per_shipped
        : Infinity;

    const meetsGovernance =
      glk.escaped_defects <= gate.max_escaped_defects &&
      glk.stub_pr_rate <= gate.max_stub_pr_rate &&
      glk.governed_receipt_rate === 1;
    const meetsShippingAndCost =
      glk.first_pass_merge_rate >= gate.min_first_pass_merge_rate &&
      shepherdRatio >= gate.min_shepherd_minutes_reduction_ratio;

    if (meetsGovernance && meetsShippingAndCost) {
      verdict = 'SWITCH_TO_GOVERNED_LIGHTWEIGHT';
      reasons.push(
        `Governed Lightweight met 100% receipt/firewall fidelity with 0 escaped defects, ${(glk.first_pass_merge_rate * 100).toFixed(1)}% first-pass merge rate, and ${Number.isFinite(shepherdRatio) ? shepherdRatio.toFixed(1) + 'x' : 'infinite'} reduction in human shepherd minutes/task.`
      );
    } else {
      verdict = 'RETAIN_DUAL_OR_FIX_GAPS';
      if (!meetsGovernance) reasons.push('Governed Lightweight did not meet zero-defect / 100% receipt governance bar.');
      if (!meetsShippingAndCost) reasons.push('Governed Lightweight did not clear first-pass merge or >=2x shepherd reduction bar.');
    }
  }

  return { thresholds: gate, cc_bo: ccBo, governed_lightweight: glk, verdict, reasons };
}

function main() {
  const argv = process.argv.slice(2);
  const sub = argv[0] || 'compare';
  let root = process.cwd();
  let file = null;
  let recordJson = null;

  for (let i = 1; i < argv.length; i++) {
    if (argv[i] === '--root') root = path.resolve(argv[++i]);
    else if (argv[i] === '--file') file = path.resolve(argv[++i]);
    else if (argv[i] === '--record') recordJson = argv[++i];
  }
  const jsonlPath = file || path.join(root, 'data', 'ab-pipeline-runs.jsonl');
  const cfg = loadGovernanceConfig(root);

  if (sub === 'log') {
    if (!recordJson) {
      process.stderr.write('Usage: node tools/governed/ab-telemetry.mjs log --record \'{"pipeline":"governed-lightweight",...}\'\n');
      process.exit(2);
    }
    const saved = appendRunRecord(jsonlPath, JSON.parse(recordJson));
    process.stdout.write(JSON.stringify(saved, null, 2) + '\n');
  } else {
    const report = comparePipelines(jsonlPath, cfg.ab_switchover_thresholds || {});
    process.stdout.write(JSON.stringify(report, null, 2) + '\n');
  }
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  main();
}
