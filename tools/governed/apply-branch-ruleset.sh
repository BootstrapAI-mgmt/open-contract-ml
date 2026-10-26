#!/usr/bin/env bash
# Enforces required status checks, PR-only merges to default branch, and no-force-push
# via GitHub Repository Rulesets API (idempotent PUT-or-POST, reads `required_status_checks`
# from `GOVERNANCE.json` when present so repo-specific CI job names never drift).
# Usage: bash apply-branch-ruleset.sh <owner/repo> [path/to/GOVERNANCE.json]
set -euo pipefail

REPO="${1:?Usage: apply-branch-ruleset.sh <owner/repo> [path/to/GOVERNANCE.json]}"
GOV_JSON="${2:-GOVERNANCE.json}"

PAYLOAD="$(GOV_JSON_PATH="$GOV_JSON" node -e '
const fs = require("node:fs");
const p = process.env.GOV_JSON_PATH;
let checks = ["Governed Checks", "Secrets (gitleaks)"];
if (p && fs.existsSync(p)) {
  const cfg = JSON.parse(fs.readFileSync(p, "utf8"));
  if (Array.isArray(cfg.required_status_checks) && cfg.required_status_checks.length > 0) {
    checks = cfg.required_status_checks;
  }
}
process.stdout.write(JSON.stringify({
  name: "governed-lightweight-main",
  target: "branch",
  enforcement: "active",
  conditions: { ref_name: { include: ["~DEFAULT_BRANCH"], exclude: [] } },
  rules: [
    { type: "deletion" },
    { type: "non_fast_forward" },
    {
      type: "pull_request",
      parameters: {
        dismiss_stale_reviews_on_push: false,
        require_code_owner_review: false,
        require_last_push_approval: false,
        required_approving_review_count: 0,
        required_review_thread_resolution: false
      }
    },
    {
      type: "required_status_checks",
      parameters: {
        strict_required_status_checks_policy: true,
        required_status_checks: checks.map((c) => ({ context: c }))
      }
    }
  ]
}, null, 2));
')"

EXISTING_LIST="$(gh api "repos/${REPO}/rulesets")"
EXISTING_ID="$(RULESETS_RAW="$EXISTING_LIST" node -e '
const list = JSON.parse(process.env.RULESETS_RAW || "[]");
const hit = Array.isArray(list) ? list.find((r) => r.name === "governed-lightweight-main") : null;
process.stdout.write(hit ? String(hit.id) : "");
')"

if [ -n "$EXISTING_ID" ]; then
  printf '%s\n' "$PAYLOAD" | gh api --method PUT "repos/${REPO}/rulesets/${EXISTING_ID}" --input - >/dev/null
  echo "Updated existing governed-lightweight-main ruleset (id=${EXISTING_ID}) on ${REPO}."
else
  printf '%s\n' "$PAYLOAD" | gh api --method POST "repos/${REPO}/rulesets" --input - >/dev/null
  echo "Created governed-lightweight-main ruleset on ${REPO}."
fi
