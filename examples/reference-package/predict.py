"""Reference stdio_json entrypoint for the Contract v1 reference package.

This is a *contract fixture*, not a surrogate. It is a real, deterministic,
dependency-free model -- a log-linear fit with a fixed conformal half-width --
so that every hash, every metric and every gate verdict in this package refers
to something that actually exists and can be recomputed. Nothing here is a
trained network and the model card says so.

Protocol (`invocation.protocol: stdio_json`, the frame the specification's
section 12 defines): one JSON request on stdin, then end of file; one frame per
row on stdout, one per line, exit 0.

    {"run_id": "r1", "mode": "single",
     "inputs": {"peak_temp_K": 873.15, "cycle_count": 5000, "material": "GG25"}}
 -> {"run_id": "r1", "status": "ok",
     "outputs": {"life_cycles": ..., "life_cycles_lower": ..., "life_cycles_upper": ...}}

`mode: "batch"` takes `inputs` as an array and answers one frame per row, in
order. A request the model will not take is answered in band, still exit 0:

 -> {"run_id": "r1", "status": "error",
     "error": {"code": "OUT_OF_RANGE", "message": "...", "field": "material"}}

Run:  echo {"inputs": {...}} | python predict.py
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

WEIGHTS_PATH = Path(__file__).resolve().parent / "model_weights.json"
INPUTS = ("peak_temp_K", "cycle_count", "material")


class Declined(Exception):
    """A request this model will not take: answered in band, never as a crash."""

    def __init__(self, code, message, field=None):
        Exception.__init__(self, message)
        self.code, self.message, self.field = code, message, field


def load_weights():
    return json.loads(WEIGHTS_PATH.read_text(encoding="utf-8"))


def predict(inputs, weights):
    """Deterministic log-linear life model with a fixed split-conformal band."""
    if not isinstance(inputs, dict):
        raise Declined("BAD_REQUEST", "inputs must be a JSON object")
    for name in INPUTS:
        if inputs.get(name) is None:
            raise Declined("MISSING_INPUT", "required input %r is missing" % name, name)
    material = str(inputs["material"])
    if material not in weights["material_offset"]:
        raise Declined("OUT_OF_RANGE", "material %r is outside the declared choices %s"
                       % (material, sorted(weights["material_offset"])), "material")
    try:
        peak_temp_K = float(inputs["peak_temp_K"])
        cycle_count = float(inputs["cycle_count"])
    except (TypeError, ValueError):
        raise Declined("BAD_REQUEST", "peak_temp_K and cycle_count must be numbers")
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


def answer(run_id, inputs, weights):
    """One row's frame: ok with the outputs, or the in-band error."""
    try:
        return {"run_id": run_id, "status": "ok", "outputs": predict(inputs, weights)}
    except Declined as exc:
        error = {"code": exc.code, "message": exc.message}
        if exc.field is not None:
            error["field"] = exc.field
        return {"run_id": run_id, "status": "error", "error": error}


def write_frame(frame):
    sys.stdout.write(json.dumps(frame) + "\n")


def main() -> int:
    try:
        request = json.loads(sys.stdin.read())
    except ValueError as exc:
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "stdin is not JSON: %s" % exc}})
        return 0
    if not isinstance(request, dict):
        write_frame({"run_id": None, "status": "error",
                     "error": {"code": "BAD_REQUEST", "message": "the request must be a JSON object"}})
        return 0
    run_id, inputs = request.get("run_id"), request.get("inputs")
    mode = request.get("mode") or ("batch" if isinstance(inputs, list) else "single")
    if mode not in ("single", "batch") or (mode == "batch") != isinstance(inputs, list):
        write_frame({"run_id": run_id, "status": "error",
                     "error": {"code": "BAD_REQUEST",
                               "message": "mode %r with inputs of type %s: single takes an object, batch an array"
                                          % (mode, type(inputs).__name__)}})
        return 0
    try:
        weights = load_weights()
    except (OSError, ValueError) as exc:              # a broken package, not a bad request
        write_frame({"run_id": run_id, "status": "error",
                     "error": {"code": "INTERNAL_ERROR", "message": "%s: %s" % (type(exc).__name__, exc)}})
        return 1
    for row in (inputs if mode == "batch" else [inputs]):
        write_frame(answer(run_id, row, weights))
    return 0


if __name__ == "__main__":
    sys.exit(main())
