"""
TASK-8-1103 Peak-Stress Surrogate — SAMPLE-DATA SYNTHESIZER
===========================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real FE results.

The functional form here is an analytical *pastiche* of beam-bending
plus stress-concentration-at-a-fillet — it is not a substitute for a
real FE solve. The purpose is to give the surrogate something
smoothly variable and qualitatively plausible to learn from, so the
reader can verify the workflow shape:

    base bending stress     σ_b  ≈ M·c / I          (M = F·L_eff)
    stress concentration    Kt   ≈ 1 + a·(d/r)^b    (d = thickness, r = fillet)
    hole-net-section bump   Kh   ≈ 1 + c·(hole/width)^2
    angle de-rating         Kang ≈ 1 - sin(angle)·0.15  (off-axis softens bending)
    peak vM stress          σ_pk = σ_b · Kt · Kh · Kang
    tip displacement        δ    ≈ F·L^3 / (3·E·I)  (Euler-Bernoulli cantilever)

The numerical coefficients are CHOSEN to make the synthetic responses
land in the data-contract.md typical ranges; they are NOT derived from
any specific FE benchmark and they do NOT reproduce the absolute
magnitudes of any specific real bracket. See data-contract.md and
WALKTHROUGH.md §4 for the illustrative-numerics framing.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --rows 400 --seed 7 --out my-data.csv
"""

import argparse
import csv
import math
import os
import random


# --- coefficients tuned so the synthetic responses cover the contract ranges ---
# (calibrated empirically against the contract's typical-range columns)
_KT_A = 0.70      # fillet stress-concentration amplitude (max Kt ≈ 2.7 at t/r=8)
_KT_B = 0.45      # fillet stress-concentration exponent
_KH_C = 0.80      # hole-net-section bump amplitude
_ANG_DERATE = 0.0035  # per-deg² off-axis softening (negligible at 0°, ~3 % at 30°)
_NOISE_FRAC = 0.03    # multiplicative scatter mimicking mesh / post-processing noise


def _sample_design(rng):
    """Sample one (geometry + load + material) input vector.

    Force is sampled in a band scaled by the section's bending capacity
    so the design space stays in the linear-static regime across the
    contract ranges. Without this coupling, a thin/long bracket at the
    top of the force range produces multi-GPa stresses far outside any
    realistic linear-static benchmark (and far outside the data
    contract's typical-range column). The coupling preserves the full
    range of `force_N` reported in the contract — `force_N` is still
    sampled from 200 to 4000 N when geometry permits — but biases the
    sampler away from physically-implausible corners.
    """
    length = rng.uniform(80.0, 200.0)        # mm
    width = rng.uniform(20.0, 60.0)          # mm
    thickness = rng.uniform(4.0, 16.0)       # mm
    fillet = rng.uniform(2.0, 12.0)          # mm
    # hole_dia constrained < width - 4 mm (else nonsense net section)
    hole_max = min(14.0, width - 4.0)
    hole = rng.uniform(0.0, hole_max) if hole_max > 0 else 0.0
    # force-vs-geometry coupling: aim for σ_b ≈ 100–500 MPa pre-Kt
    # σ_b = M·c/I  with  M = F·L_eff, c = t/2, I = w·t³/12   →
    # F ≈ σ_b · I / (c · L_eff) = σ_b · (w·t² / 6) / (0.92·L)
    I = width * thickness ** 3 / 12.0
    c = thickness / 2.0
    L_eff = length * 0.92
    # target a uniform σ_b in [60, 500] MPa, clipped to the data-contract force range
    sigma_b_target = rng.uniform(60.0, 500.0)
    force_capacity = sigma_b_target * I / (c * L_eff)   # N
    force = max(min(force_capacity, 4000.0), 200.0)
    angle = rng.uniform(-30.0, 30.0)         # deg
    E_GPa = rng.uniform(70.0, 210.0)         # GPa
    yld = rng.uniform(200.0, 900.0)          # MPa
    return [length, width, thickness, fillet, hole, force, angle, E_GPa, yld]


def _eval_response(x):
    """Map an input vector to (peak_vm_stress_MPa, peak_disp_mm)."""
    (length, width, thickness, fillet,
     hole, force, angle_deg, E_GPa, _yld) = x
    # --- bending stress at the constraint root ---
    # rectangular cross-section: I = width·thickness³ / 12  (mm⁴)
    # outer fibre distance c = thickness / 2  (mm)
    # bending moment M = F · L_eff  where L_eff slightly less than length
    L_eff_mm = length * 0.92
    I = width * thickness ** 3 / 12.0           # mm⁴
    c = thickness / 2.0                         # mm
    M = force * L_eff_mm                        # N·mm
    sigma_b = M * c / I                         # N/mm² = MPa
    # --- stress concentration at the fillet ---
    # ratio d/r ≈ thickness / fillet — classic geometric-discontinuity ratio
    ratio = thickness / max(fillet, 0.5)
    Kt = 1.0 + _KT_A * (ratio ** _KT_B)
    # --- hole net-section bump ---
    Kh = 1.0 + _KH_C * (hole / width) ** 2 if width > 0 else 1.0
    # --- angle-induced softening (bending dominates; axial/shear take some load) ---
    Kang = 1.0 - _ANG_DERATE * (angle_deg ** 2)
    Kang = max(Kang, 0.6)                       # floor — no unphysical signs
    peak_vm = sigma_b * Kt * Kh * Kang          # MPa
    # --- tip displacement: Euler-Bernoulli cantilever, δ = F·L³ / (3·E·I) ---
    # E_GPa = 1000 N/mm² ;  L in mm ;  I in mm⁴  =>  δ in mm
    E_Nmm2 = E_GPa * 1000.0
    delta = force * length ** 3 / (3.0 * E_Nmm2 * I)   # mm
    return peak_vm, delta


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        peak_vm, delta = _eval_response(x)
        # add modest multiplicative scatter to mimic mesh / post-processing noise
        peak_vm *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        delta *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        # clamp to data-contract.md ranges as a defensive guard
        peak_vm = max(min(peak_vm, 1200.0), 30.0)
        delta = max(min(delta, 20.0), 0.02)
        out.append(x + [peak_vm, delta])
    return out


def write_csv(rows, path):
    header = [
        "length_mm", "width_mm", "thickness_mm", "fillet_mm",
        "hole_dia_mm", "force_N", "force_angle_deg",
        "youngs_modulus_GPa", "yield_strength_MPa",
        "peak_vm_stress_MPa", "peak_disp_mm",
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:9]:
                out.append("%.4f" % v)
            out.append("%.3f" % r[9])     # stress
            out.append("%.4f" % r[10])    # displacement
            w.writerow(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rows", type=int, default=250)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--out", type=str, default=None)
    args = ap.parse_args()
    out_path = args.out
    if out_path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        out_path = os.path.join(here, "sample-dataset.csv")
    rows = synthesize(args.rows, args.seed)
    write_csv(rows, out_path)
    # quick summary so the reader (or a session) can sanity-check ranges
    vm = [r[9] for r in rows]
    dx = [r[10] for r in rows]
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  peak_vm_stress_MPa : min %.1f  max %.1f  mean %.1f"
          % (min(vm), max(vm), sum(vm) / len(vm)))
    print("  peak_disp_mm       : min %.3f  max %.3f  mean %.3f"
          % (min(dx), max(dx), sum(dx) / len(dx)))


if __name__ == "__main__":
    main()
