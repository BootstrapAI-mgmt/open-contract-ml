"""V1 / V2 / V3 -- model validation, physics validity, deployment readiness.

Validates the artifacts produced by train_b1.py:

  V1.1 held-out accuracy      R2 / MAE / RMSE on the random test split vs r2_min, mae_max
  V1.2 extrapolation honesty  the same on the corner split; degradation ratio vs degradation_max
  V1.3 UQ calibration         empirical coverage of the nominal-90 % conformal interval in the band
  V1.4 baseline beat          RMSE <= beat_mean x RMSE(mean) and, when the champion is not the
                              linear model, RMSE <= beat_linear x RMSE(linear)
  V1.5 reproducibility        re-train with the same seeds -> identical V1.1 metrics (rel tol)
  V2.1 monotonicity           declared (feature, target, direction) pairs on probe lines
  V2.2 bounds                 declared bounds on a probe set covering the hull expanded by 10 %
  V2.3 / V2.4                 conservation / symmetry: declared applicable or not, never skipped silently
  V3                          rung-4 anchor, inference target, Stage-8 status, use statement

Usage:
  python -m opencontractml.gate --corpus <dir>/training_corpus.parquet --gate-report out/corpus_gate_report.json
                                --rules <rules.json> --model out/model --card out/model_card.json

Exit code 0 when every model passes; 1 otherwise. The model card is written either way.
"""

from __future__ import annotations

import argparse
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

os.environ.setdefault("OMP_NUM_THREADS", "1")

import numpy as np
import pandas as pd

from .cc_common import load_corpus, read_json, utc_now, write_json
# every bundle read goes through safe_artifact -- a bundle is an untrusted input
# (it arrives via --model) and pickle.load on one is a code-execution primitive
from .safe_artifact import load_bundle
from .train_b1 import design_matrix, predict_entry, train


def _metrics(y: np.ndarray, p: np.ndarray) -> Dict[str, float]:
    if len(y) == 0:
        return {"n": 0, "rmse": float("nan"), "mae": float("nan"), "r2": float("nan")}
    err = p - y
    ss_res = float(np.sum(err ** 2))
    ss_tot = float(np.sum((y - y.mean()) ** 2))
    r2 = 1.0 - ss_res / ss_tot if ss_tot > 0 else float("nan")
    return {"n": int(len(y)), "rmse": float(np.sqrt(np.mean(err ** 2))), "mae": float(np.mean(np.abs(err))), "r2": r2}


def _rows_for(df_adm: pd.DataFrame, component: str, target: str) -> pd.DataFrame:
    dc = df_adm[df_adm["component_name"] == component].reset_index(drop=True)
    return dc[dc[target].notna()].reset_index(drop=True)


