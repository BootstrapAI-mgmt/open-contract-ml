#!/usr/bin/env python3
"""Reference ``stdio_json`` stub model for ``brake_disc_tmf_v1`` (arc TC-601 / TC-GUI07).

This is a **fake** model: it implements the full ``stdio_json`` wire format
(design ``gui-design.md`` §8) with deterministic, plausible-but-synthetic
outputs and **no actual ML**. Its job is to be the dispatch/E2E fixture — the
thing the dispatch engine (arc TC-201) spawns and the end-to-end smoke
(arc TC-603) drives — so the wire format can be exercised end to end before any
real trained model is available. Conflating "the server works" with "the model
is good" is exactly what this stub avoids.

Protocol (design §8):

* **stdin** — one JSON object, then EOF::

      {"run_id": "...", "mode": "single", "inputs": {"peak_temp": 873.15, ...}}

  For ``"mode": "batch"``, ``inputs`` is a JSON *array* of input objects and one
  result object is written per row on stdout, newline-delimited (NDJSON).
* **stdout — success** — ``{"run_id", "status": "ok", "outputs": {...}}``.
* **stdout — error** — ``{"run_id", "status": "error", "error": {code, message, field?}}``.
  A model-level error (e.g. an out-of-envelope input) is a *valid* protocol
  response on stdout with exit code 0 — it is not a crash.
* **stderr** — newline-delimited progress events
  (``{"event": "progress", "pct": .., "message": ".."}``) the server forwards
  over the WebSocket, plus a free-form banner line the server captures into the
  run record's ``stderr_debug`` (never shown to the user by default).

**Units.** The server converts display inputs to each field's
``canonical_units`` *before* spawning the model (design §8; arc TC-105), so this
stub receives — and validates against — the canonical envelope: ``peak_temp`` in
**Kelvin** (``[473.15, 1123.15]`` K), ``cycle_count`` a count in ``[10, 100000]``.

Stdlib only (no third-party imports), so it runs standalone as
``python fake_model.py`` and can be frozen to a single ``fake_model.exe`` with
PyInstaller without dragging in the server package.
"""

from __future__ import annotations

import json
import os
import sys
import time
from typing import Any

# --------------------------------------------------------------------------- #
# Model envelope — canonical units, mirroring the ranges in this folder's
# manifest.yaml. A real model knows its own training envelope; the stub hardcodes
# the brake-disc one so it stays dependency-free (it does not read the manifest).
# --------------------------------------------------------------------------- #
PEAK_TEMP_RANGE = (473.15, 1123.15)  # K  (200-850 degC, the manifest's canonical range)
CYCLE_COUNT_RANGE = (10, 100000)
MATERIALS = ("GG20", "GG25", "GGG70")
MATERIAL_FACTORS = {"GG20": 0.85, "GG25": 1.0, "GGG70": 1.4}
FAILURE_MODES = ("thermal", "mechanical", "interaction")

# "Sleeps briefly" to simulate compute so a progress event is observable before
# the result (design §8). Overridable to 0 in tests via the environment.
SLEEP_S = float(os.environ.get("FAKE_MODEL_SLEEP_S", "0.01"))


