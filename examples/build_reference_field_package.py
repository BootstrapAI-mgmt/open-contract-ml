"""Build examples/reference-field-package/ from its seeded synthetic corpus, or check that it reproduces.

    python examples/build_reference_field_package.py --commit <sha>    write the package's generated files
    python examples/build_reference_field_package.py --check           rebuild and compare; exit 1 on any difference
    python examples/build_reference_field_package.py --measure-runtime time five single calls of the entrypoint

--package <dir> points any of the three at another copy of the package.

The entrypoint, predict.py, is written by hand. This script writes the other
four files of the package -- model_weights.json, manifest.yaml,
validation_report.json and model_card.md -- from one seeded corpus, so every
number in them is computed rather than typed. It builds into a temporary copy of
the package; --check then compares that copy with the files on disk.

It uses the standard library alone, and in every number it writes only
operations IEEE 754 requires to be correctly rounded (addition, subtraction,
multiplication, division, square root), with sums taken by math.fsum. No result
therefore depends on the platform's maths library, and the files come out
byte-identical on any machine that runs Python 3.11 or later.

Two values are recorded rather than re-derived on each run: the entrypoint's
runtime (C4), measured with --measure-runtime under the interpreter
RECORDED_PYTHON names, and the commit the package was built from, which --check
reads back from the manifest it compares with.
"""

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import math
import os
import random
import re
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

sys.dont_write_bytecode = True

HERE = Path(__file__).resolve().parent
PACKAGE = HERE / "reference-field-package"
GENERATED = ("model_weights.json", "manifest.yaml", "validation_report.json", "model_card.md")

MODEL_ID = "contract_reference_plate_field_v1"
MODEL_VERSION = "1.0.0"
SPEC_VERSION = "1.1"
BUILD_DATE = "2026-10-07"
CORPUS_VERSION = "contract-reference-field-corpus-1.0"
REPO_URL = "https://github.com/BootstrapAI-mgmt/open-contract-ml"
#: The interpreter the runtime below was measured under, and that built the package.
RECORDED_PYTHON = "3.11.15"
#: The median of five single calls of the entrypoint, from --measure-runtime (Linux, the interpreter above).
RECORDED_RUNTIME_S = 0.0345

# The plate, the corpus and the model's fixed parts.
CONDUCTIVITY_W_MK = 50.0
THICKNESS_M = 0.004
NODES = 17
RANGES = {"power_W": (5.0, 50.0), "length_m": (0.05, 0.2), "width_m": (0.05, 0.2)}
TRUE_AMPLITUDE = 3.0
NOISE_FRACTION_OF_PEAK = 0.01
SEED_CORPUS, SEED_SPLIT = 0, 1
N_DESIGNS, N_CORNER, N_TRAIN, N_CAL, N_TEST = 1000, 100, 400, 250, 250
LEVEL = 0.9
SIGNIFICANT = 6

# Every bar, fixed before any measurement.
THRESHOLDS = {
    "A1_accuracy": {"rel_l2_mean_max": 0.05, "rel_l2_worst_max": 0.1},
    "A2_extrapolation": {"degradation_max": 3.0, "rel_l2_extrap_max": 0.1},
    "A3_uq_calibration": {"coverage_band_lo": 0.85, "coverage_band_hi": 0.96},
    "A4_baseline_beat": {"beat_mean_max_ratio": 0.5},
    "A5_reproducibility": {"tolerance": 0.0},
    "B1_monotonicity": {"violation_fraction_max": 0.0},
    "B2_bounds": {"lower_bound_K": 0.0, "max_violations": 0},
    "B3_residual": {"relative_residual_max": 0.01},
    "B4_conservation": {"imbalance_max": 0.01},
    "B5_invariance": {"max_abs_diff_allowed_K": 1e-09},
    "C1_ood_guard": {"min_pass_fraction_id": 0.95, "far_out_must_refuse": 1},
    "C2_serve_parity": {"max_rel_diff_allowed": 1e-09},
    "C3_provenance_integrity": {"max_hash_mismatches": 0},
    "C4_deployment_readiness": {"declarations_required": 4, "timeout_s": 60},
}
DECLARATIONS = {
    "validation_anchor": "illustrative: a Contract fixture fitted to a synthetic corpus, not a validated surrogate",
    "inference_target": "workstation, single call, standard-library Python",
    "retrain_cadence": "not scheduled (fixture)",
    "owner_escalation": "open-contract-ml@example.invalid",
}
EXAMPLES = [
    ("A square plate at moderate power", {"power_W": 20.0, "length_m": 0.1, "width_m": 0.1}),
    ("A long, narrow plate at full power", {"power_W": 50.0, "length_m": 0.2, "width_m": 0.05}),
]
SERVE_CASES = [
    {"power_W": 5.0, "length_m": 0.05, "width_m": 0.05},
    {"power_W": 50.0, "length_m": 0.2, "width_m": 0.2},
    {"power_W": 20.0, "length_m": 0.1, "width_m": 0.1},
    {"power_W": 50.0, "length_m": 0.2, "width_m": 0.05},
    {"power_W": 5.0, "length_m": 0.05, "width_m": 0.2},
    {"power_W": 35.0, "length_m": 0.12, "width_m": 0.08},
]
FAR_OUT = {"power_W": 500.0, "length_m": 0.1, "width_m": 0.1}


def sig(x: float) -> float:
    """x rounded to SIGNIFICANT significant digits (a correctly rounded decimal conversion)."""
    return float("%.*g" % (SIGNIFICANT, x))


# --------------------------------------------------------------------------- #
# The model, written independently of predict.py with the same operation order,
# so that C2 compares two implementations and not one with itself.
# --------------------------------------------------------------------------- #
def shape(n: int) -> List[float]:
    steps = n - 1
    return [(i / steps) * (1.0 - i / steps) for i in range(n)]


def field(amplitude: float, power: float, length: float, width: float, n: int = NODES) -> List[float]:
    k_t = CONDUCTIVITY_W_MK * THICKNESS_M
    scale = amplitude * power * length * width / (k_t * (length * length + width * width))
    s = shape(n)
    return [scale * (s[i] * s[j]) for j in range(n) for i in range(n)]


def heating(power: float, length: float, width: float, x: float, y: float) -> float:
    """The heating density, W/m^2, whose solution with every edge at zero rise is the field at amplitude 3."""
    return 6.0 * power * (x * (length - x) + y * (width - y)) / (length * width * (length * length + width * width))


# --------------------------------------------------------------------------- #
# The corpus and its splits.
# --------------------------------------------------------------------------- #
class Design:
    def __init__(self, power: float, length: float, width: float, values: List[float]):
        self.power, self.length, self.width, self.values = power, length, width, values

    @property
    def inputs(self) -> Dict[str, float]:
        return {"power_W": self.power, "length_m": self.length, "width_m": self.width}


