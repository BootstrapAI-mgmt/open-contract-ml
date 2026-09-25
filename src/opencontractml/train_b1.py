"""M1 -- corpus-native B1 trainer for corpus-consumer-schema corpora (per component, per target).

The M1 training stage:

  M1.1 split      random test split + a CORNER split by parameter region:
                  rows at or above the corner quantile of the declared
                  extrapolation axis are held out entirely; the interior is split
                  into fit / calibration / random-test
  M1.2 models     candidates: a 5-seed gradient-boosted-tree ensemble (scikit-learn
                  HistGradientBoostingRegressor), a quadratic ridge, and an anisotropic
                  RBF Gaussian process; a linear model and a mean predictor as the
                  mandatory baselines; split-conformal calibration for 90 % prediction
                  intervals; champion = lowest calibration RMSE among the candidates
                  and the linear baseline (an honest champion may be the linear model)
  M1.3 artifact   model_bundle.pkl + model_meta.json (corpus sha256, admissible rows,
                  split spec + indices, seeds, features, targets, versions, wall time)
  M1.4 determinism  fixed seeds; OMP_NUM_THREADS=1 so a re-train reproduces metrics

Usage:
  python -m opencontractml.train_b1 --corpus <dir>/training_corpus.parquet
      --gate-report out/corpus_gate_report.json --rules <rules.json> --out out/model [--component heat_shield]

The gate report is REQUIRED: the trainer consumes the G1 admissible-row index,
so nothing can be trained on a corpus the gate did not admit.
"""

from __future__ import annotations

import argparse
import os
import pickle
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

os.environ.setdefault("OMP_NUM_THREADS", "1")

import warnings

import numpy as np
import pandas as pd

from .cc_common import corpus_fingerprint, load_corpus, read_json, swept_columns, utc_now, write_json

ENSEMBLE_SEEDS = (0, 1, 2, 3, 4)


def _versions() -> Dict[str, str]:
    import sklearn  # type: ignore
    return {"python": sys.version.split()[0], "numpy": np.__version__, "pandas": pd.__version__,
            "sklearn": sklearn.__version__}


def feature_columns(df: pd.DataFrame, rules: Dict[str, Any]) -> List[str]:
    """Swept dotted columns minus the rules' exclusions; numeric only (categoricals one-hot later)."""
    swept = swept_columns(df)
    exclude = set(rules.get("feature_policy", {}).get("exclude", []))
    return [c for c in swept if c not in exclude]


def design_matrix(df: pd.DataFrame, features: List[str], dummy_columns: Optional[List[str]] = None
                  ) -> Tuple[np.ndarray, List[str]]:
    X = pd.get_dummies(df[features], dtype=float)
    if dummy_columns is not None:
        X = X.reindex(columns=dummy_columns, fill_value=0.0)
    return X.to_numpy(dtype=float), list(X.columns)


def _transform_spec(rules: Dict[str, Any], target: str, columns: List[str]) -> Dict[str, Any]:
    """Which columns / target are trained in log space (rules: feature_transform, target_transform)."""
    ft = rules.get("feature_transform", {}) or {}
    tt = (rules.get("target_transform", {}) or {}).get(target)
    return {"features": {c: ft[c] for c in columns if c in ft and ft[c] == "log"}, "target": tt if tt == "log" else None}


def apply_feature_transform(X: np.ndarray, cols: List[str], spec: Dict[str, Any]) -> np.ndarray:
    X = np.array(X, dtype=float, copy=True)
    for c, kind in spec.get("features", {}).items():
        if kind == "log" and c in cols:
            j = cols.index(c)
            X[:, j] = np.log(np.clip(X[:, j], 1e-300, None))
    return X


def forward_target(y: np.ndarray, spec: Dict[str, Any]) -> np.ndarray:
    return np.log(np.clip(y, 1e-300, None)) if spec.get("target") == "log" else np.array(y, dtype=float)


def inverse_target(z: np.ndarray, spec: Dict[str, Any]) -> np.ndarray:
    return np.exp(z) if spec.get("target") == "log" else np.array(z, dtype=float)


def make_splits(d: pd.DataFrame, rules: Dict[str, Any]) -> Dict[str, Any]:
    """Return index arrays (into d) for fit / calibration / random_test / corner."""
    sp = rules.get("split", {})
    seed = int(sp.get("seed", 0))
    axis = sp.get("corner_axis")
    q = float(sp.get("corner_quantile", 0.9))
    test_frac = float(sp.get("random_test_fraction", 0.2))
    cal_frac = float(sp.get("calibration_fraction", 0.25))
    rng = np.random.RandomState(seed)
    idx = np.arange(len(d))
    if axis and axis in d.columns and pd.api.types.is_numeric_dtype(d[axis]):
        thr = float(d[axis].quantile(q))
        corner = idx[(d[axis] >= thr).to_numpy()]
        interior = idx[(d[axis] < thr).to_numpy()]
    else:
        thr = None
        corner = np.array([], dtype=int)
        interior = idx
    perm = rng.permutation(interior)
    n_test = max(1, int(round(test_frac * len(perm))))
    random_test = np.sort(perm[:n_test])
    rest = perm[n_test:]
    n_cal = max(1, int(round(cal_frac * len(rest))))
    calibration = np.sort(rest[:n_cal])
    fit = np.sort(rest[n_cal:])
    return {"corner_axis": axis, "corner_quantile": q, "corner_threshold": thr, "seed": seed,
            "fit": fit.tolist(), "calibration": calibration.tolist(), "random_test": random_test.tolist(),
            "corner": corner.tolist()}