class _InvalidInput(Exception):
    """An input the model cannot accept — surfaced as a stdout ``status: error``."""

    def __init__(self, code: str, message: str, field: str | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.field = field


def _as_number(value: Any, field: str) -> float:
    """Coerce a numeric input to ``float`` or raise. ``bool`` is rejected (it is
    an ``int`` subclass and is never a meaningful brake-disc input)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise _InvalidInput("INVALID_TYPE", f"{field} must be a number, got {value!r}", field)
    return float(value)


def validate(inputs: dict[str, Any]) -> None:
    """Validate one row of inputs against the canonical envelope; raise on the first
    problem. Required: ``peak_temp``, ``cycle_count``, ``material``
    (``vent_geometry`` is optional and ignored by this stub)."""
    if not isinstance(inputs, dict):
        raise _InvalidInput("BAD_REQUEST", "inputs must be a JSON object")
    for required in ("peak_temp", "cycle_count", "material"):
        if inputs.get(required) is None:
            raise _InvalidInput(
                "MISSING_INPUT", f"required input {required!r} is missing", required
            )

    peak_temp = _as_number(inputs["peak_temp"], "peak_temp")
    low, high = PEAK_TEMP_RANGE
    if not low <= peak_temp <= high:
        raise _InvalidInput(
            "OUT_OF_RANGE", f"peak_temp={peak_temp} outside [{low}, {high}] K", "peak_temp"
        )

    cycle_count = _as_number(inputs["cycle_count"], "cycle_count")
    clow, chigh = CYCLE_COUNT_RANGE
    if not clow <= cycle_count <= chigh:
        raise _InvalidInput(
            "OUT_OF_RANGE", f"cycle_count={cycle_count} outside [{clow}, {chigh}]", "cycle_count"
        )

    if inputs["material"] not in MATERIALS:
        raise _InvalidInput(
            "UNKNOWN_MATERIAL",
            f"material {inputs['material']!r} not one of {list(MATERIALS)}",
            "material",
        )


def predict(inputs: dict[str, Any]) -> dict[str, Any]:
    """Deterministic synthetic brake-disc TMF prediction. Assumes ``inputs`` already
    passed :func:`validate`. Monotonic and reproducible: hotter discs and higher
    cycle counts shorten life; tougher (spheroidal) iron lengthens it."""
    peak_temp = float(inputs["peak_temp"])
    cycle_count = int(inputs["cycle_count"])
    material = str(inputs["material"])

    span = PEAK_TEMP_RANGE[1] - PEAK_TEMP_RANGE[0]
    thermal = (peak_temp - PEAK_TEMP_RANGE[0]) / span  # 0 at cold edge, 1 at hot edge

    base_life = 60000.0 * (1.0 - 0.80 * thermal)
    life_value = base_life * MATERIAL_FACTORS[material] * (5000.0 / max(cycle_count, 1)) ** 0.25
    life = max(1, round(life_value))
    # Synthetic 90% predictive interval (asymmetric, ~-20% / +25%).
    life_lower = max(1, round(life * 0.80))
    life_upper = round(life * 1.25)

    # Class probabilities, deterministic and summing to exactly 1.0.
    scores = {
        "thermal": thermal + 0.10,
        "mechanical": min(cycle_count / CYCLE_COUNT_RANGE[1], 1.0) + 0.10,
        "interaction": 0.15,
    }
    total = sum(scores.values())
    probs = {mode: round(score / total, 4) for mode, score in scores.items()}
    probs["interaction"] = round(probs["interaction"] + (1.0 - sum(probs.values())), 4)
    failure_mode = max(scores, key=lambda mode: scores[mode])

    return {
        "life": life,
        "life_lower": life_lower,
        "life_upper": life_upper,
        "failure_mode": failure_mode,
        "failure_mode_probs": probs,
    }


def run_one(run_id: Any, inputs: Any) -> dict[str, Any]:
    """Validate + predict one row, returning a protocol result object (ok or error)."""
    try:
        row = inputs if isinstance(inputs, dict) else {}
        validate(row)
        outputs = predict(row)
    except _InvalidInput as exc:
        error: dict[str, Any] = {"code": exc.code, "message": exc.message}
        if exc.field is not None:
            error["field"] = exc.field
        return {"run_id": run_id, "status": "error", "error": error}
    return {"run_id": run_id, "status": "ok", "outputs": outputs}


def _emit_progress(pct: int, message: str) -> None:
    """Write one progress event to stderr (the server forwards these over the WS)."""
    print(json.dumps({"event": "progress", "pct": pct, "message": message}), file=sys.stderr)


def _write_result(result: dict[str, Any]) -> None:
    sys.stdout.write(json.dumps(result) + "\n")


def main(argv: list[str] | None = None) -> int:
    """Read one JSON request on stdin, write the result(s) on stdout; always exit 0
    for a handled request (model errors are reported in-band as ``status: error``)."""
    raw = sys.stdin.read()
    try:
        payload = json.loads(raw)
    except (json.JSONDecodeError, ValueError):
        _write_result(
            {"run_id": None, "status": "error",
             "error": {"code": "BAD_REQUEST", "message": "stdin is not valid JSON"}}
        )
        return 0
    if not isinstance(payload, dict):
        _write_result(
            {"run_id": None, "status": "error",
             "error": {"code": "BAD_REQUEST", "message": "request must be a JSON object"}}
        )
        return 0

    run_id = payload.get("run_id")
    mode = payload.get("mode", "single")
    inputs = payload.get("inputs")

    # Free-form banner -> captured into the run record's stderr_debug (design §8).
    print(f"[fake_model] brake_disc_tmf_v1 dispatch starting (mode={mode})", file=sys.stderr)

    if mode == "batch":
        rows = inputs if isinstance(inputs, list) else []
        for index, row in enumerate(rows):
            pct = round(100 * (index + 1) / max(len(rows), 1))
            _emit_progress(pct, f"row {index + 1}/{len(rows)}")
            if SLEEP_S:
                time.sleep(SLEEP_S)
            _write_result(run_one(run_id, row))
        return 0

    _emit_progress(50, "forward pass")
    if SLEEP_S:
        time.sleep(SLEEP_S)
    result = run_one(run_id, inputs)
    _emit_progress(100, "done")
    _write_result(result)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