def unit_noise(rng: random.Random) -> float:
    """Mean 0, variance 1: the sum of twelve uniform draws, less six."""
    total = 0.0
    for _ in range(12):
        total += rng.random()
    return total - 6.0


def make_corpus() -> List[Design]:
    rng = random.Random(SEED_CORPUS)
    designs = []
    for _ in range(N_DESIGNS):
        power, length, width = (lo + (hi - lo) * rng.random() for lo, hi in RANGES.values())
        clean = field(TRUE_AMPLITUDE, power, length, width)
        spread = NOISE_FRACTION_OF_PEAK * max(clean)
        designs.append(Design(power, length, width, [v + spread * unit_noise(rng) for v in clean]))
    return designs


def corpus_sha256(designs: Sequence[Design]) -> str:
    lines = ["%r %r %r %s" % (d.power, d.length, d.width, " ".join(repr(v) for v in d.values)) for d in designs]
    return hashlib.sha256(("\n".join(lines) + "\n").encode("utf-8")).hexdigest()


def split(designs: Sequence[Design]) -> Dict[str, List[Design]]:
    by_power = sorted(range(len(designs)), key=lambda k: (designs[k].power, k))
    corner = set(by_power[-N_CORNER:])
    interior = [k for k in range(len(designs)) if k not in corner]
    rng = random.Random(SEED_SPLIT)
    keys = [rng.random() for _ in interior]
    order = [interior[k] for k in sorted(range(len(interior)), key=lambda k: (keys[k], k))]
    return {"train": [designs[k] for k in order[:N_TRAIN]],
            "cal": [designs[k] for k in order[N_TRAIN:N_TRAIN + N_CAL]],
            "test_id": [designs[k] for k in order[N_TRAIN + N_CAL:N_TRAIN + N_CAL + N_TEST]],
            "test_extrap": [designs[k] for k in sorted(corner)]}


