"""G1 -- corpus acceptance gate for training corpora in the corpus-consumer schema.

The G1 checks:

  G1.1 schema         required columns present with the right kinds
  G1.2 admissibility  converged rows with finite targets; admissible fraction >= floor
  G1.3 physics reach  every swept axis must reach the response: (a) vocabulary --
                      the axis is one of the vertical's declared physics_inputs;
                      (b) structural -- distinct parameter points give distinct
                      solver_input_hash values when that column exists; (c) statistical
                      -- ANOVA / Spearman association, raw or partial after the other
                      axes; (d) mesh dominance -- no target is a function of
                      mesh_size_mm / n_cells alone (von Neumann ratio test)
  G1.4 DOE coverage   admissible rows span the intended ranges; corner has enough cases
  G1.5 regime bounds  per-target bounds from the rules file; margin/pass-fail consistency
  G1.6 degeneracy     no duplicate parameter points; no constant target
  G1.7 data card      required provenance fields present

Usage:
  python -m opencontractml.corpus_gate --corpus <dir>/training_corpus.parquet --rules <rules.json> --report out/corpus_gate_report.json

Exit code 0 when every check passes, 1 otherwise. The report carries the
admissible-row index so train_b1.py trains only on what the gate admitted.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, List

import numpy as np
import pandas as pd

from .cc_common import (MESH_COLUMNS, REQUIRED_COLUMNS, STRING_COLUMNS, corpus_fingerprint, load_corpus,
                       one_way_anova, read_json, residual_after_linear, spearman, swept_columns, utc_now,
                       write_json)

P_VALUE = 0.05
EFFECT_FLOOR_RHO = 0.10
EFFECT_FLOOR_ETA2 = 0.01
DISCRETE_MAX_LEVELS = 10


def _check(name: str, passed: bool, **detail: Any) -> Dict[str, Any]:
    return {"check": name, "passed": bool(passed), "detail": detail}


# ---- G1.1 -----------------------------------------------------------------

def g1_1_schema(df: pd.DataFrame) -> Dict[str, Any]:
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    wrong_kind = []
    for c in df.columns:
        if c in STRING_COLUMNS:
            continue
        if c in REQUIRED_COLUMNS and not pd.api.types.is_numeric_dtype(df[c]):
            wrong_kind.append(c)
    extra = [c for c in df.columns if c not in REQUIRED_COLUMNS]
    return _check("G1.1 schema", not missing and not wrong_kind, missing=missing, wrong_kind=wrong_kind,
                  extra_columns=extra, n_rows=int(len(df)))


# ---- G1.2 -----------------------------------------------------------------

def g1_2_admissibility(df: pd.DataFrame, rules: Dict[str, Any], targets: List[str]) -> Dict[str, Any]:
    adm = rules.get("admissibility", {})
    ok_status = set(adm.get("convergence_status_ok", ["converged"]))
    resid_max = float(adm.get("final_residual_max", 1e-4))
    floor = float(adm.get("min_admissible_fraction", 0.90))
    status_ok = df["convergence_status"].isin(ok_status)
    resid = pd.to_numeric(df["final_residual_T"], errors="coerce")
    resid_ok = resid.isna() | (resid <= resid_max)
    admissible = status_ok.to_numpy() & resid_ok.to_numpy()
    cases_total = df["case_id"].nunique()
    cases_ok = df.loc[admissible, "case_id"].nunique()
    frac = cases_ok / cases_total if cases_total else 0.0
    quarantined = df.loc[~admissible, ["case_id", "component_name", "convergence_status"]].to_dict("records")
    # a null target on an admissible row is legitimate (e.g. margin_K on a component without a
    # limit); it is reported per (component, target) and the trainer drops it per target
    null_targets: Dict[str, Any] = {}
    for comp, dc in df.iloc[np.flatnonzero(admissible)].groupby("component_name"):
        for t in targets:
            if t in dc.columns:
                n_null = int(dc[t].isna().sum())
                if n_null:
                    null_targets["%s/%s" % (comp, t)] = {"n_null": n_null, "n_rows": int(len(dc))}
    return _check("G1.2 admissibility", frac >= floor and cases_ok > 0, admissible_fraction=frac, floor=floor,
                  n_cases=int(cases_total), n_cases_admissible=int(cases_ok), n_rows_admissible=int(admissible.sum()),
                  n_quarantined_rows=int((~admissible).sum()), quarantined=quarantined[:50],
                  null_targets_on_admissible_rows=null_targets,
                  admissible_index=[int(i) for i in np.flatnonzero(admissible)])


# ---- G1.3 -----------------------------------------------------------------

def _is_discrete(s: pd.Series) -> bool:
    return (not pd.api.types.is_numeric_dtype(s)) or s.nunique(dropna=True) <= DISCRETE_MAX_LEVELS


def _association(x: pd.Series, y: np.ndarray) -> Dict[str, float]:
    if _is_discrete(x):
        groups = [y[(x == lvl).to_numpy()] for lvl in x.dropna().unique()]
        F, p, eta2 = one_way_anova(groups)
        return {"kind": "anova", "stat": F, "p": p, "effect": eta2, "floor": EFFECT_FLOOR_ETA2}
    rho, p = spearman(x.to_numpy(dtype=float), y)
    return {"kind": "spearman", "stat": rho, "p": p, "effect": abs(rho), "floor": EFFECT_FLOOR_RHO}


def _von_neumann_ratio(order_key: np.ndarray, y: np.ndarray) -> float:
    """mean((y_i - y_{i+1})^2) / (2 var(y)) with rows sorted by order_key.

    Near 0 when y is a smooth function of order_key alone (neighbours agree);
    O(1) when y depends on other things too. Nonparametric, model-free.
    """
    idx = np.argsort(order_key, kind="stable")
    ys = y[idx]
    var = float(np.var(ys))
    if var <= 0 or len(ys) < 3:
        return 1.0
    return float(np.mean(np.diff(ys) ** 2) / (2.0 * var))


MESH_DOMINANCE_RATIO = 0.02


def g1_3_physics_reach(df: pd.DataFrame, admissible: np.ndarray, swept: List[str], targets: List[str],
                       rules: Dict[str, Any] | None = None) -> Dict[str, Any]:
    """G1.3 in four parts: (a) vocabulary, (b) structural, (c) statistical reach, (d) mesh dominance."""
    rules = rules or {}
    d = df.iloc[admissible]
    per_axis: Dict[str, Any] = {}
    flags: List[str] = []
    # (a) vocabulary: a swept axis must be one of the vertical's declared physics inputs
    physics_inputs = rules.get("physics_inputs")
    if physics_inputs:
        allowed = set(physics_inputs)
        for ax in swept:
            if ax not in allowed:
                flags.append("SWEEP_AXIS_NOT_A_PHYSICS_INPUT: %s is not among the vertical's declared physics inputs %s"
                             % (ax, sorted(allowed)))
    # (b) structural: distinct parameter points must give distinct solver inputs
    structural = None
    if "solver_input_hash" in d.columns and d["solver_input_hash"].notna().any():
        cases = d.drop_duplicates("case_id")
        points = cases[swept].astype(str).agg("|".join, axis=1)
        n_points = points.nunique()
        n_hash = cases["solver_input_hash"].nunique()
        structural = {"n_distinct_points": int(n_points), "n_distinct_solver_inputs": int(n_hash)}
        if n_hash < n_points:
            flags.append("SWEEP_AXIS_UNREACHED(structural): %d distinct parameter points map to only %d distinct solver inputs"
                         % (n_points, n_hash))
        for ax in swept:
            others = [c for c in swept if c != ax]
            key = (cases[others].astype(str).agg("|".join, axis=1) if others
                   else pd.Series(["all"] * len(cases), index=cases.index))
            unreached = 0
            for _k, grp in cases.groupby(key):
                if grp[ax].nunique() > 1 and grp["solver_input_hash"].nunique() == 1:
                    unreached += 1
            if unreached:
                flags.append("SWEEP_AXIS_UNREACHED(structural): axis %s varied in %d group(s) without changing the solver input"
                             % (ax, unreached))
    # (c) statistical reach: raw or partial (after the other axes) association in at least one target
    for ax in swept:
        per_axis[ax] = {}
        reached_any = False
        for comp, dc in d.groupby("component_name"):
            for t in targets:
                if t not in dc.columns or not pd.api.types.is_numeric_dtype(dc[t]):
                    continue
                keep = dc[t].notna().to_numpy()
                if keep.sum() < 8:
                    continue
                dk = dc.loc[keep]
                y = dk[t].to_numpy(dtype=float)
                x = dk[ax]
                if np.nanstd(y) == 0:
                    continue
                raw = _association(x, y)
                other_num = [c for c in swept if c != ax and pd.api.types.is_numeric_dtype(dk[c])]
                partial = (_association(x, residual_after_linear(y, dk[other_num].to_numpy(dtype=float)))
                           if other_num else raw)
                reach = ((raw["p"] < P_VALUE and raw["effect"] >= raw["floor"])
                         or (partial["p"] < P_VALUE and partial["effect"] >= partial["floor"]))
                per_axis[ax]["%s/%s" % (comp, t)] = {"raw": raw, "partial_after_other_axes": partial, "reach": reach}
                reached_any = reached_any or reach
        if not reached_any:
            flags.append("SWEEP_AXIS_UNREACHED(statistical): axis %s shows no detectable response in any target" % ax)
    # (d) mesh dominance: is any target a function of mesh size alone?
    mesh_cols = [c for c in MESH_COLUMNS if c in d.columns and d[c].notna().any()]
    dominance: Dict[str, Any] = {}
    for comp, dc in d.groupby("component_name"):
        for t in targets:
            if t not in dc.columns or not pd.api.types.is_numeric_dtype(dc[t]):
                continue
            dk = dc.loc[dc[t].notna()]
            if len(dk) < 8 or np.nanstd(dk[t].to_numpy(dtype=float)) == 0:
                continue
            y = dk[t].to_numpy(dtype=float)
            for mc in mesh_cols:
                ratio = _von_neumann_ratio(dk[mc].to_numpy(dtype=float), y)
                dominance["%s/%s vs %s" % (comp, t, mc)] = ratio
                if ratio < MESH_DOMINANCE_RATIO:
                    flags.append("MESH_DOMINANT: %s/%s is a function of %s alone (von Neumann ratio %.4f < %.2f)"
                                 % (comp, t, mc, ratio, MESH_DOMINANCE_RATIO))
    return _check("G1.3 physics reach", not flags, flags=flags, structural=structural, per_axis=per_axis,
                  mesh_dominance=dominance, physics_inputs_declared=bool(physics_inputs))


# ---- G1.4 -----------------------------------------------------------------

def g1_4_coverage(df: pd.DataFrame, admissible: np.ndarray, swept: List[str], intended: Dict[str, Any],
                  rules: Dict[str, Any]) -> Dict[str, Any]:
    cov = rules.get("coverage", {})
    min_frac = float(cov.get("min_range_fraction", 0.8))
    n_corner_min = int(cov.get("n_corner_min", 5))
    d = df.iloc[admissible].drop_duplicates("case_id")
    problems: List[str] = []
    per_param: Dict[str, Any] = {}
    for ax in swept:
        spec = intended.get(ax)
        if spec is None:
            per_param[ax] = {"intended": None}
            problems.append("no intended range recorded for %s (sweep_config.json missing it)" % ax)
            continue
        if spec.get("type") == "discrete":
            levels = spec.get("levels") or spec.get("values") or []
            missing = [lv for lv in levels if not (d[ax].astype(str) == str(lv)).any()]
            per_param[ax] = {"intended_levels": levels, "missing_levels": missing}
            if missing:
                problems.append("discrete axis %s has no admissible case at level(s) %s" % (ax, missing))
        else:
            lo, hi = float(spec["low"]), float(spec["high"])
            span = (d[ax].max() - d[ax].min()) / (hi - lo) if hi > lo else 0.0
            per_param[ax] = {"intended": [lo, hi], "observed": [float(d[ax].min()), float(d[ax].max())], "span_fraction": float(span)}
            if span < min_frac:
                problems.append("axis %s covers only %.0f%% of its intended range" % (ax, 100 * span))
    split = rules.get("split", {})
    corner_axis = split.get("corner_axis")
    corner_q = float(split.get("corner_quantile", 0.9))
    n_corner = None
    if corner_axis and corner_axis in d.columns and pd.api.types.is_numeric_dtype(d[corner_axis]):
        thr = d[corner_axis].quantile(corner_q)
        n_corner = int((d[corner_axis] >= thr).sum())
        if n_corner < n_corner_min:
            problems.append("corner on %s has %d cases (< %d)" % (corner_axis, n_corner, n_corner_min))
    return _check("G1.4 DOE coverage", not problems, problems=problems, per_parameter=per_param,
                  corner_axis=corner_axis, n_corner_cases=n_corner, n_corner_min=n_corner_min)


# ---- G1.5 -----------------------------------------------------------------

def _bound_value(spec: Any, row: pd.Series) -> float:
    if isinstance(spec, dict) and "col" in spec:
        return float(row[spec["col"]])
    return float(spec)


def g1_5_bounds(df: pd.DataFrame, admissible: np.ndarray, rules: Dict[str, Any]) -> Dict[str, Any]:
    d = df.iloc[admissible]
    violations: List[Dict[str, Any]] = []
    n_checked = 0
    unevaluable: List[str] = []
    for b in rules.get("bounds", []):
        t = b["target"]
        if t not in d.columns:
            unevaluable.append("target %s not in corpus" % t)
            continue
        needed = [spec["col"] for spec in (b.get("lower"), b.get("upper")) if isinstance(spec, dict) and "col" in spec]
        missing_cols = [c for c in needed if c not in d.columns]
        if missing_cols:
            unevaluable.append("bound on %s references column(s) %s not in corpus" % (t, missing_cols))
            continue
        comps = b.get("components")
        sub = d if not comps else d[d["component_name"].isin(comps)]
        tol = float(b.get("tol", 0.0))
        for idx, row in sub.iterrows():
            v = row[t]
            if v is None or (isinstance(v, float) and np.isnan(v)):
                continue
            n_checked += 1
            if "lower" in b and v < _bound_value(b["lower"], row) - tol:
                violations.append({"row": int(idx), "target": t, "value": float(v), "bound": "lower",
                                   "limit": _bound_value(b["lower"], row)})
            if "upper" in b and v > _bound_value(b["upper"], row) + tol:
                violations.append({"row": int(idx), "target": t, "value": float(v), "bound": "upper",
                                   "limit": _bound_value(b["upper"], row)})
    cons = rules.get("consistency", {})
    mcol, pcol = cons.get("margin_col", "margin_K"), cons.get("pass_fail_col", "pass_fail_status")
    inconsistent = 0
    if mcol in d.columns and pcol in d.columns:
        m = pd.to_numeric(d[mcol], errors="coerce")
        pf = d[pcol].astype(str)
        inconsistent = int(((m >= 0) & (pf == "fail")).sum() + ((m < 0) & (pf == "pass")).sum())
    return _check("G1.5 regime bounds", not violations and inconsistent == 0 and not unevaluable, n_checked=n_checked,
                  n_violations=len(violations), violations=violations[:50], n_margin_passfail_inconsistent=inconsistent,
                  problems=unevaluable)


# ---- G1.6 -----------------------------------------------------------------

def g1_6_degeneracy(df: pd.DataFrame, admissible: np.ndarray, swept: List[str], targets: List[str]) -> Dict[str, Any]:
    d = df.iloc[admissible]
    cases = d.drop_duplicates("case_id")
    dup = int(cases.duplicated(subset=swept).sum()) if swept else 0
    constant = []
    for comp, dc in d.groupby("component_name"):
        for t in targets:
            if t in dc.columns and pd.api.types.is_numeric_dtype(dc[t]) and dc[t].notna().sum() > 1 and dc[t].nunique() <= 1:
                constant.append("%s/%s" % (comp, t))
    return _check("G1.6 degeneracy", dup == 0 and not constant, n_duplicate_points=dup, constant_targets=constant)


# ---- G1.7 -----------------------------------------------------------------

DATA_CARD_REQUIRED = ("solver", "mesh_policy", "sampler", "seed", "generator_commit", "units", "date_range_utc", "analyst")


def g1_7_data_card(corpus_path: Path) -> Dict[str, Any]:
    card_path = corpus_path.parent / "data_card.json"
    if not card_path.exists():
        return _check("G1.7 data card", False, missing_file=str(card_path))
    card = read_json(card_path)
    missing = [k for k in DATA_CARD_REQUIRED if k not in card or card[k] in (None, "", [], {})]
    return _check("G1.7 data card", not missing, missing_fields=missing, present_fields=sorted(card.keys()))


# ---- driver ---------------------------------------------------------------

def run_gate(corpus_path: Path, rules: Dict[str, Any], targets: List[str] | None = None) -> Dict[str, Any]:
    df = load_corpus(corpus_path)
    targets = targets or list(rules.get("targets", ["T_max_K"]))
    swept = swept_columns(df)
    intended = {}
    sc = corpus_path.parent / "sweep_config.json"
    if sc.exists():
        for p in read_json(sc).get("parameters", []):
            intended[p["name"]] = ({"type": "discrete", "levels": p.get("values", [])} if p.get("type") == "discrete"
                                   else {"type": "continuous", "low": p.get("low"), "high": p.get("high")})
    checks = [g1_1_schema(df)]
    if checks[0]["passed"]:
        c2 = g1_2_admissibility(df, rules, targets)
        adm = np.array(c2["detail"]["admissible_index"], dtype=int)
        checks.append(c2)
        if len(adm):
            checks += [g1_3_physics_reach(df, adm, swept, targets, rules), g1_4_coverage(df, adm, swept, intended, rules),
                       g1_5_bounds(df, adm, rules), g1_6_degeneracy(df, adm, swept, targets)]
    checks.append(g1_7_data_card(corpus_path))
    passed = all(c["passed"] for c in checks)
    admissible_index = next((c["detail"]["admissible_index"] for c in checks if c["check"] == "G1.2 admissibility"), [])
    return {"gate": "G1 corpus acceptance", "passed": passed, "timestamp_utc": utc_now(),
            "corpus": corpus_fingerprint(corpus_path), "rules_vertical": rules.get("vertical"),
            "targets": targets, "swept_parameters": swept, "n_rows": int(len(df)),
            "n_admissible_rows": len(admissible_index), "admissible_index": admissible_index,
            "checks": checks}


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description="G1 corpus acceptance gate (corpus-consumer schema)")
    p.add_argument("--corpus", required=True)
    p.add_argument("--rules", required=True)
    p.add_argument("--report", required=True)
    p.add_argument("--targets", nargs="*", default=None)
    a = p.parse_args(argv)
    rules = read_json(Path(a.rules))
    rep = run_gate(Path(a.corpus), rules, a.targets)
    write_json(Path(a.report), rep)
    for c in rep["checks"]:
        flags = c["detail"].get("flags") or c["detail"].get("problems") or c["detail"].get("missing_fields") or []
        print("  [%s] %s%s" % ("PASS" if c["passed"] else "FAIL", c["check"], ("  -- " + "; ".join(str(f) for f in flags)) if flags else ""))
    print("G1 %s: %d/%d admissible rows; report %s" % ("PASS" if rep["passed"] else "FAIL", rep["n_admissible_rows"],
                                                       rep["n_rows"], a.report))
    return 0 if rep["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
