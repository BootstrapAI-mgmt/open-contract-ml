#!/usr/bin/env python3
"""stdio_json entrypoint for brake_disc_link1_thermal_fno -- a contract fixture with no trained model.

The Contract requires the dispatched executable to be one of the hashed
artifacts (rules M012 / M013): an unhashed entrypoint is an unverifiable model
however complete the rest of the provenance block is.  So this file is real, it
is hashed, and it runs.

What it does NOT do is predict.  No model has been trained against the brake-disc
chain's link contracts, so the only honest response to a well-formed request is an
explicit refusal that says why.  Returning a plausible number here would be the
worst available outcome for a trust standard: a caller cannot distinguish an
invented value from a measured one.

Protocol: read one JSON object on stdin, write one JSON object on stdout.
Exit 0 on a well-formed request that is refused, 2 on a malformed request.  The
refusal is in the payload's ``status`` field, never in the exit code alone.
"""

import json
import sys

MODEL_ID = "brake_disc_link1_thermal_fno"
MODEL_VERSION = "1.0.0"
OUTPUTS = ['t_max_K', 't_max_time_s']


def main() -> int:
    raw = sys.stdin.read()
    try:
        request = json.loads(raw) if raw.strip() else {}
    except ValueError as exc:
        json.dump({"status": "error", "model_id": MODEL_ID,
                   "reason": "request is not valid JSON: %s" % exc}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    if not isinstance(request, dict):
        json.dump({"status": "error", "model_id": MODEL_ID,
                   "reason": "request must be a JSON object"}, sys.stdout)
        sys.stdout.write("\n")
        return 2
    json.dump({
        "status": "refused",
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "reason": ("no model has been trained against this contract: this package is a "
                   "Contract fixture for the brake-disc worked instance, whose values are illustrative, "
                   "not measured. See validation_report.json, whose "
                   "overall verdict is FAIL because every Tier-A and Tier-B check is NOT_RUN."),
        "would_return": OUTPUTS,
        "received_keys": sorted(request),
        "advisory": ("Any output of this family is decision-support, not a substitute for "
                     "professional-engineer judgement; a licensed engineer must remain in the loop."),
    }, sys.stdout, indent=2, sort_keys=True)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
