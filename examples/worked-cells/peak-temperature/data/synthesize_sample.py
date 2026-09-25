"""
Peak-Temperature Surrogate example — SAMPLE-DATA SYNTHESIZER
================================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real FE results.

The functional form here is an analytical *pastiche* of a 1-D pin fin
with internal volumetric heat generation and convective cooling on
the lateral surfaces — it is not a substitute for a real steady-state
thermal-FE solve. The purpose is to give the surrogate something
smoothly variable and qualitatively plausible to learn from, so the
reader can verify the workflow shape:

    fin parameter           m   = sqrt(h·P / (k·A))         (1/m)
    cross-section area      A   = w·t                       (m²)
    perimeter               P   = 2·(w + t)                 (m)
    volumetric heat source  q''' = q_W / (L·A)              (W/m³)
    equilibrium excess      T_eq - T_∞ = q''' / (k·m²)      (= q_W / (h·P·L))
    base excess temperature T_b - T_∞ = α(geometry) · q_W / (h·P·L_ref)
    analytical T(x) - T_∞   = T_eq + C1·cosh(m·x) + C2·sinh(m·x)

with C1 / C2 fixed by BCs: T(0) = T_b (prescribed by upstream thermal-
budget allocation that scales with q_W and L) and dT/dx(L) = 0
(adiabatic tip). The closed form admits two regimes: source-dominated
(T_b > T_eq → peak at x=0) and self-heating-dominated (T_b < T_eq →
peak in the interior at the point where dT/dx = 0). This split is
what makes `hot_spot_x_mm` a non-trivial second target.

The numerical coefficients are CHOSEN to make the synthetic responses
land in the data-contract.md typical ranges; they are NOT derived from
any specific FE benchmark and they do NOT reproduce the absolute
magnitudes of any specific real thermal-management component. See
data-contract.md for the illustrative-numerics framing.

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
_NOISE_FRAC = 0.025      # multiplicative scatter mimicking mesh / post-processing noise


def _sample_design(rng):
    """Sample one (geometry + material + boundary + operating-point) input vector.

    Heat-generation power `q_W` is sampled in a band that scales with the
    component's heat-rejection capacity so the design space stays inside
    the data-contract's typical peak-temperature range across the
    parameter cube. Without this coupling, a small, low-conductivity, low-h
    component at the top of the q_W range produces peak temperatures far
    above any realistic component-thermal-management benchmark (and far
    above the data contract's typical-range column). The coupling
    preserves the full range of `q_W` reported in the contract — `q_W` is
    still sampled from 1 to 200 W when geometry permits — but biases the
    sampler away from physically-implausible corners.
    """
    length_mm = rng.uniform(30.0, 200.0)        # mm
    width_mm = rng.uniform(10.0, 60.0)          # mm
    thickness_mm = rng.uniform(2.0, 20.0)       # mm
    conductivity = rng.uniform(10.0, 400.0)     # W/(m·K)  — polymer through copper
    h = rng.uniform(5.0, 250.0)                 # W/(m²·K) — natural through forced air
    T_amb = rng.uniform(-20.0, 80.0)            # °C
    # heat-rejection capacity ≈ h · A_surface · ΔT_allow
    # with A_surface = P · L (lateral) and ΔT_allow ≈ 200 K (target peak excess)
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    thickness_m = thickness_mm / 1000.0
    perimeter_m = 2.0 * (width_m + thickness_m)
    q_capacity = h * perimeter_m * length_m * 200.0   # W at ΔT_eq = 200 K
    # target a uniform q in [0.15, 1.10] × capacity, clipped to data-contract range
    q_target_frac = rng.uniform(0.15, 1.10)
    q_W = max(min(q_target_frac * q_capacity, 200.0), 1.0)
    return [length_mm, width_mm, thickness_mm, conductivity, h, T_amb, q_W]


def _eval_response(x):
    """Map an input vector to (peak_temp_C, hot_spot_x_mm).

    Closed-form analytical pin-fin solution under BCs:
        T(0) = T_b      (prescribed by upstream thermal-budget allocation)
        dT/dx(L) = 0    (adiabatic tip)

    Excess temperature θ(x) = T(x) - T_∞ satisfies
        d²θ/dx² - m²·θ + q'''/k = 0
    with particular solution θ_eq = q'''/(k·m²) = q_W / (h·P·L)
    and general solution θ(x) = θ_eq + C1·cosh(m·x) + C2·sinh(m·x).
    Applying the BCs gives
        C1 = θ_b - θ_eq
        C2 = -C1·tanh(m·L)
    and the location of the maximum (if interior) satisfies
        tanh(m·x_peak) = -C2 / C1 = tanh(m·L)
    i.e. x_peak = L. So when self-heating dominates and the base is
    cooler than the equilibrium excess, the peak is at the adiabatic
    tip; when the source side is hotter than the equilibrium, the peak
    is at the base x = 0. We add a small geometry-dependent offset to
    make the interior-peak case land at a non-degenerate interior
    position rather than exactly at L, mimicking the way a real fin
    with non-adiabatic-but-low-h tip would have its peak slightly
    inside the tip.
    """
    length_mm, width_mm, thickness_mm, conductivity, h, T_amb, q_W = x
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    thickness_m = thickness_mm / 1000.0

    A = width_m * thickness_m                              # m²
    P = 2.0 * (width_m + thickness_m)                      # m
    # fin parameter m  (1/m)
    m_fin = math.sqrt(h * P / (conductivity * A))
    # equilibrium excess temperature  (K)
    theta_eq = q_W / (h * P * length_m)
    # base excess temperature: derived from a fixed upstream cold-plate
    # thermal resistance R_th_plate (representing the heat-sink / coolant-
    # loop hardware the component is mounted on). This makes theta_base a
    # deterministic, learnable function of q_W alone — independent of the
    # fin's own geometry / cooling. The regime split then falls out
    # naturally: components where theta_base > theta_eq (well-cooled fin
    # but a bottlenecked upstream attachment) peak at x = 0; components
    # where theta_base < theta_eq (good upstream cold-plate but a long,
    # poorly-lateral-cooled fin) peak in the interior.
    R_TH_PLATE = 0.80    # K/W   — fixed cold-plate thermal resistance
    theta_base = R_TH_PLATE * q_W

    # closed-form profile constants
    mL = m_fin * length_m
    # numerical guard for very thermally-thick or very thermally-thin fins
    mL = min(mL, 12.0)
    C1 = theta_base - theta_eq
    C2 = -C1 * math.tanh(mL)

    # peak location: at x=0 if source-dominated (theta_base > theta_eq),
    # at x=L (the adiabatic tip) if self-heating-dominated.
    if theta_base >= theta_eq:
        x_peak_m = 0.0
        theta_peak = theta_base
    else:
        # interior maximum is at x = L (adiabatic-tip case); shift inward
        # by a small fraction of L to mimic finite-h tip BCs and avoid
        # the trivial L-always answer.
        tip_inset_frac = 0.05 + 0.10 * (1.0 - math.tanh(mL))   # 5-15% of L
        x_peak_m = length_m * (1.0 - tip_inset_frac)
        # evaluate the analytical profile at x_peak
        theta_peak = theta_eq + C1 * math.cosh(m_fin * x_peak_m) + C2 * math.sinh(m_fin * x_peak_m)

    peak_temp_C = T_amb + theta_peak
    hot_spot_x_mm = x_peak_m * 1000.0
    return peak_temp_C, hot_spot_x_mm


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        peak_T, hot_x = _eval_response(x)
        # add modest multiplicative scatter to mimic mesh / post-processing noise
        # (temperature excess, not absolute temperature, so subtract / add T_amb)
        T_amb = x[5]
        excess = peak_T - T_amb
        excess *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
        peak_T = T_amb + excess
        # additive scatter on hot-spot position (mm)
        hot_x += rng.gauss(0.0, 1.5)
        # clamp to data-contract ranges as a defensive guard
        peak_T = max(min(peak_T, 350.0), 30.0)
        hot_x = max(min(hot_x, x[0]), 0.0)   # clamp to [0, length_mm]
        out.append(x + [peak_T, hot_x])
    return out


def write_csv(rows, path):
    header = [
        "length_mm", "width_mm", "thickness_mm",
        "conductivity_W_mK", "h_W_m2K", "T_ambient_C", "q_W",
        "peak_temp_C", "hot_spot_x_mm",
    ]
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:7]:
                out.append("%.4f" % v)
            out.append("%.3f" % r[7])     # peak temp
            out.append("%.3f" % r[8])     # hot-spot x
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
    T = [r[7] for r in rows]
    xh = [r[8] for r in rows]
    # how many rows landed at the source-side peak (x ≈ 0) vs. interior-peak
    interior = sum(1 for v in xh if v > 5.0)
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  peak_temp_C   : min %.1f  max %.1f  mean %.1f"
          % (min(T), max(T), sum(T) / len(T)))
    print("  hot_spot_x_mm : min %.1f  max %.1f  mean %.1f"
          % (min(xh), max(xh), sum(xh) / len(xh)))
    print("  interior peaks (x > 5 mm) : %d / %d (%.0f %%)"
          % (interior, len(rows), 100.0 * interior / len(rows)))


if __name__ == "__main__":
    main()
