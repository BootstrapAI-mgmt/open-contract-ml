"""Shared helpers for the TASK-10 corpus consumer (E-2): schema, loading, stats, I/O.

The corpus contract is cfd-automation's PSW04 schema (TC-PSW04,
``cfd_auto/sweep/corpus.py``): one row per (case_id, component_name); swept
parameters as dotted-path columns; ``mesh_size_mm`` / ``n_cells`` inputs;
``T_max_K`` / ``T_min_K`` / ``T_mean_K`` / ``pass_fail_status`` / ``margin_K``
targets; ``wall_time_s`` / ``cost_usd`` / ``convergence_status`` /
``final_residual_T`` metadata. Extra columns (fea-automation's strength
targets, ``solver_input_hash``) are allowed and reported, never required.

ASCII-only source by project rule (LESSONS L15).
"""

from __future__ import annotations

import hashlib
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

import numpy as np
import pandas as pd

IDENTIFIER_COLUMNS = ("case_id", "component_name")
MESH_COLUMNS = ("mesh_size_mm", "n_cells")
PSW04_TARGETS = ("T_max_K", "T_min_K", "T_mean_K", "pass_fail_status", "margin_K")
META_COLUMNS = ("wall_time_s", "cost_usd", "convergence_status", "final_residual_T")
OPTIONAL_COLUMNS = ("max_vm_stress_Pa", "max_disp_m", "compliance_J", "mass_kg", "margin_stress_Pa",
                    "solver_input_hash")
STRING_COLUMNS = ("case_id", "component_name", "pass_fail_status", "convergence_status", "solver_input_hash")
REQUIRED_COLUMNS = IDENTIFIER_COLUMNS + MESH_COLUMNS + PSW04_TARGETS + META_COLUMNS


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _clean(obj: Any) -> Any:
    if isinstance(obj, (np.floating, float)):
        f = float(obj)
        return None if (math.isnan(f) or math.isinf(f)) else f
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.bool_, bool)):
        return bool(obj)
    if isinstance(obj, dict):
        return {str(k): _clean(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, np.ndarray)):
        return [_clean(v) for v in list(obj)]
    return obj


def write_json(path: Path, payload: Dict[str, Any]) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(_clean(payload), indent=2, sort_keys=True, allow_nan=False) + "\n",
                          encoding="utf-8")


def read_json(path: Path) -> Dict[str, Any]:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def load_corpus(path: "str | Path") -> pd.DataFrame:
    """Read Parquet or CSV; coerce numeric columns to float64 and strings to object."""
    p = Path(path)
    if p.suffix.lower() == ".parquet":
        df = pd.read_parquet(p)
    else:
        df = pd.read_csv(p)
    for c in df.columns:
        if c in STRING_COLUMNS:
            df[c] = df[c].astype("object").where(df[c].notna(), None)
        else:
            if df[c].dtype == object:
                # a swept categorical parameter stays a string column; numeric-looking objects become float
                converted = pd.to_numeric(df[c], errors="coerce")
                if converted.notna().sum() >= df[c].notna().sum() and df[c].notna().any():
                    df[c] = converted.astype("float64")
            else:
                try:
                    df[c] = df[c].astype("float64")
                except (TypeError, ValueError):
                    pass
    return df


def swept_columns(df: pd.DataFrame) -> List[str]:
    """Swept-parameter columns = everything that is not identifier / mesh / target / metadata / optional."""
    known = set(REQUIRED_COLUMNS) | set(OPTIONAL_COLUMNS)
    return [c for c in df.columns if c not in known]


def numeric_feature_columns(df: pd.DataFrame, features: Sequence[str]) -> List[str]:
    return [c for c in features if pd.api.types.is_numeric_dtype(df[c])]


def corpus_fingerprint(path: Path) -> Dict[str, Any]:
    return {"path": str(path), "sha256": sha256_file(path), "bytes": path.stat().st_size}


# ---- statistics --------------------------------------------------------------

def spearman(x: np.ndarray, y: np.ndarray) -> Tuple[float, float]:
    """(rho, p-value) via scipy when available, else a t-approximation."""
    try:
        import warnings
        from scipy.stats import spearmanr  # type: ignore
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")      # a constant input gives rho = nan -> handled below
            res = spearmanr(x, y)
        rho = float(res.statistic if hasattr(res, "statistic") else res[0])
        pval = float(res.pvalue if hasattr(res, "pvalue") else res[1])
        if math.isnan(rho):
            return 0.0, 1.0
        return rho, pval
    except ImportError:  # pragma: no cover
        rx = pd.Series(x).rank().to_numpy()
        ry = pd.Series(y).rank().to_numpy()
        if rx.std() == 0 or ry.std() == 0:
            return 0.0, 1.0
        rho = float(np.corrcoef(rx, ry)[0, 1])
        n = len(x)
        t = rho * math.sqrt(max(n - 2, 1) / max(1e-12, 1 - rho * rho))
        pval = 2.0 * (1.0 - _t_cdf(abs(t), n - 2))
        return rho, pval


def _t_cdf(t: float, dof: int) -> float:  # pragma: no cover - fallback only
    x = dof / (dof + t * t)
    return 1.0 - 0.5 * _betainc(dof / 2.0, 0.5, x)


def _betainc(a: float, b: float, x: float) -> float:  # pragma: no cover - crude fallback
    n = 2000
    xs = np.linspace(0, x, n + 1)[1:]
    ys = xs ** (a - 1) * (1 - xs) ** (b - 1)
    from math import gamma
    return float(np.trapz(ys, xs) * gamma(a + b) / (gamma(a) * gamma(b)))


def one_way_anova(groups: List[np.ndarray]) -> Tuple[float, float, float]:
    """(F, p-value, eta_squared) for a list of groups."""
    groups = [g[~np.isnan(g)] for g in groups if len(g) > 0]
    groups = [g for g in groups if len(g) > 0]
    if len(groups) < 2:
        return 0.0, 1.0, 0.0
    allv = np.concatenate(groups)
    grand = allv.mean()
    ss_between = sum(len(g) * (g.mean() - grand) ** 2 for g in groups)
    ss_total = float(((allv - grand) ** 2).sum())
    eta2 = ss_between / ss_total if ss_total > 0 else 0.0
    try:
        from scipy.stats import f_oneway  # type: ignore
        res = f_oneway(*groups)
        F = float(res.statistic if hasattr(res, "statistic") else res[0])
        p = float(res.pvalue if hasattr(res, "pvalue") else res[1])
        if math.isnan(F):
            return 0.0, 1.0, eta2
        return F, p, eta2
    except ImportError:  # pragma: no cover
        return 0.0, (0.0 if eta2 > 0.5 else 1.0), eta2


def residual_after_linear(y: np.ndarray, X: np.ndarray) -> np.ndarray:
    """Residual of y after ordinary least squares on X (with intercept)."""
    A = np.column_stack([np.ones(len(y)), X])
    coef, *_ = np.linalg.lstsq(A, y, rcond=None)
    return y - A @ coef
