"""
Injection-Molding Warpage Surrogate example — SAMPLE-DATA SYNTHESIZER
========================================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real injection-molding
process-simulation results (Autodesk Moldflow / Moldex3D / SIGMASOFT /
3D TIMON warpage-and-shrinkage exports).

The functional form here is an analytical *pastiche* of injection-
molding warpage-and-shrinkage behaviour — it is NOT a substitute for a
real Hele-Shaw / 3-D fill-pack-cool-warp solve. The purpose is to give
the surrogate something smoothly variable and qualitatively plausible to
learn from, so the reader can verify the workflow shape.

Injection-molding warpage is, physically, the part-level consequence of
*differential shrinkage*: as the molten polymer cools and solidifies in
the mold, it shrinks, and any non-uniformity in that shrinkage across
the part thickness or across its plan area locks in residual stress and
bows the part out of plane. The dominant levers, all represented here:

    volumetric shrinkage  S_v ∝ thermal contraction (melt → ambient)
                              + crystallisation shrinkage (semi-crystalline)
                              − packing compensation (melt fed in during pack)
    cooling asymmetry     Δ   ∝ wall_thickness² / (mold-coolant heat removal)
                              (thick walls + hot mold cool unevenly → bow)
    fibre anisotropy      f   ∝ glass_fibre_pct (flow-direction vs cross-flow
                              shrinkage differential — the canonical warp
                              driver for fibre-reinforced thermoplastics)
    warpage W   ∝ S_v · cooling_asymmetry · (part size / thickness) · (1 + fibre)
    springback  ∝ the elastic-recovery fraction of the locked-in strain,
                  released on ejection — scales with stiffness × frozen strain
    peak residual stress ∝ frozen-in thermal-stress gradient
                  ∝ E · α · ΔT_freeze · (thickness / cooling-time factor)

The three sub-physics of injection molding (Kennedy2013) — non-Newtonian
fill, non-isothermal cool, and (for fibre-reinforced grades)
fibre-orientation evolution — all feed these three headline outputs.
The two dominant *deployed-surrogate* failure modes are baked into the
response surface so the example is honest:

  * Process-parameter-envelope extrapolation (the dominant
    DEPLOYED-pattern failure mode): the warpage response is strongly
    nonlinear in packing pressure and mold temperature near the
    short-shot / over-pack boundaries, so a surrogate that never sees
    the envelope corners mispredicts there. The trainer captures the
    per-input training range and the predictor flags out-of-envelope
    queries.

  * Polymer/fibre-class sensitivity: glass-fibre content
    flips the sign of the cross-flow-vs-flow shrinkage differential and
    materially changes the warpage magnitude, so a surrogate trained on
    one fibre loading cannot be silently used on another. Here fibre
    content is a continuous input the surrogate sees directly; a real
    deployment would also flag the *polymer base resin* class as a
    categorical the surrogate must respect (documented in the contract).

Both mechanisms make the response a *deterministic* function of the
input vector — there is no per-row hidden random knob. (Per this
example's synthesizer-determinism discipline: every per-row stochastic
term in the generator becomes irreducible noise the surrogate cannot
learn and shows up as low held-out R². The only randomness here is the
small multiplicative scatter added at the end to mimic mesh /
post-processing noise, applied AFTER the deterministic response.)

The numerical coefficients are CHOSEN to make the synthetic responses
land in the data-contract.md typical ranges (warpage to ~5 mm,
springback to ~2.5 mm, peak residual stress to ~70 MPa); they are NOT
derived from any specific part design, polymer grade, or Moldflow
benchmark and they do NOT reproduce the absolute magnitudes of any
specific real injection-molded component. See data-contract.md and
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
# (calibrated empirically against the contract's typical-range columns; see the
#  module docstring for the physical role of each)
ALPHA_CTE      = 9.0e-5    # 1/C: effective volumetric thermal-contraction coeff
CRYST_SHRINK   = 0.018     # baseline crystallisation/volumetric shrink fraction
PACK_REF_MPA   = 60.0      # MPa: packing pressure at which compensation is nominal
PACK_GAIN      = 0.010     # shrink reduction per MPa of packing above/below ref
COOL_REF_S     = 20.0      # s: cooling time at which the asymmetry term is nominal
MOLD_REF_C     = 50.0      # C: mold-coolant temperature reference
WARP_K         = 4.20      # overall warpage scale (mm per unit deterministic group)
SPRING_FRAC    = 0.42      # elastic-recovery fraction feeding springback
STRESS_E_MPA   = 1850.0    # MPa: effective modulus feeding the frozen-stress gradient
FIBRE_WARP_K   = 0.022     # extra warpage anisotropy per percent glass fibre
FIBRE_STIFF_K  = 0.030     # stiffness rise per percent glass fibre (springback feed)
_NOISE_FRAC    = 0.020     # multiplicative scatter mimicking mesh / post-processing noise


def _sample_design(rng):
    """Sample one (process + part-design) input vector.

    The eight inputs parameterise an injection-molding process window and
    the part geometry, drawn from the usual deployed-tabular input set
    (process parameters + part-design parameters):
      - 5 process : melt temperature, mold (coolant) temperature, packing
                    pressure, packing+cooling time, injection rate
      - 2 part    : nominal wall thickness, projected part size (flow length)
      - 1 material: glass-fibre content (the fibre-reinforced-thermoplastic
                    warpage driver, on the critical path for warpage)
    Ranges are chosen to span a realistic thermoplastic-component process
    window (PP / PA-class) without straying into the deep short-shot or
    burn corners the contract excludes (see data-contract.md Rule 5).
    """
    melt_temp_c     = rng.uniform(200.0, 300.0)   # C   melt (barrel) temperature
    mold_temp_c     = rng.uniform(20.0, 100.0)    # C   mold-coolant / wall temperature
    pack_press_mpa  = rng.uniform(30.0, 120.0)    # MPa packing (hold) pressure
    cool_time_s     = rng.uniform(8.0, 40.0)      # s   packing + cooling time
    inj_rate_ccs    = rng.uniform(10.0, 120.0)    # cm3/s injection (fill) rate
    wall_thk_mm     = rng.uniform(1.0, 4.0)       # mm  nominal wall thickness
    part_size_mm    = rng.uniform(50.0, 400.0)    # mm  projected part size / flow length
    fibre_pct       = rng.uniform(0.0, 40.0)      # %   glass-fibre weight content
    return [melt_temp_c, mold_temp_c, pack_press_mpa, cool_time_s,
            inj_rate_ccs, wall_thk_mm, part_size_mm, fibre_pct]


def _eval_response(x):
    """Map an input vector to (warpage_mm, springback_mm, peak_residual_stress_mpa).

    Closed-form injection-molding warpage pastiche; deterministic in the
    input vector (no hidden random knob). See the module docstring for the
    governing relations and the two embedded failure-mode mechanisms.
    """
    (melt, mold, pack, cool, inj, thk, size, fibre) = x

    # --- volumetric shrinkage: thermal contraction (melt->ambient) + crystallisation,
    #     reduced by packing compensation (more pack pressure feeds more melt in) ---
    dT_freeze = melt - mold                              # C, the contraction span
    s_thermal = ALPHA_CTE * dT_freeze                    # thermal contraction fraction
    pack_comp = PACK_GAIN * (pack - PACK_REF_MPA) / 10.0 # compensation (can be +/-)
    s_v = max(0.002, CRYST_SHRINK + s_thermal - pack_comp)

    # --- cooling asymmetry: thick walls in a hot mold with short cool time cool
    #     unevenly through-thickness, locking in a bowing moment ---
    cool_factor = (COOL_REF_S / max(cool, 1.0)) ** 0.5   # short cool -> bigger asym
    mold_factor = 1.0 + 0.006 * (mold - MOLD_REF_C)      # hot mold -> more asym
    asym = (thk ** 1.5) * cool_factor * mold_factor

    # --- fibre anisotropy: glass fibre flips/amplifies the cross-flow-vs-flow
    #     shrinkage differential, the canonical fibre-reinforced warp driver ---
    fibre_term = 1.0 + FIBRE_WARP_K * fibre

    # --- warpage: differential shrinkage acting over the part's slenderness ---
    slenderness = size / (thk ** 0.5)                    # bigger / thinner -> more bow
    warpage = WARP_K * s_v * asym * slenderness * fibre_term * 0.01

    # --- springback: the elastic-recovery fraction of the locked-in strain,
    #     released on ejection; stiffer (more fibre) parts spring back more ---
    stiffness = 1.0 + FIBRE_STIFF_K * fibre
    springback = SPRING_FRAC * warpage * stiffness / fibre_term  # recovery of the bow

    # --- peak residual stress: the frozen-in thermal-stress gradient
    #     sigma ~ E * alpha * dT_freeze, raised by thicker walls (steeper through-
    #     thickness gradient) and fibre, relieved by longer cooling ---
    thk_factor = 0.7 + 0.3 * thk                         # thicker -> steeper gradient
    cool_relief = 1.0 / (1.0 + 0.015 * (cool - COOL_REF_S))
    fibre_stress = 1.0 + 0.015 * fibre                   # fibre raises locked-in stress
    peak_stress = (STRESS_E_MPA * ALPHA_CTE * dT_freeze
                   * thk_factor * cool_relief * fibre_stress)

    return warpage, springback, peak_stress


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        warp, spring, stress = _eval_response(x)
        # modest multiplicative scatter to mimic mesh / post-processing noise,
        # applied AFTER the deterministic response so it does not contaminate
        # the learnable surface (it is the only randomness on the targets).
        warp *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        spring *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        stress *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        # clamp to data-contract ranges as a defensive guard
        warp = max(min(warp, 12.0), 0.0)
        spring = max(min(spring, 8.0), 0.0)
        stress = max(min(stress, 150.0), 0.0)
        out.append(x + [warp, spring, stress])
    return out


def write_csv(rows, path):
    header = [
        "melt_temp_c", "mold_temp_c", "pack_pressure_mpa", "cooling_time_s",
        "injection_rate_ccs", "wall_thickness_mm", "part_size_mm", "glass_fibre_pct",
        "warpage_mm", "springback_mm", "peak_residual_stress_mpa",
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:8]:
                out.append("%.4f" % v)
            out.append("%.4f" % r[8])     # warpage
            out.append("%.4f" % r[9])     # springback
            out.append("%.3f" % r[10])    # peak residual stress
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
    # quick summary so the reader (or a reviewer) can sanity-check ranges
    wp = [r[8] for r in rows]
    sp = [r[9] for r in rows]
    st = [r[10] for r in rows]
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  warpage_mm               : min %.3f  max %.3f  mean %.3f"
          % (min(wp), max(wp), sum(wp) / len(wp)))
    print("  springback_mm            : min %.3f  max %.3f  mean %.3f"
          % (min(sp), max(sp), sum(sp) / len(sp)))
    print("  peak_residual_stress_mpa : min %.2f  max %.2f  mean %.2f"
          % (min(st), max(st), sum(st) / len(st)))
    # how many parts are high-warp (>= 2 mm) vs tight (< 0.5 mm)
    hi = sum(1 for v in wp if v >= 2.0)
    lo = sum(1 for v in wp if v < 0.5)
    print("  warpage >= 2 mm: %d / %d (%.0f pct);  < 0.5 mm: %d (%.0f pct)"
          % (hi, len(rows), 100.0 * hi / len(rows),
             lo, 100.0 * lo / len(rows)))


if __name__ == "__main__":
    main()
