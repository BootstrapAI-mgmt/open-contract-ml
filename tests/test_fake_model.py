"""Tests for the brake-disc reference stub model.

Two layers: subprocess tests drive the real ``stdio_json`` wire format end to end
(single, batch and out-of-range requests),
and in-process tests import the stub's pure functions to assert the synthetic
prediction is deterministic and monotonic.
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
from typing import Any

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

FAKE_MODEL = REPO_ROOT / "examples" / "brake_disc_tmf_v1" / "fake_model.py"

SINGLE_INPUTS = {"peak_temp": 873.15, "cycle_count": 5000, "material": "GG25"}
OUTPUT_FIELDS = ("life", "life_lower", "life_upper", "failure_mode", "failure_mode_probs")


def _run(payload: object) -> subprocess.CompletedProcess[str]:
    """Invoke the stub as a subprocess, feeding ``payload`` as JSON on stdin."""
    env = {**os.environ, "FAKE_MODEL_SLEEP_S": "0"}
    return subprocess.run(
        [sys.executable, str(FAKE_MODEL)],
        input=json.dumps(payload),
        capture_output=True,
        text=True,
        env=env,
        timeout=30,
    )


def _load_stub() -> Any:
    spec = importlib.util.spec_from_file_location("fake_model", FAKE_MODEL)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


fake_model: Any = _load_stub()


# --------------------------------------------------------------------------- #
# Wire format — single, batch, out of range (subprocess)
# --------------------------------------------------------------------------- #
def test_single_ok_returns_all_output_fields() -> None:
    # A single request returns status ok with every declared output field.
    proc = _run({"run_id": "t", "mode": "single", "inputs": SINGLE_INPUTS})
    assert proc.returncode == 0
    result = json.loads(proc.stdout)
    assert result["status"] == "ok"
    assert result["run_id"] == "t"
    for field in OUTPUT_FIELDS:
        assert field in result["outputs"], field


def test_batch_emits_one_ndjson_object_per_row() -> None:
    # Batch mode emits one newline-delimited JSON object per input row.
    rows = [
        SINGLE_INPUTS,
        {"peak_temp": 1023.15, "cycle_count": 20000, "material": "GGG70"},
        {"peak_temp": 573.15, "cycle_count": 200, "material": "GG20"},
    ]
    proc = _run({"run_id": "b", "mode": "batch", "inputs": rows})
    assert proc.returncode == 0
    lines = [line for line in proc.stdout.splitlines() if line.strip()]
    assert len(lines) == len(rows)
    results = [json.loads(line) for line in lines]
    assert all(r["status"] == "ok" for r in results)
    assert all(set(OUTPUT_FIELDS) <= set(r["outputs"]) for r in results)


def test_out_of_range_peak_temp_returns_error() -> None:
    # peak_temp above the canonical envelope (1123.15 K) is rejected loudly.
    proc = _run({"run_id": "t", "mode": "single",
                 "inputs": {"peak_temp": 1200.0, "cycle_count": 5000, "material": "GG25"}})
    assert proc.returncode == 0  # a model error is in-band, not a crash
    result = json.loads(proc.stdout)
    assert result["status"] == "error"
    assert result["error"]["code"] == "OUT_OF_RANGE"
    assert result["error"]["field"] == "peak_temp"


# --------------------------------------------------------------------------- #
# Wire format — robustness (subprocess)
# --------------------------------------------------------------------------- #
def test_batch_reports_partial_results_for_mixed_rows() -> None:
    # One bad row errors in place and the rest still succeed, so a batch caller
    # gets partial results instead of losing the whole batch to one row.
    rows = [SINGLE_INPUTS, {"peak_temp": 9999.0, "cycle_count": 5000, "material": "GG25"}]
    proc = _run({"run_id": "b", "mode": "batch", "inputs": rows})
    results = [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]
    assert results[0]["status"] == "ok"
    assert results[1]["status"] == "error"
    assert results[1]["error"]["code"] == "OUT_OF_RANGE"


def test_progress_event_and_banner_on_stderr() -> None:
    proc = _run({"run_id": "t", "mode": "single", "inputs": SINGLE_INPUTS})
    progress = [
        json.loads(line)
        for line in proc.stderr.splitlines()
        if line.strip().startswith("{") and "progress" in line
    ]
    assert progress, proc.stderr
    assert progress[0]["event"] == "progress"
    # The free-form banner is captured into stderr_debug, never parsed as JSON.
    assert "[fake_model]" in proc.stderr


def test_bad_json_stdin_reports_bad_request() -> None:
    proc = subprocess.run(
        [sys.executable, str(FAKE_MODEL)],
        input="this is not json",
        capture_output=True,
        text=True,
        env={**os.environ, "FAKE_MODEL_SLEEP_S": "0"},
        timeout=30,
    )
    result = json.loads(proc.stdout)
    assert result["status"] == "error"
    assert result["error"]["code"] == "BAD_REQUEST"


def test_missing_required_input_errors() -> None:
    proc = _run({"run_id": "t", "inputs": {"peak_temp": 873.15, "cycle_count": 5000}})
    result = json.loads(proc.stdout)
    assert result["status"] == "error"
    assert result["error"]["code"] == "MISSING_INPUT"
    assert result["error"]["field"] == "material"


def test_unknown_material_errors() -> None:
    proc = _run({"run_id": "t", "inputs": {**SINGLE_INPUTS, "material": "TITANIUM"}})
    result = json.loads(proc.stdout)
    assert result["status"] == "error"
    assert result["error"]["code"] == "UNKNOWN_MATERIAL"


# --------------------------------------------------------------------------- #
# Prediction logic (in-process)
# --------------------------------------------------------------------------- #
def test_predict_is_deterministic() -> None:
    assert fake_model.predict(SINGLE_INPUTS) == fake_model.predict(SINGLE_INPUTS)


def test_uq_band_brackets_the_point_prediction() -> None:
    out = fake_model.predict(SINGLE_INPUTS)
    assert out["life_lower"] <= out["life"] <= out["life_upper"]
    assert out["life_lower"] < out["life_upper"]


def test_hotter_disc_predicts_shorter_life() -> None:
    cool = fake_model.predict({**SINGLE_INPUTS, "peak_temp": 573.15})
    hot = fake_model.predict({**SINGLE_INPUTS, "peak_temp": 1073.15})
    assert hot["life"] < cool["life"]


def test_more_cycles_predicts_shorter_life() -> None:
    few = fake_model.predict({**SINGLE_INPUTS, "cycle_count": 100})
    many = fake_model.predict({**SINGLE_INPUTS, "cycle_count": 90000})
    assert many["life"] < few["life"]


def test_tougher_material_predicts_longer_life() -> None:
    weak = fake_model.predict({**SINGLE_INPUTS, "material": "GG20"})
    mid = fake_model.predict({**SINGLE_INPUTS, "material": "GG25"})
    tough = fake_model.predict({**SINGLE_INPUTS, "material": "GGG70"})
    assert weak["life"] < mid["life"] < tough["life"]


def test_failure_mode_probs_sum_to_one_and_match_argmax() -> None:
    out = fake_model.predict(SINGLE_INPUTS)
    probs = out["failure_mode_probs"]
    assert set(probs) == set(fake_model.FAILURE_MODES)
    assert round(sum(probs.values()), 6) == 1.0
    assert out["failure_mode"] in fake_model.FAILURE_MODES
    assert out["failure_mode"] == max(probs, key=lambda mode: probs[mode])
