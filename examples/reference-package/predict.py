"""Reference stdio_json entrypoint for the Contract v1 reference package.

This is a *contract fixture*, not a surrogate. It is a real, deterministic,
dependency-free model -- a log-linear fit with a fixed conformal half-width --
so that every hash, every metric and every gate verdict in this package refers
to something that actually exists and can be recomputed. Nothing here is a
trained network and the model card says so.

Protocol (cae-ml-gui `invocation.protocol: stdio_json`): read one JSON object
from stdin, write one JSON object to stdout, exit 0.

    {"inputs": {"peak_temp_K": 873.15, "cycle_count": 5000, "material": "GG25"}}
 -> {"outputs": {"life_cycles": ..., "life_cycles_lower": ..., "life_cycles_upper": ...}}

Run:  echo {"inputs": {...}} | python predict.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WEIGHTS_PATH = Path(__file__).resolve().parent / "model_weights.json"


def load_weights():
    return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))


def predict(inputs, weights):
    """Deterministic log-linear life model with a fixed split-conformal band."""
    material = str(inputs["material"])
    if material not in weights["material_offset"]:
        raise ValueError("material %r is outside the declared choices %s"
                         % (material, sorted(weights["material_offset"])))
    peak_temp_K = float(inputs["peak_temp_K"])
    cycle_count = float(inputs["cycle_count"])
    log_life = (weights["intercept"]
                + weights["beta_peak_temp"] * peak_temp_K
                + weights["beta_log_cycles"] * math.log(max(cycle_count, 1.0))
                + weights["material_offset"][material])
    half = weights["conformal_half_width_log"]
    return {
        "life_cycles": math.exp(log_life),
        "life_cycles_lower": math.exp(log_life - half),
        "life_cycles_upper": math.exp(log_life + half),
    }


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
        outputs = predict(request["inputs"], load_weights())
    except Exception as exc:                      # the protocol reports failure in-band
        json.dump({"error": "%s: %s" % (type(exc).__name__, exc)}, sys.stdout)
        sys.stdout.write("\n")
        return 1
    json.dump({"outputs": outputs}, sys.stdout)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
