"""
Temperature-Field Surrogate example -- SAMPLE-DATA SYNTHESIZER
=================================================================
Generates an *illustrative* sample dataset that the reader can use to
run the trainer end-to-end before supplying real steady-state thermal-FE
field results.

This is the first FIELD-output worked cell (grid cell n=1, m=2,
bucket B2). It bridges from the peak-temperature example (a B1 scalar
example) by stepping the OUTPUT from a single peak number to the whole
temperature field T(x) laid out on a fixed regular voxel grid. The input
vocabulary is the SAME seven thermal parameters as the peak-temperature
example.

Source-of-truth note (ASCII-only by discipline). This file deliberately
uses ASCII-only source (words like "alpha", "theta", "->", "deg" rather
than the Unicode glyphs) per this example's synthesizer-source rule: a
non-ASCII run that crosses an internal write boundary can deterministically
truncate the written file.

------------------------------------------------------------------
The field model (an analytical pastiche, NOT a real thermal-FE solve)
------------------------------------------------------------------
The temperature field is the SAME closed-form pin-fin profile that
the peak-temperature example used for its scalar peak, now EVALUATED AT
EVERY VOXEL of a
regular grid rather than only at the peak location. Concretely, the
component is modelled as a 1-D conducting fin along its length (the
"cooling axis", index i below) with:

    cross-section area      A      = w * t                  (m^2)
    perimeter               P      = 2 * (w + t)            (m)
    fin parameter           m_fin  = sqrt(h * P / (k * A))  (1/m)
    equilibrium excess      theta_eq = q_W / (h * P * L)    (K)
    base excess             theta_b  = R_TH_PLATE * q_W      (K)

The excess-temperature profile along the length is the analytical
solution of the fin equation under base-temperature + adiabatic-tip
boundary conditions:

    theta(s) = theta_eq + C1 * cosh(m_fin * s) + C2 * sinh(m_fin * s)
    C1 = theta_b - theta_eq
    C2 = -C1 * tanh(m_fin * L)

with s the distance from the base (s = 0) to the tip (s = L). This is a
deterministic function of the seven inputs and the position s.

To make it a genuine 3-D FIELD (not just a 1-D line) we add two smooth,
deterministic cross-section terms so the field varies in all three axes,
the way a real conducting solid's temperature does:

  * a LATERAL (width, index j) parabolic dip toward the cooled faces:
    points near the cooled surface (the edges of the width) sit slightly
    cooler than the core, scaled by the local convective strength. This
    is the standard "core hotter than skin" conduction signature.
  * a THROUGH-THICKNESS (index k) parabolic dip of the same kind but
    weaker (the thickness is the short dimension, so the gradient is
    smaller).

Both cross-section terms are deterministic, smooth, and vanish at the
geometric centre-line, so the field's maximum still tracks the 1-D fin
peak. The whole field is therefore POINTWISE-DETERMINISTIC in the seven
inputs and the (i, j, k) voxel coordinates -- the determinism discipline
holds across the entire grid, which is what a field surrogate needs in
order to be learnable.

The numerical coefficients are CHOSEN to make the synthetic field land
in the data-contract typical ranges; they are NOT derived from any
specific FE benchmark and do NOT reproduce the absolute magnitudes of any
specific real thermal-management component. See data-contract.md and
WALKTHROUGH.md section 4 for the illustrative-numerics framing.

------------------------------------------------------------------
The grid and the CSV layout
------------------------------------------------------------------
The field is sampled on a fixed regular grid of shape

    (NX, NY, NZ) = (12, 8, 8)   -> 768 voxels per run

indexed i = 0..NX-1 along the length, j = 0..NY-1 across the width,
k = 0..NZ-1 through the thickness. The voxel grid is NORMALISED: it
always has the same shape regardless of the component's physical
dimensions, so every row of the dataset has the same 768 output columns.
(This is the standard regular-grid B2 convention -- the physical extent
varies per run but the grid topology is fixed, which is exactly what lets
a single CNN-style decoder read every row.)

Each dataset row is:

    7 input columns   (the same vocabulary as the peak-temperature example)
  + 768 field columns (T_000 ... T_767, voxel-major in i, then j, then k)
  + 1 optional notes column

The field columns are named T_<iii> with a zero-padded flat index
flat = (i * NY + j) * NZ + k. The trainer and the data-contract both
document this flattening so a reader can re-fold the 768 numbers back
into a (12, 8, 8) grid for plotting.

Run:
    python synthesize_sample.py
    python synthesize_sample.py --rows 400 --seed 7 --out my-data.csv
"""