def fit_models(X_fit: np.ndarray, y_fit: np.ndarray, X_cal: np.ndarray, y_cal: np.ndarray,
               nominal: float = 0.90) -> Dict[str, Any]:
    from sklearn.dummy import DummyRegressor  # type: ignore
    from sklearn.ensemble import HistGradientBoostingRegressor  # type: ignore
    from sklearn.linear_model import Ridge  # type: ignore
    from sklearn.pipeline import make_pipeline  # type: ignore
    from sklearn.preprocessing import StandardScaler  # type: ignore

    n_fit = len(y_fit)
    ensemble = []
    for s in ENSEMBLE_SEEDS:
        m = HistGradientBoostingRegressor(max_iter=300, learning_rate=0.05, max_leaf_nodes=15,
                                          min_samples_leaf=max(3, n_fit // 25), l2_regularization=0.0,
                                          random_state=s, early_stopping=False)
        m.fit(X_fit, y_fit)
        ensemble.append(m)
    linear = make_pipeline(StandardScaler(), Ridge(alpha=1e-6))
    linear.fit(X_fit, y_fit)
    mean = DummyRegressor(strategy="mean").fit(X_fit, y_fit)
    # smooth low-dimensional physics favours smooth learners: a quadratic ridge and an
    # anisotropic-RBF Gaussian process (the kriging-style candidate)
    from sklearn.gaussian_process import GaussianProcessRegressor  # type: ignore
    from sklearn.gaussian_process.kernels import RBF, ConstantKernel, WhiteKernel  # type: ignore
    from sklearn.preprocessing import PolynomialFeatures  # type: ignore
    poly2 = make_pipeline(StandardScaler(), PolynomialFeatures(degree=2, include_bias=False), Ridge(alpha=1e-3))
    poly2.fit(X_fit, y_fit)
    n_dim = X_fit.shape[1]
    kernel = ConstantKernel(1.0, (1e-3, 1e3)) * RBF(length_scale=np.ones(n_dim), length_scale_bounds=(1e-2, 1e3)) \
        + WhiteKernel(1e-4, (1e-10, 1e-1))
    gp = make_pipeline(StandardScaler(), GaussianProcessRegressor(kernel=kernel, normalize_y=True, n_restarts_optimizer=2,
                                                                  random_state=0))
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")   # GP kernel-bound warnings are benign; the fit is still deterministic
        gp.fit(X_fit, y_fit)

    candidates = {"ensemble": None, "linear": linear, "poly2": poly2, "gp": gp}

    def predict_candidate(name: str, X: np.ndarray) -> np.ndarray:
        if name == "ensemble":
            return np.column_stack([m.predict(X) for m in ensemble]).mean(axis=1)
        return candidates[name].predict(X)

    cal_rmse = {name: float(np.sqrt(np.mean((predict_candidate(name, X_cal) - y_cal) ** 2))) for name in candidates}
    champion = min(cal_rmse, key=lambda k: (cal_rmse[k], k))
    cal_pred = predict_candidate(champion, X_cal)
    # split conformal: finite-sample-corrected quantile of |residual| on the calibration set
    resid = np.abs(y_cal - cal_pred)
    n = len(resid)
    k = min(n, int(np.ceil((n + 1) * nominal)))
    q_hat = float(np.sort(resid)[k - 1]) if n else float("nan")
    return {"ensemble": ensemble, "linear": linear, "poly2": poly2, "gp": gp, "mean": mean, "champion": champion,
            "conformal_q": q_hat, "conformal_nominal": nominal, "calibration_rmse": cal_rmse}


def predict_entry(entry: Dict[str, Any], X_orig: np.ndarray, which: Optional[str] = None) -> Dict[str, np.ndarray]:
    """Predict in ORIGINAL feature/target units from a bundle entry (transforms applied inside)."""
    model = entry["model"]
    spec = entry.get("transform", {"features": {}, "target": None})
    X = apply_feature_transform(X_orig, entry["feature_columns"], spec)
    which = which or model["champion"]
    P = np.column_stack([m.predict(X) for m in model["ensemble"]])
    ens_mean, ens_std = P.mean(axis=1), P.std(axis=1)
    preds_t = {"ensemble": ens_mean, "linear": model["linear"].predict(X), "poly2": model["poly2"].predict(X),
               "gp": model["gp"].predict(X), "mean": model["mean"].predict(X)}
    champ_t = preds_t[which]
    q = model["conformal_q"]
    out = {k: inverse_target(v, spec) for k, v in preds_t.items()}
    out["champion"] = inverse_target(champ_t, spec)
    out["pi_low"] = inverse_target(champ_t - q, spec)
    out["pi_high"] = inverse_target(champ_t + q, spec)
    out["ensemble_std"] = ens_std if spec.get("target") != "log" else ens_std * np.abs(out["ensemble"])
    return out


def train(corpus_path: Path, gate_report: Dict[str, Any], rules: Dict[str, Any], out_dir: Path,
          components: Optional[List[str]] = None, targets: Optional[List[str]] = None) -> Dict[str, Any]:
    t0 = time.perf_counter()
    df = load_corpus(corpus_path)
    adm = np.array(gate_report["admissible_index"], dtype=int)
    d_all = df.iloc[adm].reset_index(drop=True)
    features = feature_columns(df, rules)
    targets = targets or list(rules.get("targets", ["T_max_K"]))
    comps = components or sorted(d_all["component_name"].dropna().unique().tolist())
    bundle: Dict[str, Any] = {}
    meta_models: Dict[str, Any] = {}
    for comp in comps:
        dc = d_all[d_all["component_name"] == comp].reset_index(drop=True)
        for t in targets:
            if t not in dc.columns:
                continue
            dt = dc[dc[t].notna()].reset_index(drop=True)
            if len(dt) < 20:
                meta_models["%s/%s" % (comp, t)] = {"skipped": "fewer than 20 admissible non-null rows (%d)" % len(dt)}
                continue
            splits = make_splits(dt, rules)
            X_orig, cols = design_matrix(dt, features)
            spec = _transform_spec(rules, t, cols)
            X = apply_feature_transform(X_orig, cols, spec)
            y = forward_target(dt[t].to_numpy(dtype=float), spec)
            fit_i, cal_i = np.array(splits["fit"]), np.array(splits["calibration"])
            model = fit_models(X[fit_i], y[fit_i], X[cal_i], y[cal_i], float(rules.get("v1", {}).get("coverage_nominal", 0.90)))
            key = "%s/%s" % (comp, t)
            bundle[key] = {"model": model, "feature_columns": cols, "features": features, "component": comp,
                           "target": t, "row_case_ids": dt["case_id"].tolist(), "splits": splits, "transform": spec}
            meta_models[key] = {"n_rows": int(len(dt)), "n_fit": int(len(fit_i)), "n_calibration": int(len(cal_i)),
                                "n_random_test": len(splits["random_test"]), "n_corner": len(splits["corner"]),
                                "champion": model["champion"], "conformal_q": model["conformal_q"],
                                "calibration_rmse": model["calibration_rmse"], "feature_columns": cols,
                                "transform": spec, "calibration_rmse_space": "log" if spec.get("target") == "log" else "original",
                                "corner_axis": splits["corner_axis"], "corner_threshold": splits["corner_threshold"]}
    out_dir.mkdir(parents=True, exist_ok=True)
    with open(out_dir / "model_bundle.pkl", "wb") as fh:
        pickle.dump(bundle, fh)
    meta = {
        "gate": "M1 model build", "timestamp_utc": utc_now(), "corpus": corpus_fingerprint(corpus_path),
        "gate_report_passed": bool(gate_report.get("passed")), "n_admissible_rows": int(len(adm)),
        "rules_vertical": rules.get("vertical"), "feature_policy": rules.get("feature_policy"),
        "features": features, "targets": targets, "components": comps, "ensemble_seeds": list(ENSEMBLE_SEEDS),
        "split_spec": rules.get("split"), "models": meta_models, "versions": _versions(),
        "training_wall_time_s": time.perf_counter() - t0, "omp_num_threads": os.environ.get("OMP_NUM_THREADS"),
    }
    write_json(out_dir / "model_meta.json", meta)
    return meta


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="M1 corpus-native B1 trainer")
    p.add_argument("--corpus", required=True)
    p.add_argument("--gate-report", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--out", required=True)
    p.add_argument("--component", nargs="*", default=None)
    p.add_argument("--targets", nargs="*", default=None)
    a = p.parse_args(argv)
    gate = read_json(Path(a.gate_report))
    if not gate.get("passed"):
        print("refusing to train: the G1 gate report says the corpus did not pass")
        return 2
    meta = train(Path(a.corpus), gate, read_json(Path(a.rules)), Path(a.out), a.component, a.targets)
    for k, m in meta["models"].items():
        if "skipped" in m:
            print("  %-32s skipped: %s" % (k, m["skipped"]))
        else:
            cr = m["calibration_rmse"]
            print("  %-28s champion=%-8s cal-RMSE ens=%.3g lin=%.3g poly2=%.3g gp=%.3g  q90=%.3g  (fit %d / cal %d / test %d / corner %d)"
                  % (k, m["champion"], cr["ensemble"], cr["linear"], cr["poly2"], cr["gp"],
                     m["conformal_q"], m["n_fit"], m["n_calibration"], m["n_random_test"], m["n_corner"]))
    print("M1 artifact: %s (%.1f s)" % (Path(a.out) / "model_bundle.pkl", meta["training_wall_time_s"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