# --------------------------------------------------------------------------- #
# The fit: one amplitude by least squares, two half-widths by split conformal.
# --------------------------------------------------------------------------- #
def conformal_rank(n: int) -> int:
    """ceil((n + 1) * LEVEL) for LEVEL = 0.9, in integer arithmetic."""
    return -(-(n + 1) * 9 // 10)


def field_score(d: Design, amplitude: float) -> float:
    pred = field(amplitude, d.power, d.length, d.width)
    return max(abs(p - y) for p, y in zip(pred, d.values)) / max(pred)


def peak_score(d: Design, amplitude: float) -> float:
    pred = field(amplitude, d.power, d.length, d.width)
    centre = (NODES // 2) * NODES + NODES // 2
    return abs(d.values[centre] - max(pred)) / max(pred)


def fit(splits: Dict[str, List[Design]]) -> Dict[str, float]:
    """The raw (unrounded) amplitude and half-widths."""
    products, squares = [], []
    for d in splits["train"]:
        for b, y in zip(field(1.0, d.power, d.length, d.width), d.values):
            products.append(b * y)
            squares.append(b * b)
    amplitude = math.fsum(products) / math.fsum(squares)
    k = conformal_rank(len(splits["cal"]))
    field_half = sorted(field_score(d, amplitude) for d in splits["cal"])[k - 1]
    peak_half = sorted(peak_score(d, amplitude) for d in splits["cal"])[k - 1]
    return {"amplitude": amplitude, "field_half_width": field_half, "peak_half_width": peak_half}


def weights_document(raw: Dict[str, float]) -> Dict[str, Any]:
    return {
        "model": "closed-form temperature rise over a heated plate, one fitted amplitude",
        "amplitude": sig(raw["amplitude"]),
        "conductivity_W_mK": CONDUCTIVITY_W_MK,
        "thickness_m": THICKNESS_M,
        "nodes_per_side": NODES,
        "field_half_width": sig(raw["field_half_width"]),
        "peak_half_width": sig(raw["peak_half_width"]),
        "band_level": LEVEL,
        "input_ranges": {name: list(bounds) for name, bounds in RANGES.items()},
    }


# --------------------------------------------------------------------------- #
# The measurements: every check, against the weights the package ships.
# --------------------------------------------------------------------------- #
def rel_l2(pred: Sequence[float], truth: Sequence[float]) -> float:
    return math.sqrt(math.fsum((p - y) * (p - y) for p, y in zip(pred, truth))) / math.sqrt(
        math.fsum(y * y for y in truth))


def accuracy(designs: Sequence[Design], amplitude: float) -> Dict[str, float]:
    errors, squared = [], []
    for d in designs:
        pred = field(amplitude, d.power, d.length, d.width)
        errors.append(rel_l2(pred, d.values))
        squared.extend((p - y) * (p - y) for p, y in zip(pred, d.values))
    return {"rel_l2_mean": math.fsum(errors) / len(errors), "rel_l2_worst": max(errors),
            "rmse_K": math.sqrt(math.fsum(squared) / len(squared)), "n": len(designs)}


def coverage(designs: Sequence[Design], weights: Dict[str, Any]) -> Tuple[float, float]:
    centre = (NODES // 2) * NODES + NODES // 2
    inside_field = inside_peak = 0
    for d in designs:
        pred = field(weights["amplitude"], d.power, d.length, d.width)
        peak = max(pred)
        if max(abs(p - y) for p, y in zip(pred, d.values)) <= weights["field_half_width"] * peak:
            inside_field += 1
        if abs(d.values[centre] - peak) <= weights["peak_half_width"] * peak:
            inside_peak += 1
    return inside_field / len(designs), inside_peak / len(designs)


def baseline(train: Sequence[Design], test: Sequence[Design], amplitude: float) -> Dict[str, float]:
    count = NODES * NODES
    mean_field = [math.fsum(d.values[k] for d in train) / len(train) for k in range(count)]
    model_sq, mean_sq = [], []
    for d in test:
        pred = field(amplitude, d.power, d.length, d.width)
        model_sq.extend((p - y) * (p - y) for p, y in zip(pred, d.values))
        mean_sq.extend((m - y) * (m - y) for m, y in zip(mean_field, d.values))
    rmse_model = math.sqrt(math.fsum(model_sq) / len(model_sq))
    rmse_mean = math.sqrt(math.fsum(mean_sq) / len(mean_sq))
    return {"rmse_model_K": rmse_model, "rmse_mean_field_K": rmse_mean, "ratio_vs_mean": rmse_model / rmse_mean,
            "n": len(test)}


def monotonicity(amplitude: float) -> Dict[str, float]:
    geometries = [(length, width) for width in (0.075, 0.175) for length in (0.05, 0.1, 0.15, 0.2)]
    lo, hi = RANGES["power_W"]
    powers = [lo + (hi - lo) * k / 63 for k in range(64)]
    peak_drops = node_drops = steps = 0
    for length, width in geometries:
        previous = None
        for power in powers:
            values = field(amplitude, power, length, width)
            if previous is not None:
                steps += 1
                peak_drops += max(values) < max(previous)
                node_drops += sum(1 for v, p in zip(values, previous) if v < p)
            previous = values
    return {"violation_fraction_peak": peak_drops / steps,
            "violation_fraction_nodes": node_drops / (steps * NODES * NODES),
            "n_probe_points": len(geometries) * len(powers)}


def bounds(amplitude: float) -> Dict[str, float]:
    levels = {name: [lo + (hi - lo) * k / 15 for k in range(16)] for name, (lo, hi) in RANGES.items()}
    lowest, violations, points = math.inf, 0, 0
    for power in levels["power_W"]:
        for length in levels["length_m"]:
            for width in levels["width_m"]:
                values = field(amplitude, power, length, width)
                lowest = min(lowest, min(values))
                violations += sum(1 for v in values if v < THRESHOLDS["B2_bounds"]["lower_bound_K"])
                points += 1
    return {"n_probe_points": points, "n_violations": violations, "min_predicted_rise_K": lowest}


def grid(values: Sequence[float], n: int = NODES) -> List[List[float]]:
    return [list(values[j * n:(j + 1) * n]) for j in range(n)]


def residual(designs: Sequence[Design], amplitude: float) -> Dict[str, float]:
    k_t = CONDUCTIVITY_W_MK * THICKNESS_M
    steps = NODES - 1
    worst, ratios = 0.0, []
    for d in designs:
        t = grid(field(amplitude, d.power, d.length, d.width))
        hx, hy = d.length / steps, d.width / steps
        r_sq, q_sq = [], []
        for j in range(1, steps):
            for i in range(1, steps):
                lap = ((t[j][i + 1] - 2.0 * t[j][i] + t[j][i - 1]) / (hx * hx)
                       + (t[j + 1][i] - 2.0 * t[j][i] + t[j - 1][i]) / (hy * hy))
                q = heating(d.power, d.length, d.width, (i / steps) * d.length, (j / steps) * d.width)
                r_sq.append((k_t * lap + q) * (k_t * lap + q))
                q_sq.append(q * q)
        ratio = math.sqrt(math.fsum(r_sq)) / math.sqrt(math.fsum(q_sq))
        ratios.append(ratio)
        worst = max(worst, ratio)
    return {"relative_residual_worst": worst, "relative_residual_mean": math.fsum(ratios) / len(ratios),
            "n": len(designs), "nodes_per_design": (NODES - 2) * (NODES - 2)}


def simpson(values: Sequence[float], h: float) -> float:
    weights = [1.0] + [4.0 if k % 2 else 2.0 for k in range(1, len(values) - 1)] + [1.0]
    return h / 3.0 * math.fsum(w * v for w, v in zip(weights, values))


def conservation(designs: Sequence[Design], amplitude: float) -> Dict[str, float]:
    """Heat generated in the plate against heat conducted out through its four edges, on the prediction."""
    k_t = CONDUCTIVITY_W_MK * THICKNESS_M
    steps = NODES - 1
    worst = 0.0
    for d in designs:
        t = grid(field(amplitude, d.power, d.length, d.width))
        hx, hy = d.length / steps, d.width / steps
        # outward conduction per unit edge length, from second-order one-sided differences
        west = [k_t * (-3.0 * t[j][0] + 4.0 * t[j][1] - t[j][2]) / (2.0 * hx) for j in range(NODES)]
        east = [k_t * (-3.0 * t[j][steps] + 4.0 * t[j][steps - 1] - t[j][steps - 2]) / (2.0 * hx)
                for j in range(NODES)]
        south = [k_t * (-3.0 * t[0][i] + 4.0 * t[1][i] - t[2][i]) / (2.0 * hy) for i in range(NODES)]
        north = [k_t * (-3.0 * t[steps][i] + 4.0 * t[steps - 1][i] - t[steps - 2][i]) / (2.0 * hy)
                 for i in range(NODES)]
        out = math.fsum([simpson(west, hy), simpson(east, hy), simpson(south, hx), simpson(north, hx)])
        generated = d.power
        worst = max(worst, abs(generated - out) / (generated + abs(out)))
    return {"relative_imbalance": worst, "n": len(designs)}


def invariance(designs: Sequence[Design], amplitude: float) -> Dict[str, float]:
    fine_n = 2 * NODES - 1
    worst = 0.0
    for d in designs:
        coarse = grid(field(amplitude, d.power, d.length, d.width))
        fine = grid(field(amplitude, d.power, d.length, d.width, fine_n), fine_n)
        for j in range(NODES):
            for i in range(NODES):
                worst = max(worst, abs(coarse[j][i] - fine[2 * j][2 * i]))
    return {"max_abs_diff_K": worst, "n": len(designs), "fine_nodes_per_side": fine_n}


def load_entrypoint(pkg: Path) -> Any:
    spec = importlib.util.spec_from_file_location("reference_field_predict", pkg / "predict.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def ood_guard(pkg: Path, test: Sequence[Design], weights: Dict[str, Any]) -> Dict[str, float]:
    entry = load_entrypoint(pkg)
    passed = 0
    for d in test:
        try:
            entry.read_inputs(d.inputs, weights)
            passed += 1
        except entry.Declined:
            pass
    try:
        entry.read_inputs(FAR_OUT, weights)
        refused = 0
    except entry.Declined:
        refused = 1
    return {"pass_fraction_test_id": passed / len(test), "far_out_design_refused": refused, "n": len(test)}


def read_array(path: Path, name: str) -> List[float]:
    text = path.read_text(encoding="utf-8")
    start = text.index('Name="%s"' % name)
    body = text[text.index(">", start) + 1:text.index("</DataArray>", start)]
    return [float(token) for token in body.split()]


def run_entrypoint(pkg: Path, request: Dict[str, Any], run_dir: Path) -> List[Dict[str, Any]]:
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    proc = subprocess.run([sys.executable, str(pkg / "predict.py")], input=json.dumps(request) + "\n",
                          capture_output=True, text=True, encoding="utf-8", cwd=str(run_dir), env=env, timeout=60)
    if proc.returncode != 0:
        raise SystemExit("the entrypoint exited %d: %s" % (proc.returncode, proc.stderr or proc.stdout))
    return [json.loads(line) for line in proc.stdout.splitlines() if line.strip()]


def serve_parity(pkg: Path, weights: Dict[str, Any]) -> Dict[str, float]:
    worst, references = 0.0, 0
    for n, case in enumerate(SERVE_CASES):
        with tempfile.TemporaryDirectory(prefix="reference-field-run-") as tmp:
            run_dir = Path(tmp)
            (frame,) = run_entrypoint(pkg, {"run_id": "parity-%d" % n, "mode": "single", "inputs": case}, run_dir)
            outputs = frame["outputs"]
            own = field(weights["amplitude"], case["power_W"], case["length_m"], case["width_m"])
            peak = max(own)
            field_half, peak_half = weights["field_half_width"] * peak, weights["peak_half_width"] * peak
            expected = {"temperature_rise": own,
                        "temperature_rise_lower": [v - field_half for v in own],
                        "temperature_rise_upper": [v + field_half for v in own]}
            for key, values in expected.items():
                ref = outputs[key]
                data = (run_dir / ref["path"]).read_bytes()
                if hashlib.sha256(data).hexdigest() != ref["sha256"] or len(data) != ref["bytes"]:
                    raise SystemExit("the entrypoint's reference for %s does not describe its file" % key)
                references += 1
                served = read_array(run_dir / ref["path"], key)
                worst = max([worst] + [abs(s - v) / peak for s, v in zip(served, values)])
            for key, value in (("peak_rise", peak), ("peak_rise_lower", peak - peak_half),
                               ("peak_rise_upper", peak + peak_half)):
                worst = max(worst, abs(outputs[key] - value) / peak)
    return {"max_rel_diff": worst, "n_cases": len(SERVE_CASES), "references_verified": references}


def measure_runtime(pkg: Path) -> float:
    label, inputs = EXAMPLES[0]
    times = []
    for n in range(5):
        with tempfile.TemporaryDirectory(prefix="reference-field-time-") as tmp:
            start = time.perf_counter()
            run_entrypoint(pkg, {"run_id": "time-%d" % n, "mode": "single", "inputs": inputs}, Path(tmp))
            times.append(time.perf_counter() - start)
    return statistics.median(times)


def sha256_bytes(path: Path) -> Tuple[str, int]:
    data = path.read_bytes()
    return hashlib.sha256(data).hexdigest(), len(data)


# --------------------------------------------------------------------------- #
# The documents.
# --------------------------------------------------------------------------- #
def check(status: str, method: str, metrics: Dict[str, Any], key: str, comparators: List[Tuple[str, str, str]],
          **extra: Any) -> Dict[str, Any]:
    out: Dict[str, Any] = {"status": status, "method": method, "metrics": metrics,
                           "thresholds": dict(THRESHOLDS[key]),
                           "comparators": [{"metric": m, "op": op, "bar": b} for m, op, b in comparators]}
    out.update(extra)
    return out


def status_of(metrics: Dict[str, Any], thresholds: Dict[str, Any], comparators: List[Tuple[str, str, str]]) -> str:
    ops = {"<=": lambda a, b: a <= b, ">=": lambda a, b: a >= b, "<": lambda a, b: a < b}
    return "PASS" if all(ops[op](metrics[m], thresholds[b]) for m, op, b in comparators) else "FAIL"


def measured(key: str, method: str, metrics: Dict[str, Any], comparators: List[Tuple[str, str, str]],
             **extra: Any) -> Dict[str, Any]:
    return check(status_of(metrics, THRESHOLDS[key], comparators), method, metrics, key, comparators, **extra)


def report_document(m: Dict[str, Any], dataset_sha: str) -> Dict[str, Any]:
    n_nodes = NODES * NODES
    checks: Dict[str, Any] = {}
    checks["A1_accuracy"] = measured(
        "A1_accuracy", "relative L2 error of the predicted field against each interior-test design's corpus field, "
                       "over all %d nodes" % n_nodes,
        m["A1"], [("rel_l2_mean", "<=", "rel_l2_mean_max"), ("rel_l2_worst", "<=", "rel_l2_worst_max")])
    checks["A2_extrapolation"] = measured(
        "A2_extrapolation", "the same on the corner split, every design at or above %r W, which training never saw; "
                            "degradation_ratio is the corner's mean relative L2 error over the interior test's"
                            % m["corner_threshold_W"],
        m["A2"], [("degradation_ratio", "<=", "degradation_max"), ("rel_l2_mean", "<=", "rel_l2_extrap_max")])
    checks["A3_uq_calibration"] = measured(
        "A3_uq_calibration", "split conformal, calibrated on the calibration split: coverage of the field band "
                             "(every node inside it) and of the peak band, on the interior test split",
        m["A3"], [("empirical_coverage", ">=", "coverage_band_lo"), ("empirical_coverage", "<=", "coverage_band_hi"),
                  ("peak_empirical_coverage", ">=", "coverage_band_lo"),
                  ("peak_empirical_coverage", "<=", "coverage_band_hi")])
    checks["A4_baseline_beat"] = measured(
        "A4_baseline_beat", "RMSE over all interior-test nodes against the training mean field, node by node",
        m["A4"], [("ratio_vs_mean", "<=", "beat_mean_max_ratio")])
    checks["A5_reproducibility"] = measured(
        "A5_reproducibility", "refit the amplitude and both half-widths on the same rows and compare them",
        m["A5"], [("max_abs_coefficient_delta", "<=", "tolerance")], determinism_class="bitwise")
    checks["B1_monotonicity"] = measured(
        "B1_monotonicity", "64-point probe lines in power_W at eight plate sizes; a violation is a decrease from one "
                           "probe point to the next",
        m["B1"], [("violation_fraction_peak", "<=", "violation_fraction_max"),
                  ("violation_fraction_nodes", "<=", "violation_fraction_max")],
        declared=[{"feature": "power_W", "target": "peak_rise", "direction": "+"},
                  {"feature": "power_W", "target": "temperature_rise", "direction": "+"}])
    checks["B2_bounds"] = measured(
        "B2_bounds", "every node of the predicted field on a 16-level grid over each input's declared range",
        m["B2"], [("min_predicted_rise_K", ">=", "lower_bound_K"), ("n_violations", "<=", "max_violations")])
    checks["B3_residual"] = measured(
        "B3_residual", "five-point discrete Laplacian of the predicted field at the interior nodes of every "
                       "interior-test design: the residual of k t laplacian(T) + q = 0, relative to q in the L2 norm",
        m["B3"], [("relative_residual_worst", "<=", "relative_residual_max")])
    b4 = measured(
        "B4_conservation", "heat conducted out through the four edges, from second-order one-sided differences of "
                           "the predicted field and Simpson's rule along each edge, against the heating power P; "
                           "steady, so nothing is stored; the worst interior-test design",
        m["B4"], [("relative_imbalance", "<=", "imbalance_max")])
    checks["B4_conservation"] = dict(b4, applicable=True, quantity="heat flow (W)",
                                     control_volume="the whole plate", scope="control_volume")
    checks["B5_invariance"] = measured(
        "B5_invariance", "the predicted field on a %d x %d grid over the same plate against the %d x %d grid, at "
                         "the nodes the two grids share" % (2 * NODES - 1, 2 * NODES - 1, NODES, NODES),
        m["B5"], [("max_abs_diff_K", "<=", "max_abs_diff_allowed_K")])
    checks["B6_integrated_quantities"] = {
        "status": "NOT_APPLICABLE",
        "reason": "no declared output is an integrated quantity: peak_rise is the value at one node, so there is no "
                  "integral of the field to re-derive and compare with a label (the heat the field conducts out is "
                  "B4's balance)"}
    checks["C1_ood_guard"] = measured(
        "C1_ood_guard", "the entrypoint's own input check (predict.read_inputs), a box on the declared ranges, on the "
                        "interior-test inputs and on one far-out design (power_W 500)",
        m["C1"], [("pass_fraction_test_id", ">=", "min_pass_fraction_id"),
                  ("far_out_design_refused", ">=", "far_out_must_refuse")])
    checks["C2_serve_parity"] = measured(
        "C2_serve_parity", "predict.py launched with a stdio_json request in a working directory of the "
                           "caller's, on %d inputs; every node of the field and of its two band files, read back "
                           "from the files it wrote, and the three peak numbers, against this script's own "
                           "implementation; differences relative to the predicted peak" % len(SERVE_CASES),
        m["C2"], [("max_rel_diff", "<=", "max_rel_diff_allowed")])
    checks["C3_provenance_integrity"] = measured(
        "C3_provenance_integrity", "both pinned files hashed again once the measurements were done, and compared "
                                   "with the pins written into the manifest",
        m["C3"], [("hash_mismatches", "<=", "max_hash_mismatches")])
    checks["C4_deployment_readiness"] = measured(
        "C4_deployment_readiness", "the deployment declarations below present, and the median of five single calls "
                                   "of the entrypoint, measured on Linux under CPython %s, against the manifest "
                                   "timeout" % RECORDED_PYTHON,
        m["C4"], [("declarations_present", ">=", "declarations_required"), ("measured_runtime_s", "<=", "timeout_s")],
        declarations=dict(DECLARATIONS))
    blocking = sum(1 for c in checks.values() if c["status"] in ("FAIL", "NOT_RUN"))
    return {
        "spec_version": SPEC_VERSION,
        "produced_by": "examples/build_reference_field_package.py in this repository, from the seeded corpus it "
                       "generates; C4's runtime is the measurement its --measure-runtime mode records",
        "model_id": MODEL_ID,
        "model_version": MODEL_VERSION,
        "dataset_sha256": dataset_sha,
        "lane": "field",
        "splits": {"train": N_TRAIN, "cal": N_CAL, "test_id": N_TEST, "test_extrap": N_CORNER},
        "checks": checks,
        "overall": "FAIL" if blocking else "PASS",
    }


def tidy(values: Dict[str, Any]) -> Dict[str, Any]:
    """Floats rounded to SIGNIFICANT digits for the report; integers as they are."""
    return {k: sig(v) if isinstance(v, float) else v for k, v in values.items()}


def measure(pkg: Path, splits: Dict[str, List[Design]], raw: Dict[str, float],
            weights: Dict[str, Any]) -> Dict[str, Any]:
    amplitude = weights["amplitude"]
    interior, corner = accuracy(splits["test_id"], amplitude), accuracy(splits["test_extrap"], amplitude)
    cover_field, cover_peak = coverage(splits["test_id"], weights)
    refit = fit(splits)
    delta = max(abs(refit[key] - raw[key]) for key in raw)
    m: Dict[str, Any] = {
        "corner_threshold_W": sig(min(d.power for d in splits["test_extrap"])),
        "A1": tidy(interior),
        "A2": tidy(dict(corner, degradation_ratio=corner["rel_l2_mean"] / interior["rel_l2_mean"])),
        "A3": tidy({"nominal": LEVEL, "empirical_coverage": cover_field, "peak_empirical_coverage": cover_peak,
                    "n": len(splits["test_id"]), "half_width_field": weights["field_half_width"],
                    "half_width_peak": weights["peak_half_width"]}),
        "A4": tidy(baseline(splits["train"], splits["test_id"], amplitude)),
        "A5": tidy({"max_abs_coefficient_delta": delta, "coefficients_compared": len(raw),
                    "bitwise_identical": int(delta == 0.0)}),
        "B1": tidy(monotonicity(amplitude)),
        "B2": tidy(bounds(amplitude)),
        "B3": tidy(residual(splits["test_id"], amplitude)),
        "B4": tidy(conservation(splits["test_id"], amplitude)),
        "B5": tidy(invariance(splits["test_id"], amplitude)),
        "C1": tidy(ood_guard(pkg, splits["test_id"], weights)),
        "C2": tidy(serve_parity(pkg, weights)),
        "C4": {"declarations_present": sum(1 for v in DECLARATIONS.values() if v.strip()),
               "measured_runtime_s": RECORDED_RUNTIME_S},
    }
    return m


MANIFEST = '''\
# Contract 1.1 -- the reference field package's manifest.
#
# A CONTRACT fixture, not a model of any real plate: a closed-form expression
# with one amplitude fitted to a synthetic corpus. Its entrypoint runs and every
# check in its report was measured, but nothing here is a validated surrogate.
#
# It is a worked instance of a type: field output under docs/spec/CONTRACT-v1.md:
# the output's field block, a band carried by *_artifact references, a scalar in
# the frame, and a licence block. examples/build_reference_field_package.py wrote
# this file and computed every number and digest in it. To check the package and
# run its entrypoint on the examples below:
#
#     python -m opencontractml.verify check --smoke examples/reference-field-package

spec_version: "{spec_version}"

id: {model_id}
name: "Contract Reference -- Plate Temperature-Rise Field"
version: "{model_version}"

owner:
  team: "open-contract-ml maintainers"
  contact: "open-contract-ml@example.invalid"

domain: heat_conduction
# The plate's size is its geometry, stated as two lengths. The modality
# enumeration has no value for numeric inputs with a field output, and this is
# the nearest one.
modality: geometry_in_field_out
analysis_type: "steady conduction"
tags: [reference, contract-v1, contract-fixture, field]

purpose: "Reference instance of a Contract 1.1 field package: it predicts the temperature rise over a heated plate as a field, so that checkers and consumers can try the field block, the artifact references and the stdio_json frame on a package that really runs."

when_to_use: |
  Validating how a consumer handles a field output -- the field block, the
  artifact references a run answers with, the payload files themselves --
  against a package that is known to be conformant.

when_not_to_use: |
  Do NOT use for engineering decisions. The expression has one coefficient,
  fitted to a synthetic corpus drawn from the same expression; it carries no
  physical validation.

inputs:
  - name: power_W
    type: float
    units: W
    canonical_units: W
    range: [{power_lo}, {power_hi}]
    required: true
    default: 20.0
    description: "Heating power delivered into the plate."
  - name: length_m
    type: float
    units: m
    canonical_units: m
    range: [{length_lo}, {length_hi}]
    required: true
    default: 0.1
    description: "Plate length, along x."
  - name: width_m
    type: float
    units: m
    canonical_units: m
    range: [{width_lo}, {width_hi}]
    required: true
    default: 0.1
    description: "Plate width, along y."

outputs:
  - name: temperature_rise
    type: field
    units: K
    viewer: field_contour
    description: "Steady temperature rise above the edge temperature, at every node of the plate."
    field:
      kind: scalar
      units: K
      support: node
      media_type: application/vnd.vtk.vtp+xml
      shape: [{nodes}, {nodes}]
      coordinate_ref: "the {nodes} x {nodes} nodes of a uniform grid over the plate, at x = i * length_m / {steps} and y = j * width_m / {steps}; the shape and the payload both index j, along y, first and i, along x, second"
  - name: peak_rise
    type: float
    units: K
    viewer: scalar_with_uq
    description: "The largest value of the predicted field, which this model always places at the centre node."

primary_inputs: [power_W, length_m, width_m]
primary_outputs: [temperature_rise, peak_rise]

uncertainty:
  form: predictive_interval
  per_output:
    temperature_rise:
      lower_artifact: temperature_rise_lower
      upper_artifact: temperature_rise_upper
      level: {level}
      method: "split conformal on each design's largest absolute nodal residual, as a fraction of its predicted peak; one half-width applied at every node"
    peak_rise:
      lower_field: peak_rise_lower
      upper_field: peak_rise_upper
      level: {level}
      method: "split conformal on the absolute residual at the centre node, as a fraction of the predicted peak"
  calibration:
    holdout_size: {n_cal}
    empirical_coverage: {coverage}
    method: "split conformal, on a calibration split disjoint from training and test; coverage of the field band measured on the interior test split"

invocation:
  executable: ./predict.py
  protocol: stdio_json
  timeout_s: {timeout}
  expected_runtime_s: {runtime}
  batch_supported: true

lineage:
  training_data_version: "{corpus_version}"
  training_date: "{build_date}"
  metrics:
    rel_l2_mean: {rel_l2_mean}
    rmse_K: {rmse}
    n_test: {n_test}
  retrain_cadence: "not scheduled (contract fixture)"

# --- the Contract's additions to the package-v1 manifest ---------------------- #

provenance:
  artifacts:
    - path: ./predict.py
      role: entrypoint
      sha256: {predict_sha}
      bytes: {predict_bytes}
    - path: ./model_weights.json
      role: weights
      sha256: {weights_sha}
      bytes: {weights_bytes}
  dataset:
    sha256: {dataset_sha}
    n_samples: {n_designs}
    generator_version: "{corpus_version}"
    solver_version: "none (synthetic closed-form corpus)"
  code:
    repo: "{repo}"
    commit: "{commit}"
    version: "contract-reference-field-{model_version}"
  environment:
    python: "{python}"
    # predict.py and its builder import nothing outside the standard library
    packages: {{}}

validation:
  report: ./validation_report.json
  overall: {overall}

model_card: ./model_card.md

# --- the licences, contract 1.1 --------------------------------------------- #
# The entrypoint and the weights are files of this repository, which is
# Apache-2.0. The corpus is not shipped with the package, so no licence is
# asserted for the data.
licence:
  model:
    spdx: Apache-2.0
    url: "http://www.apache.org/licenses/LICENSE-2.0"
  weights:
    spdx: Apache-2.0
    url: "http://www.apache.org/licenses/LICENSE-2.0"
  training_data:
    spdx: NOASSERTION
    note: "the synthetic corpus {corpus_version} is not shipped with this package; examples/build_reference_field_package.py in this repository regenerates it from its seed, the package pins it by sha256, and no licence is asserted for the data"

examples:
{examples}'''


CARD = '''\
---
model_id: {model_id}
version: {model_version}
spec_version: "{spec_version}"
---

# Contract Reference -- Plate Temperature-Rise Field

> The worked field package for Contract 1.1. Its eleven H2 sections are the
> required set (spec section 4.2). examples/build_reference_field_package.py
> computed every number below, and each appears identically in
> `validation_report.json`.

## TL;DR

Predicts the steady temperature rise over a thin rectangular plate, at each node
of a {nodes} x {nodes} grid, from the heating power and the plate's length and
width, together with the peak rise at the plate's centre. The field and the two
edges of its {level_pct} percent split-conformal band come back as VTK XML PolyData
files the entrypoint writes; the peak and its band come back as numbers in the
frame. The package exists so that Contract 1.1's field declaration, its artifact
reference and its `stdio_json` frame have a real package to be checked against.
It is a closed-form expression with one fitted coefficient, fitted to a
synthetic corpus drawn from that same expression, and it is not an engineering
surrogate.

## Intended use

- Exercising a consumer's handling of field outputs -- reading `outputs[].field`,
  dispatching the entrypoint, verifying every artifact reference against the file
  it names, drawing the payload -- against a package known to be conformant.
- Showing, in one package, a field output's declaration, a band carried by
  `*_artifact` references, a scalar carried in the frame, a licence block and a
  report measured on a field model.
- Comparing against when a field model is brought onto the Contract: what that
  model must declare in addition is the difference between its package and this one.

## Out of scope

- Any engineering or design decision. The corpus is synthetic, and nothing ties
  the expression to a measured plate.
- Inputs beyond the declared ranges: the entrypoint answers them with an
  `OUT_OF_RANGE` error frame instead of a prediction.
- Any other plate, edge condition or heating pattern. The model knows one plate --
  conductivity {k} W/(m K), thickness {t} m, every edge held at the reference
  temperature -- heated by the distribution Architecture states.
- Reading the band as a map of nodal uncertainty. One half-width, a fixed fraction
  of the predicted peak, is applied at every node.

## Training data

- **Source:** a synthetic corpus that the builder generates from the expression
  below with amplitude {true_amplitude}, seeded (`random.Random({seed_corpus})`). Every
  node of every design carries independent noise whose standard deviation is
  {noise_pct} percent of that design's peak rise (a sum of twelve uniform draws,
  less six, scaled).
- **Size:** {n_designs} designs of {n_nodes} nodes each; {n_train} train /
  {n_cal} calibration / {n_test} interior test / {n_corner} corner (extrapolation).
- **Distribution:** `power_W` uniform on [{power_lo}, {power_hi}]; `length_m` and
  `width_m` uniform on [{length_lo}, {length_hi}], each drawn independently.
- **Split policy:** the corner split holds the {n_corner} designs of highest power,
  every design at or above {corner_power} W. The rest are permuted
  (`random.Random({seed_split})`) into the train, calibration and interior-test
  splits, so the four splits share no design.
- **Known bias:** the corpus follows the very expression the model fits, so the
  accuracy checks mostly measure the noise. The card says so here rather than
  leaving it to be discovered, and it is why C4 claims no validation anchor.

## Architecture

The predicted rise at node (i, j), where x = i L / {steps} and y = j W / {steps}, is

`c * P * L * W / (k * t * (L^2 + W^2)) * (x/L) * (1 - x/L) * (y/W) * (1 - y/W)`

with P the heating power (`power_W`), L and W the plate's length and width, k and
t its conductivity and thickness, and c the one fitted coefficient. With c = 3 the
expression is the exact steady solution of k t (d2T/dx2 + d2T/dy2) + q = 0 with
zero rise on every edge, for the heating density
q(x, y) = 6 P (x (L - x) + y (W - y)) / (L W (L^2 + W^2)), which integrates to P
over the plate. The peak sits at the centre node and equals
c P L W / (16 k t (L^2 + W^2)). The fitted c is {amplitude}. `model_weights.json`
holds it with the plate's two properties, the node count, the two band
half-widths and the declared input ranges, and that is the whole model.

## Training configuration

| Element | Value |
|---|---|
| Estimator | least squares for the one coefficient, in closed form: the sum of basis times target over the sum of basis squared, on every node of the training designs |
| Iterations | none |
| Regularisation | none |
| Seeds | corpus `random.Random({seed_corpus})`; split permutation `random.Random({seed_split})` |
| Rounding | the coefficient and both half-widths to {significant} significant digits, as written to `model_weights.json` |
| Measured against | the rounded values the entrypoint loads, not the unrounded fit |
| Calibration | split conformal at level {level} on the {n_cal}-design calibration split |
| Arithmetic | addition, subtraction, multiplication, division and square roots only, so no number depends on the platform's maths library |

## Performance

Measured against each design's corpus field, over all {n_nodes} nodes, with the
shipped coefficient.

| Slice | n | Mean relative L2 | Worst relative L2 | RMSE (K) |
|---|---|---|---|---|
| Interior test | {n_test} | {a1_mean} | {a1_worst} | {a1_rmse} |
| Corner (extrapolation) | {n_corner} | {a2_mean} | {a2_worst} | {a2_rmse} |

The corner's mean relative L2 error is {degradation} times the interior
test's, against a cap of {degradation_max} (A2). The model's RMSE is
{ratio_vs_mean} times that of the training mean field, taken node by node,
against a cap of {beat_max} (A4). The physics checks, on the same predictions:
the relative residual of the conduction equation is at most {b3_worst} (B3), the
worst relative heat imbalance over the whole plate is {b4} (B4), and on a
twice-finer grid the shared nodes differ by at most {b5} K (B5).

## Uncertainty quantification

Split-conformal predictive intervals at a nominal level of {level_pct} percent,
fitted on the {n_cal}-design calibration split and never on training or test
designs. For the field, each design's score is its largest absolute nodal
residual divided by its predicted peak, and the {rank}th smallest of the {n_cal}
calibration scores is the half-width: {half_field} of the predicted peak, applied
at every node, so that the band is meant to hold every node of a design at once. For the peak, the score is the
absolute residual at the centre node over the predicted peak, and the half-width
is {half_peak} of it.

On the {n_test}-design interior test split the field band holds every node of
{cover_field_pct} percent of designs (empirical coverage {cover_field}) and the
peak band holds the centre value of {cover_peak_pct} percent ({cover_peak}),
both against the accepted band [{band_lo}, {band_hi}]. Coverage on the corner split
is neither measured nor claimed.

## Known failure modes

- **Flattering corpus.** The corpus and the model share their functional form.
  Real temperature fields will not follow it, and the accuracy above says nothing
  about a real plate.
- **The physics checks pass by construction.** With any coefficient the field is
  zero on the edges and is exactly a product of two parabolas, so the discrete
  Laplacian and the edge fluxes are exact, and B3 and B4 measure only how far the
  fitted c lies from 3. B5 passes because each node's value comes from the
  expression alone, so a finer grid adds nodes and never moves the ones already there.
- **The band edges are not physical.** The lower edge goes below zero near the
  plate's edges, where the predicted rise is zero, because one half-width is used
  at every node.
- **Inputs outside the ranges are refused, not extrapolated.** A consumer that
  ignores the error frame will find no outputs.
- **The scalar band is calibrated on one node.** It covers the centre value
  only, not the largest value of a noisy field.

## Provenance

| Item | Value |
|---|---|
| Entrypoint | `./predict.py` sha256 `{predict_sha}` ({predict_bytes} bytes) |
| Weights | `./model_weights.json` sha256 `{weights_sha}` ({weights_bytes} bytes) |
| Dataset | sha256 `{dataset_sha}` ({n_designs} designs, not shipped) |
| Code | `{repo}` at commit `{commit}`, the tree the builder ran on |
| Environment | Python {python}, standard library only |
| Licences | the model and the weights: Apache-2.0, the licence of this repository; the training data: none asserted, because the corpus is not shipped |

Every `python -m opencontractml.verify check` re-hashes both artifacts (rule
M013), as the builder did when it measured C3, so an entrypoint or weights file
edited after the build fails the check. Neither this card nor the validation
report is hashed, since each was written after the artifacts it describes; the
package's id, version and dataset digest tie them to it instead (rules C002, V002,
V003).
Each run's payloads are pinned too, but by the run: every reference carries the
sha256 and length of the file the entrypoint wrote (section 12 of the Contract).

## Version history

- **{model_version}** ({build_date}) -- first issue, built as the worked field
  instance of Contract 1.1. The coefficient, the half-widths, every metric and
  every digest come from the builder; none was typed by hand.

## Disclosure

| Element | Status |
|---|---|
| The package's shape: the field block, the artifact references, the frame, the sections, the ladder keys | **Normative** -- this package is a reference instance |
| The expression, the corpus and every metric | **Real but illustrative** -- measured and reproducible, and of no engineering significance |
| Threshold values | **Chosen for the fixture** -- fixed before the first measurement; the Contract sets no physics bars |

## References

- `docs/spec/CONTRACT-v1.md` -- the specification this package instantiates.
- `examples/build_reference_field_package.py` -- the builder that wrote it.
- `src/opencontractml/verify.py` -- the checker that grades it.
'''


def pct(x: float) -> str:
    return "%.1f" % (100.0 * x)


def manifest_text(m: Dict[str, Any], weights: Dict[str, Any], pins: Dict[str, Tuple[str, int]], dataset_sha: str,
                  commit: str, overall: str) -> str:
    example_lines = []
    for label, inputs in EXAMPLES:
        example_lines.append('  - label: "%s"' % label)
        example_lines.append("    inputs:")
        example_lines.extend("      %s: %r" % (name, value) for name, value in inputs.items())
    return MANIFEST.format(
        spec_version=SPEC_VERSION, model_id=MODEL_ID, model_version=MODEL_VERSION,
        power_lo=RANGES["power_W"][0], power_hi=RANGES["power_W"][1],
        length_lo=RANGES["length_m"][0], length_hi=RANGES["length_m"][1],
        width_lo=RANGES["width_m"][0], width_hi=RANGES["width_m"][1],
        nodes=NODES, steps=NODES - 1, level=LEVEL, n_cal=N_CAL, coverage=m["A3"]["empirical_coverage"],
        timeout=THRESHOLDS["C4_deployment_readiness"]["timeout_s"], runtime=RECORDED_RUNTIME_S,
        corpus_version=CORPUS_VERSION, build_date=BUILD_DATE, rel_l2_mean=m["A1"]["rel_l2_mean"],
        rmse=m["A1"]["rmse_K"], n_test=N_TEST,
        predict_sha=pins["predict.py"][0], predict_bytes=pins["predict.py"][1],
        weights_sha=pins["model_weights.json"][0], weights_bytes=pins["model_weights.json"][1],
        dataset_sha=dataset_sha, n_designs=N_DESIGNS, repo=REPO_URL, commit=commit, python=RECORDED_PYTHON,
        overall=overall, examples="\n".join(example_lines) + "\n")


def card_text(m: Dict[str, Any], weights: Dict[str, Any], pins: Dict[str, Tuple[str, int]], dataset_sha: str,
              commit: str) -> str:
    a3 = m["A3"]
    return CARD.format(
        model_id=MODEL_ID, model_version=MODEL_VERSION, spec_version=SPEC_VERSION, nodes=NODES, steps=NODES - 1,
        n_nodes=NODES * NODES, level=LEVEL, level_pct="%d" % round(100 * LEVEL), k=CONDUCTIVITY_W_MK, t=THICKNESS_M,
        true_amplitude="%g" % TRUE_AMPLITUDE, seed_corpus=SEED_CORPUS, seed_split=SEED_SPLIT,
        noise_pct="%g" % (100 * NOISE_FRACTION_OF_PEAK), n_designs=N_DESIGNS, n_train=N_TRAIN, n_cal=N_CAL,
        n_test=N_TEST, n_corner=N_CORNER, power_lo=RANGES["power_W"][0], power_hi=RANGES["power_W"][1],
        length_lo=RANGES["length_m"][0], length_hi=RANGES["length_m"][1], corner_power=m["corner_threshold_W"],
        amplitude=weights["amplitude"], significant=SIGNIFICANT,
        a1_mean=m["A1"]["rel_l2_mean"], a1_worst=m["A1"]["rel_l2_worst"], a1_rmse=m["A1"]["rmse_K"],
        a2_mean=m["A2"]["rel_l2_mean"], a2_worst=m["A2"]["rel_l2_worst"], a2_rmse=m["A2"]["rmse_K"],
        degradation=m["A2"]["degradation_ratio"], degradation_max=THRESHOLDS["A2_extrapolation"]["degradation_max"],
        ratio_vs_mean=m["A4"]["ratio_vs_mean"], beat_max=THRESHOLDS["A4_baseline_beat"]["beat_mean_max_ratio"],
        b3_worst=m["B3"]["relative_residual_worst"], b4=m["B4"]["relative_imbalance"], b5=m["B5"]["max_abs_diff_K"],
        rank=conformal_rank(N_CAL), half_field=weights["field_half_width"], half_peak=weights["peak_half_width"],
        cover_field=a3["empirical_coverage"], cover_field_pct=pct(a3["empirical_coverage"]),
        cover_peak=a3["peak_empirical_coverage"], cover_peak_pct=pct(a3["peak_empirical_coverage"]),
        band_lo=THRESHOLDS["A3_uq_calibration"]["coverage_band_lo"],
        band_hi=THRESHOLDS["A3_uq_calibration"]["coverage_band_hi"],
        predict_sha=pins["predict.py"][0], predict_bytes=pins["predict.py"][1],
        weights_sha=pins["model_weights.json"][0], weights_bytes=pins["model_weights.json"][1],
        dataset_sha=dataset_sha, repo=REPO_URL, commit=commit, python=RECORDED_PYTHON, build_date=BUILD_DATE)


def build(commit: str, package: Path = PACKAGE) -> Dict[str, bytes]:
    """Every generated file of the package, as bytes, built in a temporary copy of the package."""
    designs = make_corpus()
    dataset_sha = corpus_sha256(designs)
    splits = split(designs)
    raw = fit(splits)
    weights = weights_document(raw)
    files = {"model_weights.json": (json.dumps(weights, indent=2) + "\n").encode("utf-8")}
    with tempfile.TemporaryDirectory(prefix="reference-field-build-") as tmp:
        pkg = Path(tmp) / "reference-field-package"
        pkg.mkdir()
        shutil.copyfile(package / "predict.py", pkg / "predict.py")
        (pkg / "model_weights.json").write_bytes(files["model_weights.json"])
        pins = {name: sha256_bytes(pkg / name) for name in ("predict.py", "model_weights.json")}
        m = measure(pkg, splits, raw, weights)
        m["C3"] = {"artifacts_verified": len(pins),
                   "hash_mismatches": sum(1 for name, pin in pins.items() if sha256_bytes(pkg / name) != pin)}
    report = report_document(m, dataset_sha)
    files["validation_report.json"] = (json.dumps(report, indent=2) + "\n").encode("utf-8")
    files["manifest.yaml"] = manifest_text(m, weights, pins, dataset_sha, commit, report["overall"]).encode("utf-8")
    files["model_card.md"] = card_text(m, weights, pins, dataset_sha, commit).encode("utf-8")
    return files


def recorded_commit(package: Path) -> str:
    text = (package / "manifest.yaml").read_text(encoding="utf-8")
    found = re.search(r'^    commit: "([0-9a-f]{7,40})"$', text, re.M)
    if not found:
        raise SystemExit("manifest.yaml records no provenance.code.commit to rebuild with")
    return found.group(1)


def main(argv: Optional[Sequence[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--commit", help="write the package, recording this commit as the tree it was built from")
    mode.add_argument("--check", action="store_true", help="rebuild and compare with the files on disk")
    mode.add_argument("--measure-runtime", action="store_true", help="print the median of five single calls")
    parser.add_argument("--package", type=Path, default=PACKAGE, help="the package directory (default: %(default)s)")
    args = parser.parse_args(argv)
    package = args.package.resolve()
    if args.measure_runtime:
        print("median of five single calls: %.4f s (Python %s)" % (measure_runtime(package),
                                                                   ".".join(map(str, sys.version_info[:3]))))
        return 0
    if args.commit is not None and not re.match(r"^[0-9a-f]{7,40}$", args.commit):
        parser.error("--commit takes a hex commit id, got %r" % args.commit)
    files = build(recorded_commit(package) if args.check else args.commit, package)
    if args.check:
        differ = [name for name in GENERATED
                  if not (package / name).is_file() or (package / name).read_bytes() != files[name]]
        for name in differ:
            print("differs from a rebuild: %s" % (package / name))
        print("%d of %d generated files reproduce" % (len(GENERATED) - len(differ), len(GENERATED)))
        return 1 if differ else 0
    for name in GENERATED:
        (package / name).write_bytes(files[name])
    report = json.loads(files["validation_report.json"])
    print("wrote %d files; overall %s" % (len(GENERATED), report["overall"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