import argparse
import csv
import math
import os
import random


# --- fixed grid shape: same for every run (the regular-grid B2 convention) ---
NX = 12   # voxels along the length (the cooling axis)
NY = 8    # voxels across the width
NZ = 8    # voxels through the thickness
N_VOXELS = NX * NY * NZ   # 768

# --- coefficients tuned so the synthetic field covers the contract ranges ---
R_TH_PLATE = 0.80      # K/W  -- fixed upstream cold-plate thermal resistance
LATERAL_DIP_FRAC = 0.18   # max fractional cross-section dip across the width
THROUGH_DIP_FRAC = 0.08   # max fractional dip through the thickness (weaker)
_NOISE_FRAC = 0.015    # small multiplicative scatter mimicking mesh noise


def flat_index(i, j, k):
    """Voxel-major flat index: i outer (length), then j (width), then k (thickness)."""
    return (i * NY + j) * NZ + k


def _sample_design(rng):
    """Sample one (geometry + material + boundary + operating-point) input vector.

    Identical sampling discipline to the peak-temperature example: the
    heat-generation power
    q_W is sampled in a band that scales with the component's heat-rejection
    capacity so the design space stays inside the data-contract's typical
    temperature range across the parameter cube.
    """
    length_mm = rng.uniform(30.0, 200.0)        # mm
    width_mm = rng.uniform(10.0, 60.0)          # mm
    thickness_mm = rng.uniform(2.0, 20.0)       # mm
    conductivity = rng.uniform(10.0, 400.0)     # W/(m K)  -- polymer through copper
    h = rng.uniform(5.0, 250.0)                 # W/(m^2 K) -- natural through forced air
    T_amb = rng.uniform(-20.0, 80.0)            # deg C
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    thickness_m = thickness_mm / 1000.0
    perimeter_m = 2.0 * (width_m + thickness_m)
    q_capacity = h * perimeter_m * length_m * 200.0   # W at delta-T_eq = 200 K
    q_target_frac = rng.uniform(0.15, 1.10)
    q_W = max(min(q_target_frac * q_capacity, 200.0), 1.0)
    return [length_mm, width_mm, thickness_mm, conductivity, h, T_amb, q_W]


def _profile_constants(x):
    """Return the deterministic 1-D fin-profile constants for input vector x.

    These are computed once per run and then reused at every voxel.
    """
    length_mm, width_mm, thickness_mm, conductivity, h, T_amb, q_W = x
    length_m = length_mm / 1000.0
    width_m = width_mm / 1000.0
    thickness_m = thickness_mm / 1000.0

    A = width_m * thickness_m                       # m^2
    P = 2.0 * (width_m + thickness_m)               # m
    m_fin = math.sqrt(h * P / (conductivity * A))   # 1/m
    theta_eq = q_W / (h * P * length_m)             # K
    theta_b = R_TH_PLATE * q_W                      # K
    mL = min(m_fin * length_m, 12.0)                # guard thermally-thick fins
    C1 = theta_b - theta_eq
    C2 = -C1 * math.tanh(mL)
    return {
        "length_m": length_m, "m_fin": m_fin, "mL": mL,
        "theta_eq": theta_eq, "C1": C1, "C2": C2,
        "T_amb": T_amb, "h": h,
    }


