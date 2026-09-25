"""Physically grounded synthetic heat-shield corpus in the corpus-consumer schema.

Response source: thermal-mesh-calculators' ``SingleLayerShieldCalculator``
(Newton-Raphson shield energy balance, deterministic),
composed into a three-component per-case chain:

    exhaust (fixed surface temperature, the source)
      -> heat_shield  (single-layer shield equilibrium)
        -> protected_part (a second shield equation with the shield's outer
                           face as its source; exchange factor for parallel
                           plates 1/(1/eps_shield_out + 1/eps_part - 1))

Swept parameters are emitted as dotted paths in the vocabulary of a CFD
zone-thermal overlay:
``zones.exhaust.t_surf_K``, ``zones.underhood.t_air_K``,
``zones.underhood.h_out_W_m2K``, ``zones.heat_shield.eps_out``.
``mesh_size_mm`` / ``n_cells`` are derived from thermal-mesh-calculators'
boundary-driven sizing, so the mesh columns are realistic provenance rather
than filler.

Defect modes generate the G1 fail demonstrations:
  --defect mesh-only     a sweep that never reaches the physics: the swept axis is ``mesh.t_fluid_K``,
                         which reaches only mesh sizing; physics is fixed;
                         targets carry a first-order discretisation term
  --defect diverged      20 % of cases are non-converged
  --defect celsius-bug   10 % of rows report temperatures in deg C (bounds)
  --no-data-card         omit data_card.json (G1.7)
  --no-hash-column       omit solver_input_hash (forces the statistical G1.3 path)

Layout written under --out mirrors a sweep directory: training_corpus.parquet
(+ .csv), sweep_config.json, sweep_manifest.json, data_card.json.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import random
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd

from .cc_common import utc_now, write_json

try:
    from thermal_mesh_calculators import BoundaryDrivenConductionCalculator, SingleLayerShieldCalculator
except ImportError as exc:  # pragma: no cover
    raise SystemExit("thermal-mesh-calculators is required: pip install thermal-mesh-calculators (%s)" % exc)

try:
    import thermal_mesh_calculators as _tmc
    TMC_VERSION = getattr(_tmc, "__version__", "unknown")
except Exception:  # pragma: no cover
    TMC_VERSION = "unknown"

RANGES = {
    "zones.exhaust.t_surf_K": (800.0, 1100.0),
    "zones.underhood.t_air_K": (300.0, 380.0),
    "zones.underhood.h_out_W_m2K": (10.0, 60.0),
    "zones.heat_shield.eps_out": (0.3, 0.9),
}
NOMINAL = {"zones.exhaust.t_surf_K": 950.0, "zones.underhood.t_air_K": 340.0,
           "zones.underhood.h_out_W_m2K": 30.0, "zones.heat_shield.eps_out": 0.6}
FIXED = {"eps_in_shield": 0.4, "h_in_shield": 30.0, "eps_part": 0.9, "k_shield_W_mK": 45.0,
         "limit_shield_K": 800.0, "limit_part_K": 400.0, "max_dt_K": 10.0, "shield_area_m2": 0.2}
COMPONENTS = ("exhaust", "heat_shield", "protected_part")


def lhs(n: int, seed: int, ranges: Dict[str, tuple]) -> List[Dict[str, float]]:
    rng = random.Random(seed)
    cols = {}
    for name, (lo, hi) in ranges.items():
        strata = list(range(n))
        rng.shuffle(strata)
        cols[name] = [lo + (hi - lo) * (s + rng.random()) / n for s in strata]
    return [{k: cols[k][i] for k in ranges} for i in range(n)]


def physics(point: Dict[str, float]) -> Dict[str, Any]:
    """Deterministic three-component chain; returns per-component temperatures + bc hash."""
    t_surf = point["zones.exhaust.t_surf_K"]
    t_air = point["zones.underhood.t_air_K"]
    h_out = point["zones.underhood.h_out_W_m2K"]
    eps_out = point["zones.heat_shield.eps_out"]
    s = SingleLayerShieldCalculator()
    shield = s.solve_temperature(t_exh=t_surf, t_fluid=t_air, t_surr=t_air, eps_in=FIXED["eps_in_shield"],
                                 eps_out=eps_out, h_in=FIXED["h_in_shield"], h_out=h_out, tol=1e-6, max_iter=200)
    eps_exch = 1.0 / (1.0 / eps_out + 1.0 / FIXED["eps_part"] - 1.0)
    part = s.solve_temperature(t_exh=shield["t_shield_K"], t_fluid=t_air, t_surr=t_air, eps_in=eps_exch,
                               eps_out=FIXED["eps_part"], h_in=h_out, h_out=h_out, tol=1e-6, max_iter=200)
    bc_hash = hashlib.sha256(json.dumps({"t_surf": t_surf, "t_air": t_air, "h_out": h_out, "eps_out": eps_out},
                                        sort_keys=True).encode("ascii")).hexdigest()
    return {"exhaust": t_surf, "heat_shield": shield["t_shield_K"], "protected_part": part["t_shield_K"],
            "converged": bool(shield["converged"] and part["converged"]), "bc_hash": bc_hash,
            "iterations": shield["iterations"] + part["iterations"]}


def mesh_sizing(t_shield: float, t_fluid_for_sizing: float, h_out: float, eps_out: float) -> Dict[str, float]:
    c = BoundaryDrivenConductionCalculator()
    r = c.max_mesh_size(k=FIXED["k_shield_W_mK"], h=h_out, t_surf=t_shield, t_fluid=t_fluid_for_sizing,
                        epsilon=eps_out, t_surr=t_fluid_for_sizing, max_dt=FIXED["max_dt_K"])
    dx_mm = max(1.0, min(50.0, float(r["max_dx_mm"])))
    n_cells = int(round(FIXED["shield_area_m2"] / (dx_mm * 1e-3) ** 2)) * 40   # 40 layers of the fluid volume, illustrative
    return {"mesh_size_mm": dx_mm, "n_cells": float(n_cells)}


def build(n: int, seed: int, defect: str, data_card: bool, hash_column: bool, out: Path) -> Path:
    out.mkdir(parents=True, exist_ok=True)
    rows: List[Dict[str, Any]] = []
    cases: List[Dict[str, Any]] = []
    rng = random.Random(seed + 1)
    if defect == "mesh-only":
        ranges = {"mesh.t_fluid_K": (600.0, 800.0), "mesh.t_surr_K": (290.0, 320.0)}
        points = lhs(n, seed, ranges)
    else:
        ranges = dict(RANGES)
        points = lhs(n, seed, ranges)
    started = utc_now()
    for i, pt in enumerate(points, start=1):
        case_id = "case_%04d" % i
        if defect == "mesh-only":
            phys_point = dict(NOMINAL)                     # physics never changes: the sweep reaches only the mesh
            ph = physics(phys_point)
            sizing = mesh_sizing(ph["heat_shield"], pt["mesh.t_fluid_K"], NOMINAL["zones.underhood.h_out_W_m2K"],
                                 NOMINAL["zones.heat_shield.eps_out"])
            # first-order discretisation error rides on the mesh size (deterministic, mesh-driven)
            disc = 0.05 * sizing["mesh_size_mm"]
        else:
            ph = physics(pt)
            sizing = mesh_sizing(ph["heat_shield"], pt["zones.underhood.t_air_K"], pt["zones.underhood.h_out_W_m2K"],
                                 pt["zones.heat_shield.eps_out"])
            disc = 0.0
        diverged = defect == "diverged" and rng.random() < 0.20
        celsius = defect == "celsius-bug" and rng.random() < 0.10
        status = "diverged" if diverged else "converged"
        resid = 5.0e-2 if diverged else 1.0e-6
        cases.append({"case_id": case_id, "parameter_point": pt, "status": "completed", "convergence_status": status,
                      "wall_time_s": 600.0 + 3.0 * sizing["n_cells"] / 1000.0, "cost_usd": 0.0,
                      "final_residuals": {"T": resid}})
        for comp in COMPONENTS:
            t = ph[comp] + disc
            if diverged:
                t_max = t_min = t_mean = None
            else:
                t_max, t_min, t_mean = t, t - (0.0 if comp == "exhaust" else 8.0), t - (0.0 if comp == "exhaust" else 3.0)
                if celsius:
                    t_max, t_min, t_mean = t_max - 273.15, t_min - 273.15, t_mean - 273.15
            limit = {"exhaust": None, "heat_shield": FIXED["limit_shield_K"], "protected_part": FIXED["limit_part_K"]}[comp]
            margin = None if (limit is None or t_max is None) else limit - t_max
            if t_max is None:
                pf = "unknown"
            elif margin is None:
                pf = "no_limit"
            else:
                pf = "pass" if margin >= 0 else "fail"
            row: Dict[str, Any] = {"case_id": case_id, "component_name": comp}
            row.update(pt)
            row.update(sizing)
            row.update({"T_max_K": t_max, "T_min_K": t_min, "T_mean_K": t_mean, "pass_fail_status": pf,
                        "margin_K": margin, "wall_time_s": cases[-1]["wall_time_s"], "cost_usd": 0.0,
                        "convergence_status": status, "final_residual_T": resid})
            if hash_column:
                row["solver_input_hash"] = ph["bc_hash"]
            rows.append(row)
    df = pd.DataFrame(rows)
    swept = sorted(ranges)
    order = (["case_id", "component_name"] + swept + ["mesh_size_mm", "n_cells", "T_max_K", "T_min_K", "T_mean_K",
             "pass_fail_status", "margin_K", "wall_time_s", "cost_usd", "convergence_status", "final_residual_T"]
             + (["solver_input_hash"] if hash_column else []))
    df = df[order]
    for c in order:
        if c not in ("case_id", "component_name", "pass_fail_status", "convergence_status", "solver_input_hash"):
            df[c] = df[c].astype("float64")
    try:
        df.to_parquet(out / "training_corpus.parquet", index=False)
        written = out / "training_corpus.parquet"
    except (ImportError, ValueError):
        written = out / "training_corpus.csv"
    df.to_csv(out / "training_corpus.csv", index=False)
    write_json(out / "sweep_config.json", {"name": out.name, "method": "latin_hypercube", "n_samples": n, "seed": seed,
                                           "parameters": [{"name": k, "type": "continuous", "low": lo, "high": hi}
                                                          for k, (lo, hi) in ranges.items()]})
    write_json(out / "sweep_manifest.json", {"sweep_id": out.name, "generator": "synth_corpus.py (tmc %s)" % TMC_VERSION,
                                             "generator_commit": "n/a-synthetic", "started_utc": started,
                                             "finished_utc": utc_now(), "n_cases": n,
                                             "n_completed": n, "n_failed": 0, "cases": cases})
    if data_card:
        write_json(out / "data_card.json", {
            "corpus_file": written.name, "schema": "corpus-consumer schema (opencontractml.cc_common)",
            "generator": "synth_corpus.py (thermal-mesh-calculators %s shield solver)" % TMC_VERSION,
            "generator_commit": "n/a-synthetic", "solver": ["thermal-mesh-calculators %s SingleLayerShieldCalculator" % TMC_VERSION],
            "mesh_policy": "tmc BoundaryDrivenConductionCalculator.max_mesh_size(max_dt=%.0f K), 40 illustrative layers" % FIXED["max_dt_K"],
            "sampler": "latin_hypercube", "seed": seed, "swept_parameters": swept,
            "intended_ranges": {k: {"type": "continuous", "low": lo, "high": hi} for k, (lo, hi) in ranges.items()},
            "units": {"temperature": "K", "h": "W/m2K", "mesh_size_mm": "mm"},
            "date_range_utc": [started, utc_now()], "analyst": "synth_corpus.py",
            "defect_mode": defect, "n_cases": n, "n_rows": len(df), "columns": order,
            "fixed_physics": FIXED, "components": list(COMPONENTS),
        })
    return written


def main(argv=None) -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--out", required=True)
    p.add_argument("--n", type=int, default=200)
    p.add_argument("--seed", type=int, default=0)
    p.add_argument("--defect", choices=["none", "mesh-only", "diverged", "celsius-bug"], default="none")
    p.add_argument("--no-data-card", action="store_true")
    p.add_argument("--no-hash-column", action="store_true")
    a = p.parse_args(argv)
    written = build(a.n, a.seed, a.defect, not a.no_data_card, not a.no_hash_column, Path(a.out))
    print("wrote %s (%d cases x %d components, defect=%s)" % (written, a.n, len(COMPONENTS), a.defect))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