def v1_checks(key: str, entry: Dict[str, Any], dt: pd.DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    v1 = rules.get("v1", {})
    model = entry["model"]
    t = entry["target"]
    X, _cols = design_matrix(dt, entry["features"], entry["feature_columns"])
    y = dt[t].to_numpy(dtype=float)
    sp = entry["splits"]
    rt, corner = np.array(sp["random_test"], dtype=int), np.array(sp["corner"], dtype=int)
    pr = predict_entry(entry, X[rt])
    m_rand = _metrics(y[rt], pr["champion"])
    checks: List[Dict[str, Any]] = []
    # V1.1
    r2_min = float(v1.get("r2_min", 0.90))
    mae_max = (v1.get("mae_max") or {}).get(t)
    ok11 = (not np.isnan(m_rand["r2"])) and m_rand["r2"] >= r2_min and (mae_max is None or m_rand["mae"] <= float(mae_max))
    checks.append({"check": "V1.1 held-out accuracy", "passed": ok11, "detail": {**m_rand, "r2_min": r2_min, "mae_max": mae_max}})
    # V1.2
    y_range = float(np.max(y) - np.min(y)) if len(y) else 1.0
    if len(corner):
        pc = predict_entry(entry, X[corner])
        m_corner = _metrics(y[corner], pc["champion"])
        ratio = m_corner["rmse"] / m_rand["rmse"] if m_rand["rmse"] > 0 else float("inf")
        deg_max = float(v1.get("degradation_max", 3.0))
        # an absolute floor keeps the ratio from punishing excellent models: a corner error
        # below mae_max (or 1 % of the target range) is honest extrapolation whatever the ratio
        abs_floor = float(mae_max) if mae_max is not None else float(v1.get("degradation_abs_floor_fraction", 0.01)) * y_range
        ok12 = ratio <= deg_max or m_corner["rmse"] <= abs_floor
        checks.append({"check": "V1.2 extrapolation honesty (corner)", "passed": ok12,
                       "detail": {**m_corner, "degradation_ratio": ratio, "degradation_max": deg_max,
                                  "abs_floor": abs_floor, "passed_by": ("ratio" if ratio <= deg_max else ("abs_floor" if ok12 else None)),
                                  "corner_axis": sp["corner_axis"], "corner_threshold": sp["corner_threshold"],
                                  "corner_coverage": float(np.mean((y[corner] >= pc["pi_low"]) & (y[corner] <= pc["pi_high"])))}})
    else:
        checks.append({"check": "V1.2 extrapolation honesty (corner)", "passed": False,
                       "detail": {"error": "no corner rows -- declare a corner axis in the rules split spec"}})
    # V1.3
    cov = float(np.mean((y[rt] >= pr["pi_low"]) & (y[rt] <= pr["pi_high"])))
    lo, hi = v1.get("coverage_band", [0.85, 0.95])
    nominal = float(model["conformal_nominal"])
    # sample-size-aware band: with n test rows the empirical coverage of a calibrated interval
    # fluctuates by ~2 sqrt(p (1-p) / n); the declared band governs once n is large enough
    n_rt = int(len(rt))
    sigma2 = 2.0 * np.sqrt(nominal * (1.0 - nominal) / n_rt) if n_rt else 0.0
    eff_lo, eff_hi = min(lo, nominal - sigma2), max(hi, nominal + sigma2)
    # over-coverage is acceptable only when the interval is narrow (a perfect model covers 100 %
    # with a hair-width interval); a wide interval that over-covers is a calibration failure
    width_floor = float(v1.get("pi_width_floor_fraction", 0.01)) * y_range
    half_width = float(np.mean(pr["pi_high"] - pr["pi_low"]) / 2.0)   # original units (log transforms make it asymmetric)
    narrow = half_width <= width_floor
    ok13 = (eff_lo <= cov <= eff_hi) or (cov > eff_hi and narrow)
    checks.append({"check": "V1.3 UQ calibration (conformal 90 % PI coverage on random test)", "passed": ok13,
                   "detail": {"coverage": cov, "band_declared": [lo, hi], "band_effective_n": [eff_lo, eff_hi], "n_test": n_rt,
                              "nominal": nominal, "half_width": half_width, "width_floor": width_floor,
                              "narrow_interval": narrow, "mean_ensemble_std": float(np.mean(pr["ensemble_std"]))}})
    # V1.4
    m_mean = _metrics(y[rt], pr["mean"])
    m_lin = _metrics(y[rt], pr["linear"])
    beat_mean, beat_lin = float(v1.get("beat_mean", 0.5)), float(v1.get("beat_linear", 0.8))
    ok_mean = m_rand["rmse"] <= beat_mean * m_mean["rmse"]
    if model["champion"] == "linear":
        ok_lin, lin_note = True, "not applicable: the champion IS the linear model"
    else:
        ok_lin, lin_note = m_rand["rmse"] <= beat_lin * m_lin["rmse"], None
    checks.append({"check": "V1.4 baseline beat", "passed": ok_mean and ok_lin,
                   "detail": {"champion": model["champion"], "rmse_champion": m_rand["rmse"], "rmse_mean_predictor": m_mean["rmse"],
                              "rmse_linear": m_lin["rmse"], "beat_mean": beat_mean, "beat_linear": beat_lin,
                              "linear_clause": lin_note or ("pass" if ok_lin else "fail"),
                              "calibration_rmse_all_candidates": model["calibration_rmse"]}})
    return {"key": key, "checks": checks, "random_test_metrics": m_rand}


def v1_5_reproducibility(corpus_path: Path, gate_report: Dict[str, Any], rules: Dict[str, Any], meta: Dict[str, Any],
                         bundle: Dict[str, Any], df_adm: pd.DataFrame) -> Dict[str, Any]:
    tol = float(rules.get("v1", {}).get("reproducibility_rel_tol", 1e-6))
    tmp = Path(tempfile.mkdtemp(prefix="v15_"))
    try:
        train(corpus_path, gate_report, rules, tmp, meta.get("components"), meta.get("targets"))
        again = load_bundle(tmp / "model_bundle.pkl")
        worst = 0.0
        compared = 0
        for key, entry in bundle.items():
            if key not in again:
                continue
            dt = _rows_for(df_adm, entry["component"], entry["target"])
            X, _ = design_matrix(dt, entry["features"], entry["feature_columns"])
            rt = np.array(entry["splits"]["random_test"], dtype=int)
            y = dt[entry["target"]].to_numpy(dtype=float)
            a = _metrics(y[rt], predict_entry(entry, X[rt])["champion"])["rmse"]
            b = _metrics(y[rt], predict_entry(again[key], X[rt])["champion"])["rmse"]
            worst = max(worst, abs(a - b) / (abs(a) if a else 1.0))
            compared += 1
        return {"check": "V1.5 reproducibility (re-train with the same seeds)", "passed": worst <= tol and compared > 0,
                "detail": {"max_rel_metric_diff": worst, "tol": tol, "models_compared": compared}}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def v2_checks(key: str, entry: Dict[str, Any], dt: pd.DataFrame, rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    v2 = rules.get("v2", {})
    model, t, comp = entry["model"], entry["target"], entry["component"]
    feats = entry["features"]
    cols = entry["feature_columns"]
    num_feats = [f for f in feats if f in cols]           # numeric features map 1:1 to design columns
    Xall, _ = design_matrix(dt, feats, cols)
    y = dt[t].to_numpy(dtype=float)
    y_range = float(np.max(y) - np.min(y)) if len(y) else 1.0
    lo = Xall.min(axis=0)
    hi = Xall.max(axis=0)
    rng = np.random.RandomState(0)
    checks: List[Dict[str, Any]] = []
    # V2.1 monotonicity
    n_lines = int(v2.get("n_lines", 50))
    n_pts = int(v2.get("n_points_per_line", 25))
    step_tol = float(v2.get("step_tol_fraction", 0.001)) * y_range
    mono_eps = float(v2.get("mono_eps", 0.02))
    for rule in v2.get("monotone", []):
        if rule.get("target") != t or rule["feature"] not in num_feats:
            continue
        if rule.get("components") and comp not in rule["components"]:
            continue
        j = cols.index(rule["feature"])
        sign = 1.0 if rule.get("direction", "+") == "+" else -1.0
        violations = 0
        steps = 0
        for _ in range(n_lines):
            base = lo + rng.rand(len(cols)) * (hi - lo)
            line = np.tile(base, (n_pts, 1))
            line[:, j] = np.linspace(lo[j], hi[j], n_pts)
            pred = predict_entry(entry, line)["champion"]
            d = np.diff(pred) * sign
            violations += int(np.sum(d < -step_tol))
            steps += len(d)
        frac = violations / steps if steps else 0.0
        checks.append({"check": "V2.1 monotonicity %s -> %s (%s)" % (rule["feature"], t, rule.get("direction", "+")),
                       "passed": frac <= mono_eps, "detail": {"violation_fraction": frac, "mono_eps": mono_eps,
                                                              "n_lines": n_lines, "n_steps": steps, "step_tol": step_tol}})
    # V2.2 bounds on an expanded-hull probe set
    bp = v2.get("bounds_probe", {})
    expand = float(bp.get("expand", 0.10))
    n_probe = int(bp.get("n", 500))
    span = hi - lo
    plo, phi = lo - expand * span, hi + expand * span
    probe = plo + rng.rand(n_probe, len(cols)) * (phi - plo)
    pred = predict_entry(entry, probe)["champion"]
    for b in rules.get("bounds", []):
        if b["target"] != t or (b.get("components") and comp not in b["components"]):
            continue
        tol = float(b.get("tol", 0.0))
        viol = 0
        evaluable = True
        for side in ("lower", "upper"):
            spec = b.get(side)
            if spec is None:
                continue
            if isinstance(spec, dict) and "col" in spec:
                if spec["col"] not in cols:
                    evaluable = False
                    continue
                limit = probe[:, cols.index(spec["col"])]
            else:
                limit = np.full(n_probe, float(spec))
            if side == "lower":
                viol += int(np.sum(pred < limit - tol))
            else:
                viol += int(np.sum(pred > limit + tol))
        checks.append({"check": "V2.2 bounds on %s (%s)" % (t, "/".join(k for k in ("lower", "upper") if k in b)),
                       "passed": evaluable and viol == 0,
                       "detail": {"n_probe": n_probe, "n_violations": viol, "expand": expand,
                                  "evaluable": evaluable, "note": None if evaluable else "bound references a non-feature column; not evaluable on the probe set"}})
    return checks


def run_gate(corpus_path: Path, gate_report: Dict[str, Any], rules: Dict[str, Any], model_dir: Path) -> Dict[str, Any]:
    df = load_corpus(corpus_path)
    adm = np.array(gate_report["admissible_index"], dtype=int)
    df_adm = df.iloc[adm].reset_index(drop=True)
    bundle = load_bundle(model_dir / "model_bundle.pkl")
    meta = read_json(model_dir / "model_meta.json")
    per_model: Dict[str, Any] = {}
    all_ok = True
    for key, entry in bundle.items():
        dt = _rows_for(df_adm, entry["component"], entry["target"])
        v1 = v1_checks(key, entry, dt, rules)
        v2 = v2_checks(key, entry, dt, rules)
        checks = v1["checks"] + v2
        ok = all(c["passed"] for c in checks)
        all_ok = all_ok and ok
        per_model[key] = {"passed": ok, "champion": entry["model"]["champion"], "checks": checks,
                          "use_statement": ("extrapolation-tolerant on %s up to the corner threshold" % entry["splits"]["corner_axis"]
                                            if next((c for c in checks if c["check"].startswith("V1.2")), {}).get("passed")
                                            else "interpolation-only (V1.2 corner degradation exceeded or unavailable)")}
    v15 = v1_5_reproducibility(corpus_path, gate_report, rules, meta, bundle, df_adm)
    all_ok = all_ok and v15["passed"]
    v2decl = {"V2.3 conservation": rules.get("v2", {}).get("conservation", "not declared"),
              "V2.4 symmetry": rules.get("v2", {}).get("symmetry", "not declared")}
    declared_ok = all(v not in ("not declared", None, "") for v in v2decl.values())
    all_ok = all_ok and declared_ok
    v3 = rules.get("v3", {})
    v3_fields = {"rung4_anchor": v3.get("rung4_anchor"), "inference_target": v3.get("inference_target"),
                 "stage8_status": v3.get("stage8_status")}
    v3_ok = all(bool(v) for v in v3_fields.values())
    all_ok = all_ok and v3_ok
    card = {
        "gate": "V1/V2/V3 model validation", "passed": all_ok, "timestamp_utc": utc_now(),
        "rules_vertical": rules.get("vertical"), "corpus": meta.get("corpus"), "model_meta": {
            "features": meta.get("features"), "targets": meta.get("targets"), "components": meta.get("components"),
            "versions": meta.get("versions"), "ensemble_seeds": meta.get("ensemble_seeds"), "split_spec": meta.get("split_spec")},
        "models": per_model, "V1.5": v15, "V2_declarations": v2decl,
        "V2_declarations_complete": declared_ok, "V3": {**v3_fields, "fields_present": v3_ok},
        "threshold_provenance": "PROVISIONAL: the defaults in opencontractml.gate apply wherever the rules file sets no threshold",
    }
    return card


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="V1/V2/V3 model validation gate")
    p.add_argument("--corpus", required=True)
    p.add_argument("--gate-report", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--model", required=True)
    p.add_argument("--card", required=True)
    a = p.parse_args(argv)
    card = run_gate(Path(a.corpus), read_json(Path(a.gate_report)), read_json(Path(a.rules)), Path(a.model))
    write_json(Path(a.card), card)
    for key, m in card["models"].items():
        print("%s  [%s]  champion=%s  %s" % (key, "PASS" if m["passed"] else "FAIL", m["champion"], m["use_statement"]))
        for c in m["checks"]:
            d = c["detail"]
            brief = {k: (round(v, 4) if isinstance(v, float) else v) for k, v in d.items()
                     if k in ("r2", "mae", "rmse", "degradation_ratio", "coverage", "violation_fraction", "n_violations",
                              "rmse_mean_predictor", "rmse_linear", "linear_clause", "evaluable")}
            print("    [%s] %s %s" % ("PASS" if c["passed"] else "FAIL", c["check"], brief))
    print("    [%s] %s %s" % ("PASS" if card["V1.5"]["passed"] else "FAIL", card["V1.5"]["check"], card["V1.5"]["detail"]))
    print("    V2 declarations: %s" % card["V2_declarations"])
    print("    V3: %s" % card["V3"])
    print("MODEL GATE %s; card %s" % ("PASS" if card["passed"] else "FAIL", a.card))
    return 0 if card["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
