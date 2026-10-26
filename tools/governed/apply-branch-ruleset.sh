#!/usr/bin/env bash
# Closes HTD's GA-1 gap: enforces required status checks (`Governed Checks` + `Secrets (gitleaks)`),
# PR-only merges to `main`, and no-force-push via GitHub Repository Rulesets API.
# Usage: ./tools/governed/apply-branch-ruleset.sh <owner/repo>
set -euo pipefail

REPO="${1:?Usage: apply-branch-ruleset.sh <owner/repo>}"

gh api --method POST "repos/${REPO}/rulesets" --input - <<'JSON'
{
  "name": "governed-lightweight-main",
  "target": "branch",
  "enforcement": "active",
  "conditions": {
    "ref_name": {
      "include": ["~DEFAULT_BRANCH"],
      "exclude": []
    }
  },
  "rules": [
    { "type": "deletion" },
    { "type": "non_fast_forward" },
    {
      "type": "pull_request",
      "parameters": {
        "dismiss_stale_reviews_on_push": false,
        "require_code_owner_review": false,
        "require_last_push_approval": false,
        "required_approving_review_count": 0,
        "required_review_thread_resolution": false
      }
    },
    {
      "type": "required_status_checks",
      "parameters": {
        "strict_required_status_checks_policy": true,
        "required_status_checks": [
          { "context": "Governed Checks" },
          { "context": "Secrets (gitleaks)" }
        ]
      }
    }
  ]
}
JSON
echo "Applied governed-lightweight-main ruleset on ${REPO}."