def _field(x):
    """Map an input vector to the full (NX, NY, NZ) temperature field, flattened.

    The value at voxel (i, j, k) is a DETERMINISTIC function of the seven
    inputs and the voxel coordinates:

        T(i,j,k) = T_amb
                 + theta_axis(s_i)                 (the 1-D fin profile)
                 * (1 - lateral_dip(j))            (cooler toward width faces)
                 * (1 - through_dip(k))            (cooler toward thickness faces)

    s_i is the physical distance from the base for grid index i. The dips
    are smooth parabolas that vanish on the centre-line and reach their
    maximum at the cooled faces, scaled by a convective-strength factor so
    that strongly-cooled components (high h) show a sharper core-to-skin
    gradient -- the qualitatively-correct conduction signature.
    """
    c = _profile_constants(x)
    length_m = c["length_m"]
    m_fin = c["m_fin"]
    theta_eq = c["theta_eq"]
    C1 = c["C1"]
    C2 = c["C2"]
    T_amb = c["T_amb"]
    h = c["h"]

    # convective-strength factor in [0, 1]: scales the cross-section dips so
    # high-h (well-cooled) parts have a larger skin-to-core gradient.
    cool_strength = h / (h + 60.0)   # smooth, in (0, 1), ~0.5 at h=60

    field = [0.0] * N_VOXELS
    for i in range(NX):
        # physical distance from the base for this length index (centre of cell)
        frac_len = (i + 0.5) / NX
        s = frac_len * length_m
        theta_axis = theta_eq + C1 * math.cosh(m_fin * s) + C2 * math.sinh(m_fin * s)
        if theta_axis < 0.0:
            theta_axis = 0.0    # guard: excess temperature is non-negative
        for j in range(NY):
            # lateral parabolic dip: 0 at centre (j_norm=0), 1 at faces (|j_norm|=1)
            j_norm = (2.0 * (j + 0.5) / NY) - 1.0
            lateral_dip = LATERAL_DIP_FRAC * cool_strength * (j_norm * j_norm)
            for k in range(NZ):
                k_norm = (2.0 * (k + 0.5) / NZ) - 1.0
                through_dip = THROUGH_DIP_FRAC * cool_strength * (k_norm * k_norm)
                theta = theta_axis * (1.0 - lateral_dip) * (1.0 - through_dip)
                field[flat_index(i, j, k)] = T_amb + theta
    return field


def synthesize(rows, seed):
    rng = random.Random(seed)
    out = []
    for _ in range(rows):
        x = _sample_design(rng)
        field = _field(x)
        T_amb = x[5]
        # small multiplicative scatter on the EXCESS temperature, per voxel,
        # mimicking mesh / post-processing noise. The scatter is random (it is
        # the only random part of the output); the underlying field is fully
        # deterministic in the inputs + coordinates.
        noisy = []
        for v in field:
            excess = v - T_amb
            excess *= 1.0 + rng.gauss(0.0, _NOISE_FRAC)
            t = T_amb + excess
            # defensive clamp to the data-contract field range
            t = max(min(t, 400.0), -40.0)
            noisy.append(t)
        out.append(x + noisy)
    return out


def field_columns():
    return ["T_%03d" % f for f in range(N_VOXELS)]


def write_csv(rows, path):
    header = [
        "length_mm", "width_mm", "thickness_mm",
        "conductivity_W_mK", "h_W_m2K", "T_ambient_C", "q_W",
    ] + field_columns()
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        for r in rows:
            out = []
            for v in r[:7]:
                out.append("%.4f" % v)
            for v in r[7:]:
                out.append("%.3f" % v)
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
    field_max = []
    field_min = []
    field_mean = []
    for r in rows:
        f = r[7:]
        field_max.append(max(f))
        field_min.append(min(f))
        field_mean.append(sum(f) / len(f))
    overall_peak = max(field_max)
    overall_floor = min(field_min)
    print("Wrote %d rows to %s" % (len(rows), out_path))
    print("  grid shape         : (%d, %d, %d) = %d voxels per run"
          % (NX, NY, NZ, N_VOXELS))
    print("  per-run peak temp  : min %.1f  max %.1f  (deg C)"
          % (min(field_max), max(field_max)))
    print("  per-run mean temp  : min %.1f  max %.1f  (deg C)"
          % (min(field_mean), max(field_mean)))
    print("  overall field range: %.1f .. %.1f  (deg C)"
          % (overall_floor, overall_peak))


if __name__ == "__main__":
    main()
